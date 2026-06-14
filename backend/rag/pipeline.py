"""RAG pipeline: ingest → chunk → embed → store → retrieve."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import faiss
import numpy as np
import structlog

from ..core.config import settings
from ..core.embeddings import embed_batch as _api_embed_batch

log = structlog.get_logger()


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
        self._load()

    def _index_path(self) -> Path:
        return self.store_path / "index.faiss"

    def _chunks_path(self) -> Path:
        return self.store_path / "chunks.json"

    def _load(self) -> None:
        """Load a previously-persisted index + chunks/meta from disk (guarded)."""
        try:
            ip, cp = self._index_path(), self._chunks_path()
            if ip.exists() and cp.exists():
                self._index = faiss.read_index(str(ip))
                payload = json.loads(cp.read_text(encoding="utf-8"))
                self._chunks = payload.get("chunks", [])
                self._meta = payload.get("meta", [])
                log.info("vector_store_loaded", chunks=len(self._chunks))
        except Exception as exc:  # noqa: BLE001
            log.warning("vector_store_load_failed", err=str(exc)[:120])
            self._index, self._chunks, self._meta = None, [], []

    def _save(self) -> None:
        """Persist index + chunks/meta so seeded data survives across processes."""
        try:
            if self._index is not None:
                faiss.write_index(self._index, str(self._index_path()))
            self._chunks_path().write_text(
                json.dumps({"chunks": self._chunks, "meta": self._meta}),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("vector_store_save_failed", err=str(exc)[:120])

    def ingest(self, text: str, metadata: dict | None = None) -> int:
        """Chunk, embed, and add text to the store. Returns number of chunks added."""
        chunks = list(_chunk_text(text, settings.chunk_size, settings.chunk_overlap))
        if not chunks:
            return 0
        # P6b: OpenAI text-embedding-3-small via shared embeddings module.
        embeddings = np.array(_api_embed_batch(chunks), dtype=np.float32)
        dim = embeddings.shape[1]
        if self._index is None:
            self._index = faiss.IndexFlatL2(dim)
        self._index.add(embeddings)
        self._chunks.extend(chunks)
        self._meta.extend([metadata or {}] * len(chunks))
        self._save()  # persist after every ingest
        return len(chunks)

    def retrieve(
        self,
        query: str,
        top_k: int = settings.retrieval_top_k,
        identity_id: str | None = None,
    ) -> list[dict]:
        if self._index is None or not self._chunks:
            return []
        q_emb = np.array([_api_embed_batch([query])[0]], dtype=np.float32)
        # Over-fetch to leave room for per-identity filtering
        fetch_k = top_k * 4 if identity_id else top_k
        distances, indices = self._index.search(q_emb, min(fetch_k, len(self._chunks)))
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx >= len(self._chunks):
                continue
            meta = self._meta[idx]
            # F-024: filter to caller's identity when provided
            if identity_id and meta.get("identity_id") not in (identity_id, None):
                continue
            results.append({
                "chunk": self._chunks[idx],
                "score": float(1 - dist),
                "metadata": meta,
            })
            if len(results) >= top_k:
                break
        return results

    def format_context(
        self,
        query: str,
        top_k: int = settings.retrieval_top_k,
        identity_id: str | None = None,
    ) -> str:
        """Retrieve and format chunks as a prompt-ready context block."""
        hits = self.retrieve(query, top_k, identity_id=identity_id)
        if not hits:
            return ""
        lines = []
        for i, hit in enumerate(hits, 1):
            src = hit["metadata"].get("source", "unknown")
            lines.append(f"[{i}] (source: {src})\n{hit['chunk']}")
        return "\n\n".join(lines)


vector_store = VectorStore()
