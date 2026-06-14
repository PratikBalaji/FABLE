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
_LOCAL_MODEL = None  # fastembed TextEmbedding, lazily loaded
_DIM_CHECKED = False

# Local (no-API-key) embedder. bge-small-en-v1.5 → 384-dim, matches vector(384) schema.
_LOCAL_DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


def _get_local_model():
    """Lazy-load the fastembed model. ONNX, ~50MB, no torch, no API key."""
    global _LOCAL_MODEL
    if _LOCAL_MODEL is not None:
        return _LOCAL_MODEL
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:  # noqa: BLE001
        raise RuntimeError(
            "EMBEDDINGS_PROVIDER=local needs fastembed. Install it: pip install fastembed"
        ) from exc
    model_name = settings.embeddings_model
    # If the configured model isn't a fastembed model id, use the default 384-d one.
    if "/" not in model_name or model_name.startswith("text-embedding") or model_name.startswith("gemini"):
        model_name = _LOCAL_DEFAULT_MODEL
    _LOCAL_MODEL = TextEmbedding(model_name=model_name)
    log.info("local_embedder_loaded", model=model_name)
    return _LOCAL_MODEL


def _is_local() -> bool:
    return (settings.embeddings_provider or "").lower() == "local"


def _verify_dim(vec: list[float]) -> None:
    """Warn once if the live embedding width != EMBEDDINGS_DIMENSIONS. A mismatch means
    the model returns a different size than the Supabase vector(N) schema / FAISS expect
    (e.g. text-embedding-004 = 768 vs schema 384). Local FAISS tolerates it; pgvector won't."""
    global _DIM_CHECKED
    if _DIM_CHECKED:
        return
    _DIM_CHECKED = True
    actual = len(vec)
    if actual != settings.embeddings_dimensions:
        log.warning(
            "embeddings_dim_mismatch",
            model=settings.embeddings_model,
            actual=actual,
            expected=settings.embeddings_dimensions,
            hint="Use gemini-embedding-001 (supports 384) or set EMBEDDINGS_DIMENSIONS + update schema vector(N).",
        )


_GOOGLE_EMBED_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"


def _get_client() -> OpenAI:
    """Lazy-init the embeddings client. Provider order:
      EMBEDDINGS_PROVIDER=google (or GOOGLE_API_KEY set) → Gemini OpenAI-compat endpoint
      OPENAI_API_KEY                                      → canonical OpenAI endpoint
      else                                                → OPENROUTER_API_KEY + base url
    """
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    provider = (settings.embeddings_provider or "").lower()
    use_google = provider == "google" or bool(settings.google_api_key)

    if use_google:
        api_key = settings.google_api_key or settings.openrouter_api_key
        base_url = _GOOGLE_EMBED_BASE
    elif settings.openai_api_key:
        api_key, base_url = settings.openai_api_key, "https://api.openai.com/v1"
    else:
        api_key, base_url = settings.openrouter_api_key, settings.openrouter_base_url

    if not api_key:
        raise RuntimeError(
            "No embeddings credential. Set GOOGLE_API_KEY (Gemini), OPENAI_API_KEY, "
            "or OPENROUTER_API_KEY."
        )
    _CLIENT = OpenAI(api_key=api_key, base_url=base_url)
    return _CLIENT


# Models that support Matryoshka output truncation via the `dimensions` param.
# Keeping all providers at settings.embeddings_dimensions (384) means the Supabase
# vector(384) schema + FAISS + memory stay aligned regardless of provider.
#   OpenAI text-embedding-3-{small,large}: support dimensions
#   Google gemini-embedding-001:           supports output dimensionality (dimensions)
#   Google text-embedding-004:             FIXED 768 — must NOT send dimensions
_MRL_PREFIXES = ("text-embedding-3", "gemini-embedding")


def _embed_kwargs(model: str, input_) -> dict:
    """Build create() kwargs. Send `dimensions` only for models that support output
    truncation; fixed-dim models (e.g. text-embedding-004 @ 768) reject it."""
    kwargs: dict = {"model": model, "input": input_}
    if model.startswith(_MRL_PREFIXES):
        kwargs["dimensions"] = settings.embeddings_dimensions
    return kwargs


def embed_text(text: str) -> list[float]:
    """Single embedding. Used by knowledge_engine + memory_service + claims (P4c)."""
    if _is_local():
        vec = next(iter(_get_local_model().embed([text[:8000] if text else " "]))).tolist()
        _verify_dim(vec)
        return vec
    client = _get_client()
    resp = client.embeddings.create(**_embed_kwargs(settings.embeddings_model, text[:8000] if text else " "))
    vec = list(resp.data[0].embedding)
    _verify_dim(vec)
    return vec


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Batch embedding. Used by RAG pipeline chunk ingestion."""
    if not texts:
        return []
    safe = [(t[:8000] if t else " ") for t in texts]
    if _is_local():
        out = [v.tolist() for v in _get_local_model().embed(safe)]
        if out:
            _verify_dim(out[0])
        return out
    client = _get_client()
    resp = client.embeddings.create(**_embed_kwargs(settings.embeddings_model, safe))
    out = [list(d.embedding) for d in resp.data]
    if out:
        _verify_dim(out[0])
    return out
