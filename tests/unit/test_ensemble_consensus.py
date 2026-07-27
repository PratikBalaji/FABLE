"""
Tests for the run-level self-consistency ensemble reducer (Phase 19, Track A).

`_run_adversarial_ensemble` fans out N independent debates and reduces them by majority
vote over the normalized final answer, using judge_score only as tie-break/fallback.
The debates themselves are stubbed — these tests cover the reducer, not the pipeline.
"""
from __future__ import annotations

import pytest

from backend.core import adversarial_lifecycle as al


def _candidate(answer: str, score: float) -> dict:
    return {"final_answer": answer, "adversarial_meta": {"judge_score": score}}


def _stub_debates(candidates: list[dict], monkeypatch):
    """Make each of the N spawned debates return the next canned candidate."""
    queue = list(candidates)

    async def _fake_run(input_text, domain, max_rounds, *, user_id=None,
                        session_id=None, router=None):
        return queue.pop(0)

    monkeypatch.setattr(al, "_run_adversarial_task", _fake_run)


async def _reduce(candidates: list[dict], monkeypatch) -> dict:
    _stub_debates(candidates, monkeypatch)
    return await al._run_adversarial_ensemble("q", "general", 1, len(candidates))


# ── majority vote ────────────────────────────────────────────────────────────

async def test_majority_wins_over_higher_scoring_minority(monkeypatch):
    """The whole point of self-consistency: 2 agreeing debates beat 1 better-scored outlier."""
    winner = await _reduce([
        _candidate("the answer is 42", 0.70),
        _candidate("the answer is 42", 0.72),
        _candidate("the answer is 99", 0.95),   # highest score, but alone
    ], monkeypatch)

    assert winner["final_answer"] == "the answer is 42"
    meta = winner["ensemble_meta"]
    assert meta["consensus_used"] is True
    assert meta["consensus_group_size"] == 2
    assert meta["num_distinct_answers"] == 2


async def test_grouping_ignores_whitespace_and_case(monkeypatch):
    winner = await _reduce([
        _candidate("The Answer Is 42", 0.60),
        _candidate("the   answer\nis 42", 0.61),
        _candidate("something else", 0.99),
    ], monkeypatch)

    assert winner["ensemble_meta"]["consensus_group_size"] == 2
    assert winner["ensemble_meta"]["num_distinct_answers"] == 2


async def test_tiebreak_within_winning_group_picks_best_score(monkeypatch):
    winner = await _reduce([
        _candidate("same answer", 0.60),
        _candidate("same answer", 0.88),
        _candidate("other", 0.90),
    ], monkeypatch)

    assert winner["adversarial_meta"]["judge_score"] == 0.88


# ── fallbacks ────────────────────────────────────────────────────────────────

async def test_all_distinct_falls_back_to_highest_score(monkeypatch):
    winner = await _reduce([
        _candidate("alpha", 0.50),
        _candidate("beta", 0.91),
        _candidate("gamma", 0.70),
    ], monkeypatch)

    assert winner["final_answer"] == "beta"
    meta = winner["ensemble_meta"]
    assert meta["consensus_used"] is False
    assert meta["consensus_group_size"] == 1
    assert meta["all_answers_empty"] is False


async def test_all_empty_answers_do_not_report_false_consensus(monkeypatch):
    """Blank answers all normalize to "" — they must not read as unanimous agreement."""
    winner = await _reduce([
        _candidate("", 0.40),
        _candidate("   ", 0.80),
        _candidate("\n", 0.55),
    ], monkeypatch)

    meta = winner["ensemble_meta"]
    assert meta["all_answers_empty"] is True
    assert meta["consensus_used"] is False
    assert meta["consensus_group_size"] == 1        # not 3
    assert winner["adversarial_meta"]["judge_score"] == 0.80  # degrades to best-of-N


# ── failure handling ─────────────────────────────────────────────────────────

async def test_partial_failure_reduces_over_survivors(monkeypatch):
    async def _flaky(input_text, domain, max_rounds, *, user_id=None,
                     session_id=None, router=None):
        if not hasattr(_flaky, "called"):
            _flaky.called = True
            raise RuntimeError("provider 503")
        return _candidate("survivor", 0.66)

    monkeypatch.setattr(al, "_run_adversarial_task", _flaky)
    winner = await al._run_adversarial_ensemble("q", "general", 1, 3)

    meta = winner["ensemble_meta"]
    assert meta["completed"] == 2
    assert meta["failed"] == 1
    assert winner["final_answer"] == "survivor"


async def test_all_debates_failing_reraises(monkeypatch):
    async def _boom(input_text, domain, max_rounds, *, user_id=None,
                    session_id=None, router=None):
        raise RuntimeError("provider down")

    monkeypatch.setattr(al, "_run_adversarial_task", _boom)
    with pytest.raises(RuntimeError, match="provider down"):
        await al._run_adversarial_ensemble("q", "general", 1, 3)
