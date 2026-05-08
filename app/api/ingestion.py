import asyncio
import os
import shutil

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Company, Document
from app.db.session import get_db, AsyncSessionLocal
from app.services import edgar_service
from app.services.document_processor import process_document

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

router = APIRouter(prefix="/ingest", tags=["ingestion"])

_progress: dict[int, list[str]] = {}

_CONTENT_TYPES = {
    ".pdf":  "application/pdf",
    ".html": "text/html",
    ".htm":  "text/html",
    ".txt":  "text/plain",
}

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

async def _get_or_create_company(ticker: str, db: AsyncSession) -> Company:
    result = await db.execute(select(Company).where(Company.ticker == ticker.upper()))
    company = result.scalar_one_or_none()
    if not company:
        company = Company(ticker=ticker.upper(), name=ticker.upper())
        db.add(company)
        await db.flush()
    return company


# ---------------------------------------------------------------------------
# Background task: download from EDGAR, save file, ingest chunks
# ---------------------------------------------------------------------------

async def _process_edgar_background(document_id: int, ticker: str, year: int) -> None:
    log = []
    _progress[document_id] = log

    def emit(msg: str):
        log.append(msg)

    async with AsyncSessionLocal() as db:
        try:
            text, meta = await edgar_service.download_and_save_10k(
                ticker, year, emit=emit
            )

            file_path = meta["file_path"]
            ext       = os.path.splitext(file_path)[1].upper()
            emit(f"File saved as {ext}.")

            # Persist file path on the document record
            document = await db.get(Document, document_id)
            document.file_path = file_path
            await db.commit()

            await process_document(document_id, text, db, emit)

        except Exception as exc:
            emit(f"Failed: {exc}")
            doc = await db.get(Document, document_id)
            if doc:
                doc.status = "failed"
                await db.commit()


# ---------------------------------------------------------------------------
# POST /download  — ticker + year triggers EDGAR fetch
# ---------------------------------------------------------------------------

class DownloadRequest(BaseModel):
    ticker: str
    year:   int


@router.post("/download")
async def download_and_ingest(
    payload: DownloadRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    ticker  = payload.ticker.upper()
    year    = payload.year
    company = await _get_or_create_company(ticker, db)

    # Prevent duplicate ingestion
    existing = await db.execute(
        select(Document)
        .where(Document.company_id == company.id)
        .where(Document.year == year)
        .where(Document.doc_type == "10-K")
        .where(Document.status.in_(["pending", "processing", "completed"]))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"A 10-K for {ticker} {year} already exists.",
        )

    document = Document(
        company_id=company.id,
        year=year,
        doc_type="10-K",
        status="pending",
        file_path=None,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    background_tasks.add_task(
        _process_edgar_background, document.id, ticker, year
    )

    return {"document_id": document.id, "status": "processing"}


# ---------------------------------------------------------------------------
# Manual PDF upload (kept for reference but disabled — use /download instead)
# ---------------------------------------------------------------------------

# @router.post("/pdf")
# async def ingest_pdf(...):  # commented out — agent auto-downloads from EDGAR


# ---------------------------------------------------------------------------
# Serve saved file for in-browser viewing
# ---------------------------------------------------------------------------

@router.get("/document/{document_id}")
async def serve_document(document_id: int, db: AsyncSession = Depends(get_db)):
    document = await db.get(Document, document_id)
    if not document or not document.file_path:
        raise HTTPException(status_code=404, detail="Document not found")
    if not os.path.exists(document.file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    ext        = os.path.splitext(document.file_path)[1].lower()
    media_type = _CONTENT_TYPES.get(ext, "application/octet-stream")
    return FileResponse(
        document.file_path,
        media_type=media_type,
        headers={"Content-Disposition": "inline"},
    )


@router.get("/document/{document_id}/download")
async def download_document(document_id: int, db: AsyncSession = Depends(get_db)):
    """
    Force-download as PDF.
    - If a PDF is already saved locally, serve it directly.
    - If only HTML is stored, fetch the PDF from EDGAR, save it, and serve it.
    - Falls back to serving whatever is on disk if no PDF exists on EDGAR.
    """
    result = await db.execute(
        select(Document, Company.ticker)
        .join(Company, Document.company_id == Company.id)
        .where(Document.id == document_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    document, ticker = row
    ext = os.path.splitext(document.file_path or "")[1].lower()

    # ── Already a PDF on disk ──────────────────────────────────────────────
    if ext == ".pdf" and document.file_path and os.path.exists(document.file_path):
        return FileResponse(
            document.file_path,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition":
                    f'attachment; filename="{os.path.basename(document.file_path)}"'
            },
        )

    # ── File is HTML / missing — try to fetch PDF from EDGAR ──────────────
    pdf_url = await edgar_service.find_10k_pdf_url(ticker, document.year)
    if pdf_url:
        try:
            pdf_bytes = await edgar_service.fetch_bytes(pdf_url)
            filename  = f"{ticker}_{document.year}_10K.pdf"
            abs_path  = os.path.abspath(os.path.join(DATA_DIR, filename))

            # Save locally and upgrade the stored file_path to PDF
            with open(abs_path, "wb") as fp:
                fp.write(pdf_bytes)
            document.file_path = abs_path
            await db.commit()

            return Response(
                content=pdf_bytes,
                media_type="application/octet-stream",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        except Exception:
            pass  # fall through to HTML fallback

    # ── Last resort: serve whatever is on disk ─────────────────────────────
    if document.file_path and os.path.exists(document.file_path):
        fn = os.path.basename(document.file_path)
        return FileResponse(
            document.file_path,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{fn}"'},
        )

    raise HTTPException(
        status_code=404,
        detail="PDF not available for this filing on EDGAR.",
    )


# ---------------------------------------------------------------------------
# Progress polling
# ---------------------------------------------------------------------------

@router.get("/progress/{document_id}")
async def get_progress(document_id: int):
    return {"steps": _progress.get(document_id, [])}


# ---------------------------------------------------------------------------
# Wipe everything
# ---------------------------------------------------------------------------

@router.delete("/all")
async def delete_all_documents(db: AsyncSession = Depends(get_db)):
    """Wipe every document, chunk, company, and file in data/."""
    await db.execute(
        text("TRUNCATE document_chunks, documents, companies RESTART IDENTITY CASCADE")
    )
    await db.commit()

    if os.path.exists(DATA_DIR):
        shutil.rmtree(DATA_DIR)
        os.makedirs(DATA_DIR, exist_ok=True)

    return {"message": "All ingested documents and files have been deleted."}


# ---------------------------------------------------------------------------
# Status list
# ---------------------------------------------------------------------------

@router.get("/status")
async def get_status(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Document, Company.ticker)
        .join(Company, Document.company_id == Company.id)
        .order_by(Document.created_at.desc())
        .limit(20)
    )
    return [
        {
            "id":         doc.id,
            "ticker":     ticker,
            "year":       doc.year,
            "doc_type":   doc.doc_type,
            "status":     doc.status,
            "has_file":   bool(doc.file_path and os.path.exists(doc.file_path)),
            "created_at": str(doc.created_at),
        }
        for doc, ticker in result.all()
    ]


# ---------------------------------------------------------------------------
# Text ingestion (unchanged)
# ---------------------------------------------------------------------------

class TextIngestRequest(BaseModel):
    content: str
    ticker:  str
    year:    int
    section: str = "general"


@router.post("/text")
async def ingest_text(
    payload: TextIngestRequest,
    db: AsyncSession = Depends(get_db),
):
    company  = await _get_or_create_company(payload.ticker, db)
    document = Document(
        company_id=company.id,
        year=payload.year,
        doc_type=payload.section,
        status="pending",
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    await process_document(document.id, payload.content, db)
    return {"document_id": document.id, "status": "completed"}
