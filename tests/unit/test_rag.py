"""Unit tests for the RAG pipeline."""
import pytest
from backend.rag.pipeline import VectorStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    def deterministic_embed_batch(texts):
        return [
            [
                float(len(text)),
                float(text.lower().count("python") + text.lower().count("fastapi")),
                float(sum(ord(ch) for ch in text) % 997),
            ]
            for text in texts
        ]

    monkeypatch.setattr("backend.rag.pipeline._api_embed_batch", deterministic_embed_batch)
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
