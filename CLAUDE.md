# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Start all services (Docker):**
```bash
docker-compose up --build
```

**Local development (requires PostgreSQL running separately):**
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**Reset the database (wipes all data):**
```bash
docker-compose down -v
docker-compose up --build
```

**Health check:**
```bash
curl http://localhost:8000/health
```

No test framework or linter is configured yet.

## Architecture

This is a **financial AI assistant** for analyzing SEC 10-K filings and stock prices. The stack is FastAPI + PostgreSQL 16 + pgvector + React, using async/await throughout (asyncpg driver).

**Services run via Docker Compose:**
- `api` container: FastAPI on port 8000, source-mounted so `--reload` picks up changes
- `db` container: `pgvector/pgvector:pg16` image on port 5432; API waits for its healthcheck before starting
- Frontend (Vite dev server): React 18 on port 5173

### Module layout

```
app/
  main.py                     FastAPI app, router registration
  core/config.py              Pydantic-settings loaded from .env
  db/
    models.py                 ORM models: Company, Document, DocumentChunk, StockPrice
    session.py                Async SQLAlchemy session factory + DB init
  api/
    ingestion.py              EDGAR download, progress polling, document viewer
    agent.py                  Streaming RAG agent endpoint (SSE)
    search.py                 Vector similarity search
    stocks.py                 Stock price history & metrics
  services/
    embeddings.py             BAAI/bge-small-en-v1.5 model loader (384-dim)
    document_processor.py     Sentence-boundary chunking, embedding storage
    edgar_service.py          SEC EDGAR CIK lookup, filing discovery, PDF/HTML download
    langgraph_agent.py        LangGraph RAG agent with auto-fetch and Gemini
    agent_service.py          Tool-calling agent loop with Gemini
    stock_service.py          yfinance OHLCV + alpha vs S&P 500
  tools/
    definitions.py            Gemini tool function schemas
    executors.py              Tool execution logic

frontend/src/
  App.jsx                     React Router, navbar
  pages/
    Dashboard.jsx             Stock chart + return metrics
    Upload.jsx                EDGAR download form + PDF viewer
    Analysis.jsx              Chat with streaming agent
  components/
    ChatInterface.jsx         SSE chat UI with source panel
    DocumentUpload.jsx        Form, live progress log, PDF viewer
    StockChart.jsx            OHLCV price chart
    CompanySelector.jsx       Ticker + date picker

mcp_servers/
  edgar_server.py             FastMCP server exposing EDGAR tools to Claude Desktop
```

### Key workflows

**Ingest → Search → Answer**
1. User enters ticker + year on Upload page
2. API downloads 10-K from SEC EDGAR (PDF first, falls back to HTML)
3. Document is chunked by sentence boundaries and embedded via sentence-transformers
4. Chunks + embeddings stored in pgvector
5. User asks a question on Analysis page
6. LangGraph agent searches pgvector; if no chunks found, auto-downloads the filing and retries
7. Agent calls Gemini with retrieved context and streams the answer via SSE

**Stock Dashboard**
- Fetches OHLCV history from yfinance
- Calculates total return and alpha vs S&P 500
- Displays interactive chart and metrics cards

**MCP integration**
- `mcp_servers/edgar_server.py` exposes three tools to Claude Desktop:
  - `list_10k_filings(ticker)` — available filing years
  - `get_filing_metadata(ticker, year)` — accession number and URL
  - `download_10k(ticker, year)` — full text content

### API routes

| Router prefix | Key endpoints |
|---|---|
| `/api/v1/stocks` | `GET /history`, `GET /metrics` |
| `/api/v1/ingest` | `POST /download`, `GET /progress/{id}`, `GET /document/{id}`, `DELETE /delete/all`, `POST /text` |
| `/api/v1/search` | `GET /` (cosine similarity, filter by ticker/year) |
| `/api/v1/agent` | `POST /query` (SSE stream) |

## Environment

Copy `.env.example` to `.env` before running locally. Key variables:

- `DATABASE_URL` — asyncpg connection string (defaults point to Docker service `db`)
- `GEMINI_API_KEY` — Google Generative AI key (Gemini 2.5 Flash); required for agent and query extraction
- `EMBEDDING_MODEL` / `EMBEDDING_DIMENSION` — model name and vector size (default: `BAAI/bge-small-en-v1.5`, 384)
- `CHUNK_SIZE` / `CHUNK_OVERLAP` — document chunking parameters (default: 512 tokens)
- `OLLAMA_BASE_URL` — for optional local LLM integration
