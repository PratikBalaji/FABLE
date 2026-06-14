"""
Tests for Agentic RAG (CRAG-lite) + VectorStore persistence (Phase 18).

No network: embeddings, retrieval, and the LLM router are stubbed via monkeypatch.
"""
from __future__ import annotations

import numpy as np
import pytest

from backend.core.config import settings
from backend.rag.pipeline import VectorStore
from backend.rag import agentic


def _fake_embed_batch(texts):
    rng = np.random.default_rng(42)
    return [rng.random(384).tolist() for _ in texts]


@pytest.fixture(autouse=True)
def _patch_embed(monkeypatch):
    monkeypatch.setattr("backend.rag.pipeline._api_embed_batch", _fake_embed_batch)
    # default agentic config for tests
    monkeypatch.setattr(settings, "agentic_rag_enabled", True)
    monkeypatch.setattr(settings, "agentic_rag_max_hops", 2)
    monkeypatch.setattr(settings, "agentic_rag_top_k", 5)
    monkeypatch.setattr(settings, "agentic_rag_min_relevant", 2)
    monkeypatch.setattr(settings, "use_supabase", False)
    monkeypatch.setattr(settings, "secondary_model", "test/model")


# ── stubs ────────────────────────────────────────────────────────────────────

class StubResp:
    def __init__(self, content: str):
        self.content = content


class GraderRouter:
    """Returns canned grade verdicts (per call) and a rewrite string."""
    def __init__(self, grade_sequence):
        self._grades = list(grade_sequence)
        self.grade_calls = 0
        self.rewrite_calls = 0

    async def complete(self, system="", user="", role_hint="", force_model=None):
        if role_hint == "rag_grade":
            import json
            rel = self._grades[min(self.grade_calls, len(self._grades) - 1)]
            self.grade_calls += 1
            return StubResp(json.dumps({"relevant": rel}))
        if role_hint == "rag_rewrite":
            self.rewrite_calls += 1
            return StubResp("rewritten query")
        return StubResp("{}")


def _candidates(n: int):
    return [{"text": f"passage {i}", "source": "corpus", "score": 0.5} for i in range(n)]


# ── VectorStore persistence ─────────────────────────────────────────────────────

def test_vectorstore_persistence_roundtrip(tmp_path):
    path = str(tmp_path / "vs")
    s1 = VectorStore(store_path=path)
    s1.ingest("Python emphasizes readability and PEP 8 style.", metadata={"source": "pep8"})
    # New instance at same path must load the persisted chunks (survives process restart)
    s2 = VectorStore(store_path=path)
    assert len(s2._chunks) == len(s1._chunks) > 0
    hits = s2.retrieve("readability style", top_k=3)
    assert len(hits) > 0


# ── grading ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_grade_drops_irrelevant(monkeypatch):
    router = GraderRouter([[2]])  # only candidate #2 relevant
    kept = await agentic._grade("q", _candidates(3), router)
    assert len(kept) == 1
    assert kept[0]["text"] == "passage 1"  # 1-based index 2 → list idx 1


@pytest.mark.asyncio
async def test_grade_failsafe_keeps_all_on_error():
    class BoomRouter:
        async def complete(self, **kw):
            raise RuntimeError("grader down")
    cands = _candidates(3)
    kept = await agentic._grade("q", cands, BoomRouter())
    assert kept == cands  # fail-safe: never drop everything on grader error


# ── full CRAG-lite loop ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_weak_hop_triggers_rewrite_and_retry(monkeypatch):
    calls = {"n": 0}

    async def fake_retrieve_all(query, identity_id, user_id):
        calls["n"] += 1
        return _candidates(3)

    monkeypatch.setattr(agentic, "_retrieve_all", fake_retrieve_all)
    # hop1 grade weak ([]) → rewrite → hop2 grade strong ([1,2])
    router = GraderRouter([[], [1, 2]])
    out = await agentic.agentic_retrieve("q", router)
    assert calls["n"] == 2           # retrieved twice
    assert router.rewrite_calls == 1  # rewrote once
    assert "passage 0" in out and "passage 1" in out


@pytest.mark.asyncio
async def test_hop_cap_respected(monkeypatch):
    calls = {"n": 0}

    async def fake_retrieve_all(query, identity_id, user_id):
        calls["n"] += 1
        return _candidates(3)

    monkeypatch.setattr(agentic, "_retrieve_all", fake_retrieve_all)
    router = GraderRouter([[]])  # always weak
    out = await agentic.agentic_retrieve("q", router)
    assert calls["n"] == settings.agentic_rag_max_hops  # never exceeds cap
    assert out == ""  # nothing relevant


@pytest.mark.asyncio
async def test_disabled_returns_empty(monkeypatch):
    monkeypatch.setattr(settings, "agentic_rag_enabled", False)
    out = await agentic.agentic_retrieve("q", GraderRouter([[1]]))
    assert out == ""


@pytest.mark.asyncio
async def test_non_fatal_on_retrieve_error(monkeypatch):
    async def boom(query, identity_id, user_id):
        raise RuntimeError("store down")
    monkeypatch.setattr(agentic, "_retrieve_all", boom)
    out = await agentic.agentic_retrieve("q", GraderRouter([[1]]))
    assert out == ""  # never raises
