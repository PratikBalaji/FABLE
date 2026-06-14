"""Tests for the GSM8K benchmark harness — grading, stats, sampling. No network, no spend."""
from __future__ import annotations

import json

import pytest

from scripts.benchmark.grader import extract_answer, extract_gold, is_correct
from scripts.benchmark.stats import (
    mcnemar_exact, bootstrap_ci, bootstrap_diff_ci, cohen_kappa, judge_validation,
)


# ── grader ─────────────────────────────────────────────────────────────────────

def test_extract_gold():
    assert extract_gold("Janet has ... so the total is 18.\n#### 18") == "18"
    assert extract_gold("... #### 1,000") == "1000"


@pytest.mark.parametrize("text,expected", [
    ("The answer is 42.", "42"),
    ("#### 7", "7"),
    ("blah blah final answer: 3.5", "3.5"),
    ("It costs $1,200 total", "1200"),
    ("step 1 = 5, step 2 = 9, so 14 apples", "14"),  # last number
    ("no numbers here", None),
])
def test_extract_answer(text, expected):
    assert extract_answer(text) == expected


def test_is_correct():
    assert is_correct("the answer is 42", "42")
    assert is_correct("total: $42.00", "42")     # normalization
    assert not is_correct("the answer is 41", "42")
    assert not is_correct("", "42")


# ── stats ──────────────────────────────────────────────────────────────────────

def test_mcnemar_symmetry_high_p():
    # equal discordance → not significant
    a = [True, False, True, False]
    b = [False, True, False, True]
    r = mcnemar_exact(a, b)
    assert r["b01"] == 2 and r["b10"] == 2
    assert r["p_value"] > 0.5


def test_mcnemar_all_one_direction_low_p():
    # B fixes 8 that A got wrong, A never beats B → significant
    a = [False] * 8 + [True, True]
    b = [True] * 8 + [True, True]
    r = mcnemar_exact(a, b)
    assert r["b01"] == 8 and r["b10"] == 0
    assert r["p_value"] < 0.05


def test_bootstrap_ci_bounds():
    ci = bootstrap_ci([1.0] * 8 + [0.0] * 2, seed=1)
    assert 0.0 <= ci["lo"] <= ci["mean"] <= ci["hi"] <= 1.0
    assert abs(ci["mean"] - 0.8) < 1e-9


def test_bootstrap_diff_ci():
    d = bootstrap_diff_ci([0.0] * 10, [1.0] * 10, seed=1)
    assert abs(d["diff"] - 1.0) < 1e-9


def test_cohen_kappa_perfect_and_chance():
    assert cohen_kappa([1, 0, 1, 0], [1, 0, 1, 0]) == pytest.approx(1.0)
    # independent-ish → near 0
    assert abs(cohen_kappa([1, 1, 0, 0], [1, 0, 1, 0])) < 0.6


def test_judge_validation():
    # verdict_good vs correct: 2 TP, 1 FP, 1 FN, 1 TN
    vg = [True, True, False, True, False]
    co = [True, False, True, True, False]
    j = judge_validation(vg, co)
    assert j["tp"] == 2 and j["fp"] == 1 and j["fn"] == 1 and j["tn"] == 1
    assert j["precision"] == pytest.approx(2 / 3, abs=1e-3)
    assert j["recall"] == pytest.approx(2 / 3, abs=1e-3)


# ── report summary wiring ───────────────────────────────────────────────────────

def test_compute_summary_pairs_by_id():
    from scripts.benchmark.report import compute_summary
    by_cond = {
        "standard":    [{"id": 1, "correct": False, "verdict_good": False, "latency_s": 10},
                        {"id": 2, "correct": True,  "verdict_good": True,  "latency_s": 10}],
        "adversarial": [{"id": 1, "correct": True,  "verdict_good": True,  "latency_s": 20},
                        {"id": 2, "correct": True,  "verdict_good": True,  "latency_s": 20}],
    }
    s = compute_summary(by_cond)
    assert s["conditions"]["standard"]["accuracy"] == 0.5
    assert s["conditions"]["adversarial"]["accuracy"] == 1.0
    assert s["pairwise"]["std_vs_adv"]["n_paired"] == 2
    assert "standard" in s["judge"] and "adversarial" in s["judge"]
