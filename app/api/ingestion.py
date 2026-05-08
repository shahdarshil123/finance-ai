import asyncio
import os
from functools import partial

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Company, Document
from app.db.session import get_db, AsyncSessionLocal
from app.services.document_processor import extract_text_from_pdf, process_document

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

router = APIRouter(prefix="/ingest", tags=["ingestion"])

# In-memory progress log keyed by document_id
_progress: dict[int, list[str]] = {}


async def _get_or_create_company(ticker: str, db: AsyncSession) -> Company:
    result = await db.execute(select(Company).where(Company.ticker == ticker.upper()))
    company = result.scalar_one_or_none()
    if not company:
        company = Company(ticker=ticker.upper(), name=ticker.upper())
        db.add(company)
        await db.flush()
    return company


async def _process_pdf_background(document_id: int, file_path: str) -> None:
    log = []
    _progress[document_id] = log

    def emit(msg: str):
        log.append(msg)

    loop = asyncio.get_running_loop()
    async with AsyncSessionLocal() as db:
        emit("Extracting text from PDF…")
        text = await loop.run_in_executor(None, partial(extract_text_from_pdf, file_path))
        emit(f"Extracted {len(text):,} characters.")
        await process_document(document_id, text, db, emit)


@router.post("/pdf")
async def ingest_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    ticker: str = Form(...),
    year: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    company = await _get_or_create_company(ticker, db)

    file_path = os.path.join(UPLOAD_DIR, f"{ticker.upper()}_{year}_{file.filename}")
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(await file.read())

    document = Document(
        company_id=company.id,
        year=year,
        doc_type="10-K",
        status="pending",
        file_path=file_path,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    background_tasks.add_task(_process_pdf_background, document.id, file_path)

    return {"document_id": document.id, "status": "processing"}


@router.get("/progress/{document_id}")
async def get_progress(document_id: int):
    return {"steps": _progress.get(document_id, [])}


class TextIngestRequest(BaseModel):
    content: str
    ticker: str
    year: int
    section: str = "general"


@router.post("/text")
async def ingest_text(
    payload: TextIngestRequest,
    db: AsyncSession = Depends(get_db),
):
    company = await _get_or_create_company(payload.ticker, db)

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


@router.get("/status")
async def get_status(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Document, Company.ticker)
        .join(Company, Document.company_id == Company.id)
        .order_by(Document.created_at.desc())
        .limit(20)
    )
    rows = result.all()
    return [
        {
            "id": doc.id,
            "ticker": ticker,
            "year": doc.year,
            "doc_type": doc.doc_type,
            "status": doc.status,
            "created_at": str(doc.created_at),
        }
        for doc, ticker in rows
    ]
