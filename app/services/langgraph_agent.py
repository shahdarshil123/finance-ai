"""
LangGraph-based agent that:
  1. Extracts ticker + year from the user query
  2. Searches the local pgvector store (RAG)
  3. If nothing is found, auto-downloads the 10-K from SEC EDGAR and ingests it
  4. Retries RAG, then generates a grounded answer via Gemini

Graph:
    extract_params → rag_search ──(chunks found)──→ generate_answer → END
                                 └─(no chunks)────→ fetch_and_ingest → rag_search
"""

import asyncio
import json
import operator
import os
from collections.abc import AsyncGenerator
from typing import Annotated, TypedDict

from google import genai
from google.genai import types
from langgraph.graph import END, StateGraph
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Company, Document, DocumentChunk
from app.db.session import AsyncSessionLocal
from app.services import edgar_service
from app.services.document_processor import process_document
from app.services.embeddings import embed_texts

settings = get_settings()

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class GraphState(TypedDict):
    query:           str
    search_query:    str        # document-friendly query used for vector search
    ticker:          str | None
    year:            int | None
    chunks:          list[dict]
    already_fetched: bool
    final_answer:    str
    # operator.add means each node's returned list is appended, not replaced
    steps:           Annotated[list[str], operator.add]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def extract_params_node(state: GraphState) -> dict:
    """Ask Gemini to extract ticker, year, and a document-friendly RAG search query."""
    client = _get_client()
    prompt = (
        "Analyse this financial question and return JSON with three fields:\n"
        "  ticker:       stock ticker symbol, or null\n"
        "  year:         fiscal year as integer, or null\n"
        "  search_query: a SHORT noun phrase (5-10 words) in 10-K filing language that will "
        "retrieve the most relevant passages via vector search. "
        "Use terms like 'total net sales revenue', 'operating income margin', "
        "'gross margin performance', 'segment revenue breakdown', "
        "'annual revenue results', 'financial highlights'. "
        "Never use question form.\n\n"
        "Return ONLY valid JSON — no markdown:\n"
        "{\"ticker\": string|null, \"year\": int|null, \"search_query\": string}\n\n"
        f"Question: {state['query']}"
    )
    response = await asyncio.to_thread(
        client.models.generate_content,
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    try:
        data         = json.loads(response.text)
        ticker       = data.get("ticker") or None
        year         = int(data["year"]) if data.get("year") else None
        search_query = data.get("search_query") or state["query"]
    except Exception:
        ticker, year, search_query = None, None, state["query"]

    return {
        "ticker":       ticker,
        "year":         year,
        "search_query": search_query,
        "steps":        [f"Identified: {ticker or '?'} / {year or '?'} — RAG query: \"{search_query}\""],
    }


async def rag_search_node(state: GraphState) -> dict:
    """Cosine-similarity search over ingested document chunks."""
    search_text = state.get("search_query") or state["query"]
    async with AsyncSessionLocal() as db:
        [query_vector] = await embed_texts([search_text])

        stmt = (
            select(
                DocumentChunk.content,
                DocumentChunk.chunk_index,
                Document.year,
                Document.doc_type,
                Company.ticker,
                DocumentChunk.embedding.cosine_distance(query_vector).label("distance"),
            )
            .join(Document, DocumentChunk.document_id == Document.id)
            .join(Company,  Document.company_id == Company.id)
            .where(Document.status == "completed")
            .order_by(DocumentChunk.embedding.cosine_distance(query_vector))
            .limit(8)
        )

        if state.get("ticker"):
            stmt = stmt.where(Company.ticker == state["ticker"].upper())
        if state.get("year"):
            stmt = stmt.where(Document.year == state["year"])

        rows = (await db.execute(stmt)).all()

    chunks = [
        {
            "content":    row.content,
            "ticker":     row.ticker,
            "year":       row.year,
            "doc_type":   row.doc_type,
            "similarity": round(1 - row.distance, 4),
        }
        for row in rows
    ]
    return {
        "chunks": chunks,
        "steps":  [f"Vector search returned {len(chunks)} chunks"],
    }


async def fetch_and_ingest_node(state: GraphState) -> dict:
    """Download the 10-K from SEC EDGAR and ingest it into pgvector."""
    ticker = state["ticker"]
    year   = state["year"]
    steps  = [f"No local data found — fetching {ticker} {year} 10-K from SEC EDGAR…"]

    try:
        text, meta = await edgar_service.download_and_save_10k(
            ticker, year, emit=steps.append
        )
        steps.append(f"Saved as {os.path.splitext(meta['file_path'])[1].upper()}. Ingesting…")

        async with AsyncSessionLocal() as db:
            result  = await db.execute(
                select(Company).where(Company.ticker == ticker.upper())
            )
            company = result.scalar_one_or_none()
            if not company:
                company = Company(ticker=ticker.upper(), name=ticker.upper())
                db.add(company)
                await db.flush()

            document = Document(
                company_id=company.id,
                year=year,
                doc_type="10-K",
                status="pending",
                file_path=meta.get("file_path"),
            )
            db.add(document)
            await db.commit()
            await db.refresh(document)

            await process_document(document.id, text, db)

        steps.append("Ingestion complete — retrying search.")
    except Exception as exc:
        steps.append(f"Fetch/ingest failed: {exc}")

    return {"already_fetched": True, "steps": steps}


async def generate_answer_node(state: GraphState) -> dict:
    """Synthesise a grounded answer from retrieved chunks using Gemini."""
    chunks = state.get("chunks", [])

    if not chunks:
        parts = ["No relevant passages found"]
        if state.get("ticker"):
            parts.append(f"for {state['ticker']}")
        if state.get("year"):
            parts.append(f"({state['year']})")
        if state.get("already_fetched"):
            parts.append("— filing was downloaded but may not contain the answer")
        return {
            "final_answer": " ".join(parts) + ".",
            "steps": ["No chunks available, returning fallback answer"],
        }

    context = "\n\n---\n\n".join(
        f"[{c['ticker']} · {c['doc_type']} · {c['year']}  sim={c['similarity']}]\n{c['content']}"
        for c in chunks
    )
    client = _get_client()
    prompt = (
        "You are a financial analyst. A user asked a question about a company's financials.\n"
        "You have retrieved passages from the company's 10-K SEC filing.\n\n"
        "Instructions:\n"
        "- If the excerpts contain the answer, lead with the specific figures "
        "(numbers, percentages) and cite the filing year.\n"
        "- If the excerpts contain partial data (e.g., actual results but no guidance), "
        "report what IS available and explicitly note what is missing from the filing.\n"
        "- If specific information (e.g., formal revenue guidance) is not in 10-K filings "
        "by nature — explain that and provide relevant context from the filing instead "
        "(e.g., actual revenue, YoY growth, management commentary on performance).\n"
        "- Clearly separate filing data from general knowledge: "
        "prefix filing facts with 'From the 10-K:' and added context with 'Note:'.\n\n"
        f"Question: {state['query']}\n\n"
        f"10-K excerpts:\n{context}\n\nAnswer:"
    )
    response = await asyncio.to_thread(
        client.models.generate_content,
        model=settings.gemini_model,
        contents=prompt,
    )
    return {
        "final_answer": response.text,
        "steps": [f"Answer generated from {len(chunks)} chunks"],
    }


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def _route_after_search(state: GraphState) -> str:
    if state.get("chunks"):
        return "generate"
    if state.get("ticker") and state.get("year") and not state.get("already_fetched"):
        return "fetch"
    return "generate"


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

def _build_graph():
    g = StateGraph(GraphState)

    g.add_node("extract_params",   extract_params_node)
    g.add_node("rag_search",       rag_search_node)
    g.add_node("fetch_and_ingest", fetch_and_ingest_node)
    g.add_node("generate_answer",  generate_answer_node)

    g.set_entry_point("extract_params")
    g.add_edge("extract_params",   "rag_search")
    g.add_conditional_edges(
        "rag_search",
        _route_after_search,
        {"fetch": "fetch_and_ingest", "generate": "generate_answer"},
    )
    g.add_edge("fetch_and_ingest", "rag_search")
    g.add_edge("generate_answer",  END)

    return g.compile()


_graph = _build_graph()


# ---------------------------------------------------------------------------
# Public entry point — yields SSE-formatted strings
# ---------------------------------------------------------------------------

async def run_graph_agent(query: str) -> AsyncGenerator[str, None]:
    initial: GraphState = {
        "query":           query,
        "search_query":    query,
        "ticker":          None,
        "year":            None,
        "chunks":          [],
        "already_fetched": False,
        "final_answer":    "",
        "steps":           [],
    }

    try:
        async for update in _graph.astream(initial, stream_mode="updates"):
            for _node, output in update.items():
                for step in output.get("steps", []):
                    yield f"data: {json.dumps({'type': 'step', 'content': step})}\n\n"

                if output.get("chunks"):
                    payload = {
                        "type":   "tool_result",
                        "tool":   "search_filings",
                        "result": {"results": output["chunks"]},
                    }
                    yield f"data: {json.dumps(payload)}\n\n"

                if output.get("final_answer"):
                    payload = {"type": "final_answer", "content": output["final_answer"]}
                    yield f"data: {json.dumps(payload)}\n\n"

    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"
    finally:
        yield "data: [DONE]\n\n"
