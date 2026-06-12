"""
Embedding engine (P6b).

Replaces the previous local `sentence-transformers` MiniLM with OpenAI's
`text-embedding-3-small` (dim 384). Same output shape (`list[float]` of length
`embeddings_dimensions`), same L2-normalized vectors, so the existing
`vector(384)` Supabase schema and FAISS index logic stay untouched.

Why the swap: removing the ~500MB torch + transformers + sentence-transformers
bundle was a hard requirement to fit the Cloud Run free tier image (<300MB).
Embedding cost at research-project volume is ~$0.003/mo (text-embedding-3-small
is $0.02 per 1M tokens).
"""
from __future__ import annotations

import structlog
from openai import OpenAI

from .config import settings

log = structlog.get_logger()

_CLIENT: OpenAI | None = None


def _get_client() -> OpenAI:
    """Lazy-init the OpenAI client. Tries direct OPENAI_API_KEY first (canonical
    embeddings endpoint), falls back to OPENROUTER for chat-only setups.
    """
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    api_key = settings.openai_api_key or settings.openrouter_api_key
    base_url = (
        "https://api.openai.com/v1"
        if settings.openai_api_key
        else settings.openrouter_base_url
    )
    if not api_key:
        raise RuntimeError(
            "No embeddings credential. Set OPENAI_API_KEY (preferred for embeddings) "
            "or OPENROUTER_API_KEY."
        )
    _CLIENT = OpenAI(api_key=api_key, base_url=base_url)
    return _CLIENT


def embed_text(text: str) -> list[float]:
    """Single embedding. Used by knowledge_engine + memory_service + claims (P4c)."""
    client = _get_client()
    resp = client.embeddings.create(
        model=settings.embeddings_model,
        input=text[:8000] if text else " ",
        dimensions=settings.embeddings_dimensions,
    )
    return list(resp.data[0].embedding)


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Batch embedding. Used by RAG pipeline chunk ingestion."""
    if not texts:
        return []
    client = _get_client()
    safe = [(t[:8000] if t else " ") for t in texts]
    resp = client.embeddings.create(
        model=settings.embeddings_model,
        input=safe,
        dimensions=settings.embeddings_dimensions,
    )
    return [list(d.embedding) for d in resp.data]
