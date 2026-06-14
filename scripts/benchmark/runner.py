"""
Benchmark runner — executes Standard vs Adversarial (+ optional single-LLM floor) over a
GSM8K sample, in-process via run_task / run_adversarial_task with a throttled free-tier router.

Records per run: correct (grader vs gold), verdict, verdict_good, rubric_score, latency_s,
rounds (adv), pred, gold. Persists raw results to data/benchmarks/results/<ts>.json.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import structlog

from backend.core.config import settings
from backend.core.lifecycle import run_task
from backend.core.adversarial_lifecycle import run_adversarial_task

from .grader import is_correct, extract_answer
from .providers import ThrottledRouter

log = structlog.get_logger()

_SINGLE_SYSTEM = (
    "You are a careful math solver. Solve the problem step by step, then on the final line "
    "output ONLY the final numeric answer in the form: #### <number>"
)


async def _run_single(router: ThrottledRouter, question: str) -> str:
    resp = await router.complete(system=_SINGLE_SYSTEM, user=question, role_hint="single")
    return resp.content or ""


async def run_condition(
    condition: str,
    items: list[dict],
    router: ThrottledRouter,
    *,
    max_rounds: int | None = None,
) -> list[dict]:
    """Run one condition ('standard'|'adversarial'|'single') over all items."""
    # Benchmark hygiene: disable golden-cache recycling so every item is solved fresh.
    settings.golden_cache_enabled = False

    rows: list[dict] = []
    for k, item in enumerate(items, 1):
        q, gold = item["question"], item["gold"]
        t0 = time.perf_counter()
        rec = {"condition": condition, "id": item["id"], "gold": gold,
               "correct": False, "verdict": "ERROR", "verdict_good": False,
               "rubric_score": 0.0, "rounds": "", "latency_s": 0.0, "pred": None}
        try:
            if condition == "single":
                answer = await _run_single(router, q)
                rec["verdict"] = "N/A"
            elif condition == "standard":
                res = await run_task(q, domain="math", router=router)
                answer = res.get("final_answer", "")
                v = res.get("verdict", {}) or {}
                rec["verdict"] = v.get("verdict", "UNKNOWN")
                rec["verdict_good"] = rec["verdict"] == "PASS"
                rec["rubric_score"] = float(v.get("score", 0.0))
            elif condition == "adversarial":
                res = await run_adversarial_task(q, domain="math", max_rounds=max_rounds, router=router)
                answer = res.get("final_answer", "")
                adv = res.get("adversarial_meta", {}) or {}
                rec["verdict"] = adv.get("judge_verdict", "UNKNOWN")
                rec["verdict_good"] = rec["verdict"] == "ACCEPT"
                rec["rubric_score"] = float(adv.get("judge_score", 0.0))
                rec["rounds"] = f"{adv.get('rounds_completed', 0)}/{adv.get('max_rounds', 0)}"
            else:
                raise ValueError(f"unknown condition {condition}")

            rec["pred"] = extract_answer(answer)
            rec["correct"] = is_correct(answer, gold)
        except Exception as exc:  # noqa: BLE001
            rec["verdict"] = "ERROR"
            rec["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
            log.warning("bench_item_failed", condition=condition, id=item["id"], err=str(exc)[:120])
        rec["latency_s"] = round(time.perf_counter() - t0, 1)
        rows.append(rec)
        print(f"  [{condition}] {k}/{len(items)} id={item['id']} "
              f"{'OK' if rec['correct'] else 'X'} pred={rec['pred']} gold={gold} "
              f"{rec['verdict']} {rec['latency_s']}s")
    return rows


def persist(payload: dict, tag: str = "run") -> Path:
    out_dir = Path("data/benchmarks/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"{tag}-{ts}.json"
    import json
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
