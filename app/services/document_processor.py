import re

import pdfplumber
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Document, DocumentChunk
from app.services.embeddings import embed_texts

settings = get_settings()


def extract_text_from_pdf(file_path: str) -> str:
    with pdfplumber.open(file_path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def chunk_text(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    chunks, current, length = [], [], 0

    for sentence in sentences:
        slen = len(sentence)
        if length + slen > settings.chunk_size and current:
            chunks.append(" ".join(current))
            # slide the window back by overlap amount
            while current and length > settings.chunk_overlap:
                removed = current.pop(0)
                length -= len(removed) + 1
        current.append(sentence)
        length += slen + 1

    if current:
        chunks.append(" ".join(current))

    return chunks


async def process_document(document_id: int, text: str, db: AsyncSession) -> None:
    document = await db.get(Document, document_id)
    document.status = "processing"
    await db.commit()

    try:
        chunks = chunk_text(text)
        embeddings = await embed_texts(chunks)

        for idx, (content, embedding) in enumerate(zip(chunks, embeddings)):
            db.add(DocumentChunk(
                document_id=document_id,
                content=content,
                chunk_index=idx,
                embedding=embedding,
            ))

        document.status = "completed"
        await db.commit()
    except Exception:
        document.status = "failed"
        await db.commit()
        raise
