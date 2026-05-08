# Financial AI Agent

FastAPI-based document ingestion service for 10-K financial reports with embeddings and vector search.

## Quick Start

### 1. Prerequisites
- Docker & Docker Compose
- Python 3.11+

### 2. Setup Environment
```bash
cp .env.example .env
# Edit .env if needed (defaults work for local Docker)
```

### 3. Start Services
```bash
docker-compose up --build
```

This starts:
- **FastAPI API** on `http://localhost:8000`
- **PostgreSQL + pgvector** on `localhost:5432`

### 4. Test Health Check
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "ok"}
```

## API Endpoints

### Health Check
```bash
GET /health
```

### Ingest PDF Document
```bash
curl -X POST "http://localhost:8000/api/v1/ingest/pdf" \
  -F "file=@document.pdf" \
  -F "ticker=AAPL" \
  -F "year=2023"
```

### Ingest Text Content
```bash
curl -X POST "http://localhost:8000/api/v1/ingest/text" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Your text here...",
    "ticker": "AAPL",
    "year": 2023,
    "section": "earnings_call"
  }'
```

### Check Ingestion Status
```bash
curl http://localhost:8000/api/v1/status
```

## Project Structure
```
app/
├── main.py              # FastAPI entry point
├── core/
│   └── config.py        # Configuration management
├── db/
│   ├── models.py        # SQLAlchemy models
│   └── session.py       # Database session management
├── services/
│   ├── embeddings.py    # Embedding generation
│   └── document_processor.py  # Document processing
└── api/
    └── ingestion.py     # Ingestion API routes
```

## Key Features
- **PDF & Text Ingestion**: Support multiple document formats
- **Automatic Metadata**: Auto-detect ticker and fiscal year from documents
- **Smart Chunking**: Split documents by sentence boundaries with overlap for context
- **Embeddings**: Generate 384-dimensional vectors using BAAI/bge-small-en-v1.5
- **Vector Storage**: Store embeddings in PostgreSQL with pgvector for similarity search
- **Async/Await**: Non-blocking database and I/O operations

## Configuration
Edit `.env` to customize:
- `DB_HOST`, `DB_PORT`, `DB_NAME`: Database connection
- `API_HOST`, `API_PORT`: FastAPI server settings
- `CHUNK_SIZE`, `CHUNK_OVERLAP`: Document chunking parameters

## Development

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Run Locally
```bash
uvicorn app.main:app --reload
```

### Reset Database
```bash
docker-compose down -v
docker-compose up --build
```

## Next Steps
1. ✅ Document ingestion API
2. ⏳ Vector similarity search endpoint
3. ⏳ MCP tool integration
4. ⏳ Agentic reasoning layer (Gemini API)
