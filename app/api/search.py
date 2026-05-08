from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Company, Document, DocumentChunk
from app.db.session import get_db
from app.services.embeddings import embed_texts

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/")
async def search(
    q: str = Query(..., description="Natural language search query"),
    ticker: Optional[str] = Query(None, description="Filter by company ticker"),
    year: Optional[int] = Query(None, description="Filter by fiscal year"),
    top_k: int = Query(5, ge=1, le=20, description="Number of results to return"),
    db: AsyncSession = Depends(get_db),
):
    embeddings = await embed_texts([q])
    query_vector = embeddings[0]

    stmt = (
        select(
            DocumentChunk.id,
            DocumentChunk.content,
            DocumentChunk.chunk_index,
            Document.year,
            Document.doc_type,
            Company.ticker,
            Company.name,
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
        stmt = stmt.where(Document.year == year)

    rows = (await db.execute(stmt)).all()

    return [
        {
            "chunk_id": row.id,
            "content": row.content,
            "chunk_index": row.chunk_index,
            "ticker": row.ticker,
            "company_name": row.name,
            "year": row.year,
            "doc_type": row.doc_type,
            "similarity": round(1 - row.distance, 4),
        }
        for row in rows
    ]
