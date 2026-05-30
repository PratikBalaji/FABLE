"""RAG pipeline: ingest → chunk → embed → store → retrieve."""
from __future__ import annotations

from pathlib import Path
from typing import Iterator, cast

from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

from ..core.config import settings

_EMBED_MODEL: SentenceTransformer | None = None


def _get_embed_model() -> SentenceTransformer:
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        _EMBED_MODEL = SentenceTransformer(settings.embedding_model)
    return _EMBED_MODEL


def _chunk_text(text: str, size: int, overlap: int) -> Iterator[str]:
    tokens = text.split()
    start = 0
    while start < len(tokens):
        yield " ".join(tokens[start : start + size])
        start += size - overlap


class VectorStore:
    """FAISS-backed vector store for RAG retrieval."""

    def __init__(self, store_path: str = settings.vector_store_path) -> None:
        self.store_path = Path(store_path)
        self.store_path.mkdir(parents=True, exist_ok=True)
        self._index: faiss.IndexFlatL2 | None = None
        self._chunks: list[str] = []
        self._meta: list[dict] = []

    def _index_path(self) -> Path:
        return self.store_path / "index.faiss"

    def _chunks_path(self) -> Path:
        return self.store_path / "chunks.npy"

    def ingest(self, text: str, metadata: dict | None = None) -> int:
        """Chunk, embed, and add text to the store. Returns number of chunks added."""
        model = _get_embed_model()
        chunks = list(_chunk_text(text, settings.chunk_size, settings.chunk_overlap))
        if not chunks:
            return 0
        embeddings = cast(np.ndarray, model.encode(chunks, convert_to_numpy=True, normalize_embeddings=True))
        dim = embeddings.shape[1]
        if self._index is None:
            self._index = faiss.IndexFlatL2(dim)
        self._index.add(embeddings.astype(np.float32))
        self._chunks.extend(chunks)
        self._meta.extend([metadata or {}] * len(chunks))
        return len(chunks)

    def retrieve(self, query: str, top_k: int = settings.retrieval_top_k) -> list[dict]:
        if self._index is None or not self._chunks:
            return []
        model = _get_embed_model()
        q_emb = cast(np.ndarray, model.encode([query], convert_to_numpy=True, normalize_embeddings=True))
        distances, indices = self._index.search(q_emb.astype(np.float32), top_k)
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < len(self._chunks):
                results.append({
                    "chunk": self._chunks[idx],
                    "score": float(1 - dist),
                    "metadata": self._meta[idx],
                })
        return results

    def format_context(self, query: str, top_k: int = settings.retrieval_top_k) -> str:
        """Retrieve and format chunks as a prompt-ready context block."""
        hits = self.retrieve(query, top_k)
        if not hits:
            return ""
        lines = []
        for i, hit in enumerate(hits, 1):
            src = hit["metadata"].get("source", "unknown")
            lines.append(f"[{i}] (source: {src})\n{hit['chunk']}")
        return "\n\n".join(lines)


vector_store = VectorStore()
