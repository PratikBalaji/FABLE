"""GET /benchmark/summary  +  GET /traces — dashboard read endpoints (Phase 15)."""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter

log = structlog.get_logger()
router = APIRouter()

_RESULTS_GLOB = "data/benchmarks/results/benchmark_v1_*.json"
_TRACES_FILE  = Path("data/traces/fable_traces.jsonl")
_YAML_PATH    = Path("benchmarks/benchmark_v1.yaml")


def _latest_results() -> dict[str, Any] | None:
    files = sorted(Path(".").glob(_RESULTS_GLOB))
    if not files:
        return None
    try:
        with open(files[-1], encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _finished_phase14() -> dict:
    """Phase-14 static fallback when no live results file exists yet."""
    return {
        "total": 60, "done": 10, "pending": 50,
        "modes": {
            "standard": {
                "mean_score": 0.82, "mean_latency": 32.8, "pass_rate": 0.80,
            },
            "adversarial": {
                "mean_score": 0.80, "mean_latency": 72.3, "pass_rate": 1.00,
            },
            "montecarlo": {"mean_consensus": 0.0},
        },
        "cost": {"total_usd": 0.0, "per_mode": {}},
    }


@router.get("/benchmark/summary")
def benchmark_summary() -> dict:
    """Aggregate summary of the 60-case benchmark for the dashboard."""
    raw = _latest_results()
    if raw is None:
        return _finished_phase14()

    try:
        from ..core.cost import price as _price
        cost_avail = True
    except ImportError:
        cost_avail = False

    def _agg_mode(records: list[dict]) -> dict:
        ok = [r for r in records if r.get("outcome") not in ("ERROR", None)]
        scores   = [r.get("score", 0.0) or 0.0 for r in ok]
        latencies = [r.get("elapsed", 0.0) or 0.0 for r in records]
        passes   = sum(1 for r in records if r.get("outcome") in ("PASS", "ACCEPT"))
        return {
            "mean_score":   round(statistics.mean(scores), 3) if scores else 0.0,
            "mean_latency": round(statistics.mean(latencies), 1) if latencies else 0.0,
            "pass_rate":    round(passes / len(records), 3) if records else 0.0,
        }

    std = raw.get("standard", [])
    adv = raw.get("adversarial", [])
    mc  = raw.get("montecarlo", [])

    mc_consensus = [r.get("consensus", 0.0) for r in mc if r.get("outcome") == "OK"]

    total_cost = 0.0
    per_mode: dict[str, float] = {}
    if cost_avail:
        for mode_key, records in [("standard", std), ("adversarial", adv)]:
            mode_cost = sum(
                _price(r.get("model", ""), r.get("usage", {}) or {})
                for r in records
            )
            per_mode[mode_key] = round(mode_cost, 4)
            total_cost += mode_cost

    done = 10 + len([r for r in std if r.get("outcome") not in ("ERROR", None, "PENDING")]) \
              + len([r for r in adv if r.get("outcome") not in ("ERROR", None, "PENDING")]) \
              + len([r for r in mc  if r.get("outcome") == "OK"])

    return {
        "total": 60,
        "done": done,
        "pending": max(0, 60 - done),
        "modes": {
            "standard":    _agg_mode(std) if std else _finished_phase14()["modes"]["standard"],
            "adversarial": _agg_mode(adv) if adv else _finished_phase14()["modes"]["adversarial"],
            "montecarlo":  {
                "mean_consensus": round(statistics.mean(mc_consensus), 3) if mc_consensus else 0.0,
            },
        },
        "cost": {"total_usd": round(total_cost, 4), "per_mode": per_mode},
    }


@router.get("/traces")
def get_traces(limit: int = 50) -> list[dict]:
    """Return recent OTel span records from the local trace file."""
    if not _TRACES_FILE.exists():
        return []
    try:
        lines = _TRACES_FILE.read_text(encoding="utf-8").splitlines()
        spans = [json.loads(l) for l in lines if l.strip()]
        return spans[-limit:]
    except Exception as exc:
        log.warning("traces_read_error", error=str(exc))
        return []
