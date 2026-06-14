"""
GSM8K answer extraction + exact-match grading. Pure-Python, deterministic, no network.

GSM8K gold answers are integers (occasionally with commas, e.g. "1,000"). Model outputs
end with the answer in varied formats ("The answer is 42.", "#### 42", "$42.00"). We
extract the final numeric token and compare numerically.
"""
from __future__ import annotations

import re

# Matches signed integers/decimals with optional thousands separators and currency.
_NUM = re.compile(r"-?\$?\d[\d,]*(?:\.\d+)?")


def _normalize_num(s: str) -> str | None:
    """Strip currency/commas, drop a trailing '.0', return canonical numeric string."""
    s = s.replace("$", "").replace(",", "").strip()
    try:
        f = float(s)
    except ValueError:
        return None
    # Represent integers without a decimal point so "42" == "42.0"
    if f == int(f):
        return str(int(f))
    return repr(f)


def extract_gold(solution: str) -> str | None:
    """Gold answer is the token after '####' in a GSM8K solution."""
    if "####" in solution:
        tail = solution.split("####")[-1]
        m = _NUM.search(tail)
        if m:
            return _normalize_num(m.group(0))
    return None


def extract_answer(text: str) -> str | None:
    """Extract a model's final numeric answer.

    Priority: an explicit '#### N' or 'answer is N' marker, else the LAST number in the text
    (GSM8K convention — the final figure is the answer)."""
    if not text:
        return None
    # 1. explicit markers
    for pat in (r"####\s*(-?\$?\d[\d,]*(?:\.\d+)?)",
                r"(?:final answer|the answer is|answer:)\s*(-?\$?\d[\d,]*(?:\.\d+)?)"):
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return _normalize_num(m.group(1))
    # 2. fallback: last number anywhere
    nums = _NUM.findall(text)
    if nums:
        return _normalize_num(nums[-1])
    return None


def is_correct(pred_text: str, gold: str) -> bool:
    """True iff the model's extracted answer matches the (normalized) gold answer."""
    pred = extract_answer(pred_text)
    if pred is None or gold is None:
        return False
    gold_norm = _normalize_num(gold) if not gold.lstrip("-").isdigit() else gold
    return pred == (gold_norm or gold)
