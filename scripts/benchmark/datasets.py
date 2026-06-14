"""
GSM8K loader with seeded sampling. Downloads test.jsonl once to a local cache (no HF
`datasets` dependency); subsequent runs read from disk.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import httpx

from .grader import extract_gold

# Canonical GSM8K test split (OpenAI grade-school-math repo, main branch).
_GSM8K_URL = "https://raw.githubusercontent.com/openai/grade-school-math/master/grade_school_math/data/test.jsonl"
_CACHE = Path("data/benchmarks/gsm8k/test.jsonl")


def _ensure_cached() -> Path:
    if _CACHE.exists() and _CACHE.stat().st_size > 0:
        return _CACHE
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        resp = client.get(_GSM8K_URL)
        resp.raise_for_status()
        _CACHE.write_text(resp.text, encoding="utf-8")
    return _CACHE


def load_gsm8k(n: int, seed: int) -> list[dict]:
    """Return n GSM8K items sampled deterministically by `seed`.

    Each item: {"id": int, "question": str, "gold": str}. The id is the index in the full
    test split, so the same (n, seed) always yields the same questions.
    """
    path = _ensure_cached()
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            gold = extract_gold(obj.get("answer", ""))
            if gold is None:
                continue
            rows.append({"id": i, "question": obj["question"], "gold": gold})

    rng = random.Random(seed)
    if n >= len(rows):
        sample = rows
    else:
        sample = rng.sample(rows, n)
    sample.sort(key=lambda r: r["id"])  # stable presentation order
    return sample
