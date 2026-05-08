import asyncio
from functools import partial

from sentence_transformers import SentenceTransformer

from app.core.config import get_settings

settings = get_settings()

_model: SentenceTransformer | None = None


def _load_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def _embed_sync(texts: list[str]) -> list[list[float]]:
    model = _load_model()
    return model.encode(texts, normalize_embeddings=True).tolist()


async def embed_texts(texts: list[str]) -> list[list[float]]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_embed_sync, texts))
