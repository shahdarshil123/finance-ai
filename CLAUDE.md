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

This is a **document ingestion service** for financial reports (10-K filings) with vector search. The stack is FastAPI + PostgreSQL 16 + pgvector, using async/await throughout (asyncpg driver).

**Services run via Docker Compose:**
- `api` container: FastAPI on port 8000, source-mounted so `--reload` picks up changes
- `db` container: `pgvector/pgvector:pg16` image on port 5432; API waits for its healthcheck before starting

**Planned module layout under `app/`** (all files are currently empty stubs):

| Module | Responsibility |
|---|---|
| `main.py` | FastAPI app instantiation, router registration |
| `core/config.py` | Pydantic-settings config loaded from `.env` |
| `db/models.py` | SQLAlchemy ORM models (documents, chunks, embeddings) |
| `db/session.py` | Async SQLAlchemy session factory |
| `services/embeddings.py` | Generates 384-dim vectors using `BAAI/bge-small-en-v1.5` via sentence-transformers |
| `services/document_processor.py` | PDF/text extraction (pdfplumber + PyPDF2), sentence-boundary chunking with overlap |
| `api/ingestion.py` | Routes: `POST /api/v1/ingest/pdf`, `POST /api/v1/ingest/text`, `GET /api/v1/status` |

**Data flow:** Document uploaded → extracted & chunked by `document_processor` → each chunk embedded by `embeddings` service → stored in PostgreSQL with pgvector column for similarity search.

## Environment

Copy `.env.example` to `.env` before running locally. Key variables:

- `DATABASE_URL` — asyncpg connection string (defaults point to Docker service `db`)
- `EMBEDDING_MODEL` / `EMBEDDING_DIMENSION` — model name and vector size (default: `BAAI/bge-small-en-v1.5`, 384)
- `CHUNK_SIZE` / `CHUNK_OVERLAP` — document chunking parameters
- `GEMINI_API_KEY` — for the planned agentic reasoning layer (not yet implemented)
- `OLLAMA_BASE_URL` — for local LLM integration (not yet implemented)

## Roadmap

Planned features not yet implemented:
1. Vector similarity search endpoint
2. MCP tool integration
3. Agentic reasoning layer via Gemini API
