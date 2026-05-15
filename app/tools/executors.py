from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Company, Document, DocumentChunk
from app.services import edgar_service
from app.services.document_processor import process_document
from app.services.embeddings import embed_texts
from app.services.stock_service import (
    calculate_returns,
    compare_to_benchmark,
    fetch_price_history,
    get_stock_valuation,
)


async def execute_tool(name: str, args: dict, db: AsyncSession) -> dict:
    if name == "fetch_10k":
        return await _fetch_and_ingest_10k(args["ticker"], int(args["year"]), db)

    if name == "get_stock_valuation":
        return await get_stock_valuation(ticker=args["ticker"])

    if name == "get_stock_metrics":
        return await calculate_returns(
            ticker=args["ticker"],
            start=date.fromisoformat(args["start_date"]),
            end=date.fromisoformat(args["end_date"]),
        )

    if name == "get_stock_history":
        rows = await fetch_price_history(
            ticker=args["ticker"],
            start=date.fromisoformat(args["start_date"]),
            end=date.fromisoformat(args["end_date"]),
        )
        # cap at 30 rows so the result doesn't overflow Gemini's context
        return {"ticker": args["ticker"].upper(), "data": rows[:30]}

    if name == "search_filings":
        return await _search_filings(args, db)

    if name == "compare_to_benchmark":
        return await compare_to_benchmark(
            ticker=args["ticker"],
            start=date.fromisoformat(args["start_date"]),
            end=date.fromisoformat(args["end_date"]),
            benchmark=args.get("benchmark", "SPY"),
        )

    return {"error": f"Unknown tool: {name}"}


async def _search_filings(args: dict, db: AsyncSession) -> dict:
    query = args["query"]
    ticker = args.get("ticker")
    year = args.get("year")
    top_k = int(args.get("top_k", 5))

    embeddings = await embed_texts([query])
    query_vector = embeddings[0]

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
        .join(Company, Document.company_id == Company.id)
        .where(Document.status == "completed")
        .order_by(DocumentChunk.embedding.cosine_distance(query_vector))
        .limit(top_k)
    )

    if ticker:
        stmt = stmt.where(Company.ticker == ticker.upper())
    if year:
        stmt = stmt.where(Document.year == int(year))

    rows = (await db.execute(stmt)).all()

    return {
        "results": [
            {
                "content": row.content,
                "ticker": row.ticker,
                "year": row.year,
                "doc_type": row.doc_type,
                "similarity": round(1 - row.distance, 4),
            }
            for row in rows
        ]
    }


async def _fetch_and_ingest_10k(ticker: str, year: int, db: AsyncSession) -> dict:
    try:
        text, meta = await edgar_service.download_and_save_10k(ticker, year)

        result = await db.execute(select(Company).where(Company.ticker == ticker.upper()))
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

        return {
            "status": "success",
            "ticker": ticker.upper(),
            "year": year,
            "filing_date": meta.get("filing_date"),
            "message": f"10-K for {ticker.upper()} {year} ingested successfully. Now retry search_filings.",
        }
    except Exception as exc:
        return {"status": "error", "ticker": ticker.upper(), "year": year, "message": str(exc)}
