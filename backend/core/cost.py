"""Token cost pricing for F.A.B.L.E. runs.

Prices sourced from provider docs (2026-06). All figures in USD per 1M tokens.
Used by the benchmark runner, dashboard API, and OTel spans.

Usage::

    from backend.core.cost import price, aggregate_costs

    usage = {"input": 1200, "output": 340}
    usd = price("anthropic/claude-sonnet-4-5", usage)
    # -> 0.004260
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

# ---------------------------------------------------------------------------
# Price table — USD / 1 000 000 tokens
# Keys match OpenRouter model IDs used in model_router.py + config.py.
# ---------------------------------------------------------------------------
_IN = "input"   # prompt tokens
_OUT = "output"  # completion tokens

MODEL_PRICES: dict[str, dict[str, float]] = {
    # Claude via Anthropic (OpenRouter pass-through)
    "anthropic/claude-sonnet-4-5":    {_IN: 3.00,  _OUT: 15.00},
    "anthropic/claude-3.5-haiku":     {_IN: 0.80,  _OUT:  4.00},
    "anthropic/claude-3-haiku":       {_IN: 0.25,  _OUT:  1.25},
    "anthropic/claude-3-opus":        {_IN: 15.00, _OUT: 75.00},
    # OpenAI via OpenRouter
    "openai/gpt-4o":                  {_IN: 2.50,  _OUT: 10.00},
    "openai/gpt-4o-mini":             {_IN: 0.15,  _OUT:  0.60},
    "openai/gpt-4-turbo":             {_IN: 10.00, _OUT: 30.00},
    # Meta via OpenRouter
    "meta-llama/llama-3.1-70b-instruct": {_IN: 0.52, _OUT: 0.75},
    "meta-llama/llama-3.1-8b-instruct":  {_IN: 0.06, _OUT: 0.06},
    # Google via OpenRouter
    "google/gemini-2.0-flash":        {_IN: 0.10,  _OUT:  0.40},
    "google/gemini-pro":              {_IN: 0.50,  _OUT:  1.50},
}

# Fallback when exact model string not found — use cheapest reasonable estimate.
_FALLBACK_PRICES: dict[str, float] = {_IN: 0.50, _OUT: 1.50}


def _lookup(model: str) -> dict[str, float]:
    """Return price row for model. Tries prefix-match if exact miss."""
    if model in MODEL_PRICES:
        return MODEL_PRICES[model]
    # Try prefix (handles versioned suffixes like "-20250101")
    for key in MODEL_PRICES:
        if model.startswith(key) or key.startswith(model):
            return MODEL_PRICES[key]
    return _FALLBACK_PRICES


def price(model: str, usage: dict[str, int]) -> float:
    """Return USD cost for one model call.

    Args:
        model: OpenRouter model ID string.
        usage: dict with ``"input"`` and ``"output"`` token counts
               (matches ``ModelResponse.usage`` shape).

    Returns:
        Cost in USD (float, ≥ 0.0).
    """
    row = _lookup(model)
    inp = usage.get("input", 0) or 0
    out = usage.get("output", 0) or 0
    return (inp * row[_IN] + out * row[_OUT]) / 1_000_000


@dataclass
class CostRecord:
    model: str
    usage: dict[str, int]
    usd: float = field(init=False)

    def __post_init__(self) -> None:
        self.usd = price(self.model, self.usage)


@dataclass
class AggregatedCosts:
    total_usd: float
    per_model: dict[str, float]          # model -> total USD
    per_run: list[float]                 # one entry per record
    total_input_tokens: int
    total_output_tokens: int


def aggregate_costs(records: Sequence[dict]) -> AggregatedCosts:
    """Aggregate cost across multiple run records.

    Each record must have ``"model"`` (str) and ``"usage"`` (dict with
    ``"input"``/``"output"`` keys) — the shape stored in
    ``AgentMessage.metadata``.
    """
    per_model: dict[str, float] = {}
    per_run: list[float] = []
    total_input = 0
    total_output = 0

    for rec in records:
        model = rec.get("model", "unknown")
        usage = rec.get("usage", {}) or {}
        usd = price(model, usage)
        per_run.append(usd)
        per_model[model] = per_model.get(model, 0.0) + usd
        total_input += usage.get("input", 0) or 0
        total_output += usage.get("output", 0) or 0

    return AggregatedCosts(
        total_usd=sum(per_run),
        per_model=per_model,
        per_run=per_run,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
    )


# ---------------------------------------------------------------------------
# Self-test (python -m backend.core.cost)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        ("anthropic/claude-sonnet-4-5", {"input": 1000, "output": 500}, 0.01050),
        ("openai/gpt-4o-mini",          {"input": 5000, "output": 1000}, 0.00135),
        ("anthropic/claude-3.5-haiku",  {"input": 2000, "output": 800},  0.00480),
    ]
    ok = True
    for model, usage, expected in tests:
        got = price(model, usage)
        diff = abs(got - expected)
        status = "PASS" if diff < 0.0001 else "FAIL"
        if status == "FAIL":
            ok = False
        print(f"[{status}] {model}: ${got:.5f} (expected ${expected:.5f})")

    agg = aggregate_costs([
        {"model": "anthropic/claude-sonnet-4-5", "usage": {"input": 1000, "output": 500}},
        {"model": "openai/gpt-4o-mini",           "usage": {"input": 5000, "output": 1000}},
    ])
    print(f"\nAggregate: total=${agg.total_usd:.5f}, models={agg.per_model}")
    print("All tests passed." if ok else "FAILURES detected.")
