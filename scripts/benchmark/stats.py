"""
Statistics for the benchmark — numpy + stdlib only (no scipy dependency).

  - mcnemar_exact: paired test on two methods' correctness over the same items.
  - bootstrap_ci:  percentile CI for a metric (e.g. accuracy) and for a paired difference.
  - cohen_kappa:   agreement between a binary signal (verdict good/bad) and truth (correct).
  - judge_validation: precision/recall/F1/kappa of verdict-vs-gold-correctness.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict

import numpy as np


def mcnemar_exact(a_correct: list[bool], b_correct: list[bool]) -> dict:
    """Exact McNemar test (binomial) on paired correctness.

    b01 = items A wrong, B right; b10 = A right, B wrong. Two-sided exact p-value over the
    discordant pairs under p=0.5. Returns counts + p-value.
    """
    assert len(a_correct) == len(b_correct)
    b01 = sum(1 for a, b in zip(a_correct, b_correct) if (not a) and b)
    b10 = sum(1 for a, b in zip(a_correct, b_correct) if a and (not b))
    n = b01 + b10
    if n == 0:
        return {"b01": 0, "b10": 0, "n_discordant": 0, "p_value": 1.0}
    k = min(b01, b10)
    # two-sided exact binomial: 2 * P(X <= k), X ~ Binom(n, 0.5), capped at 1.0
    tail = sum(math.comb(n, i) for i in range(k + 1)) * (0.5 ** n)
    p = min(1.0, 2.0 * tail)
    return {"b01": b01, "b10": b10, "n_discordant": n, "p_value": round(p, 6)}


def bootstrap_ci(values: list[float], iters: int = 10000, alpha: float = 0.05, seed: int = 0) -> dict:
    """Percentile bootstrap CI for the mean of `values` (e.g. per-item correctness 0/1)."""
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0}
    rng = np.random.default_rng(seed)
    means = arr[rng.integers(0, arr.size, size=(iters, arr.size))].mean(axis=1)
    lo, hi = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return {"mean": float(arr.mean()), "lo": float(lo), "hi": float(hi)}


def bootstrap_diff_ci(a: list[float], b: list[float], iters: int = 10000, alpha: float = 0.05, seed: int = 0) -> dict:
    """Paired bootstrap CI for mean(b) - mean(a) over matched items."""
    aa, bb = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    assert aa.size == bb.size and aa.size > 0
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, aa.size, size=(iters, aa.size))
    diffs = bb[idx].mean(axis=1) - aa[idx].mean(axis=1)
    lo, hi = np.percentile(diffs, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return {"diff": float(bb.mean() - aa.mean()), "lo": float(lo), "hi": float(hi)}


def cohen_kappa(y1: list[int], y2: list[int]) -> float:
    """Cohen's kappa for two binary label sequences."""
    a = np.asarray(y1)
    b = np.asarray(y2)
    n = a.size
    if n == 0:
        return 0.0
    po = float((a == b).mean())
    # expected agreement from marginals
    p1, p2 = a.mean(), b.mean()
    pe = p1 * p2 + (1 - p1) * (1 - p2)
    if pe >= 1.0:
        return 1.0 if po >= 1.0 else 0.0
    return float((po - pe) / (1 - pe))


@dataclass
class JudgeValidation:
    n: int
    precision: float
    recall: float
    f1: float
    kappa: float
    tp: int
    fp: int
    fn: int
    tn: int


def judge_validation(verdict_good: list[bool], correct: list[bool]) -> dict:
    """Validate the LLM verdict against objective correctness.

    verdict_good = verdict in {PASS, ACCEPT}; correct = grader vs gold.
    Treat 'verdict says good' as the prediction of 'answer is correct'.
    """
    vg = [bool(x) for x in verdict_good]
    co = [bool(x) for x in correct]
    tp = sum(1 for v, c in zip(vg, co) if v and c)
    fp = sum(1 for v, c in zip(vg, co) if v and not c)
    fn = sum(1 for v, c in zip(vg, co) if not v and c)
    tn = sum(1 for v, c in zip(vg, co) if not v and not c)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    kappa = cohen_kappa([int(x) for x in vg], [int(x) for x in co])
    return asdict(JudgeValidation(
        n=len(vg), precision=round(precision, 4), recall=round(recall, 4),
        f1=round(f1, 4), kappa=round(kappa, 4), tp=tp, fp=fp, fn=fn, tn=tn,
    ))
