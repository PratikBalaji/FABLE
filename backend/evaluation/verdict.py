"""Derive a PASS / WARN / FAIL verdict from rubric scores (standard mode)."""
from __future__ import annotations

_PASS_THRESHOLD = 0.75
_WARN_THRESHOLD = 0.50
_WEAK_THRESHOLD = 0.60


def derive_verdict(scores: dict[str, float]) -> dict:
    """
    Map rubric scores → verdict dict.

    Returns::
        {"verdict": "PASS"|"WARN"|"FAIL"|"UNKNOWN", "score": float, "rationale": str}
    """
    if not scores:
        return {"verdict": "UNKNOWN", "score": 0.0, "rationale": "No evaluation scores available."}

    avg = sum(scores.values()) / len(scores)

    if avg >= _PASS_THRESHOLD:
        verdict = "PASS"
    elif avg >= _WARN_THRESHOLD:
        verdict = "WARN"
    else:
        verdict = "FAIL"

    sorted_dims = sorted(scores.items(), key=lambda x: x[1])
    weak = [d for d, s in sorted_dims if s < _WEAK_THRESHOLD]

    if weak:
        rationale = (
            f"Overall score {avg:.0%}. "
            f"Weakest area{'s' if len(weak) > 1 else ''}: {', '.join(weak[:3])}."
        )
    else:
        top_dim = sorted_dims[-1][0] if sorted_dims else "all dimensions"
        rationale = (
            f"Strong performance: {avg:.0%} across all rubric dimensions. "
            f"Best on {top_dim}."
        )

    return {"verdict": verdict, "score": round(avg, 2), "rationale": rationale}
