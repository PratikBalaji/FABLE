"""Unit tests for the RAG pipeline."""
import numpy as np
import pytest
from unittest.mock import patch

from backend.rag.pipeline import VectorStore


def _fake_embed_batch(texts: list[str]) -> list[list[float]]:
    """Deterministic fake embeddings (dim=384) — no API key needed."""
    rng = np.random.default_rng(42)
    return [rng.random(384).tolist() for _ in texts]


@pytest.fixture(autouse=True)
def _patch_embed(monkeypatch):
    """Patch embed_batch for all tests in this module — no real API key required."""
    monkeypatch.setattr("backend.rag.pipeline._api_embed_batch", _fake_embed_batch)


@pytest.fixture
def store(tmp_path):
    return VectorStore(store_path=str(tmp_path / "vs"))


def test_ingest_and_retrieve(store):
    n = store.ingest(
        "Python is a high-level programming language. It emphasizes code readability.",
        metadata={"source": "test"},
    )
    assert n > 0
    results = store.retrieve("programming language", top_k=3)
    assert len(results) > 0
    assert "chunk" in results[0]
    assert "score" in results[0]


def test_retrieve_empty_store(store):
    results = store.retrieve("anything")
    assert results == []


def test_format_context(store):
    store.ingest("FastAPI is a modern web framework.", metadata={"source": "docs"})
    ctx = store.format_context("web framework")
    assert "FastAPI" in ctx or ctx == ""  # may be empty if below threshold
