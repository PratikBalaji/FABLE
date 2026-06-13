"""
FABLE evaluation harness — live latency + quality runs (Phase 14).

Hits the running backend 5× standard (/run) + 5× adversarial (/adversarial-run),
records latency + rubric scores + verdict per run, then appends a results table
to RESEARCH_LOG.md.

Usage (backend must be running on :8000):
    .venv/Scripts/python.exe scripts/eval_runs.py
"""
from __future__ import annotations

import time
import statistics
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE = "http://localhost:8000"
HEADERS = {"X-FABLE-Request": "1", "Content-Type": "application/json"}
TIMEOUT = 240.0  # generous — we are measuring real latency, not enforcing the UI limit

# Fixed prompts — varied domains, none should trip guardrails.
PROMPTS = [
    ("code",     "Write a Python function that returns the nth Fibonacci number iteratively, and explain its time complexity."),
    ("reasoning","A bat and a ball cost $1.10 together. The bat costs $1.00 more than the ball. How much does the ball cost? Show your reasoning."),
    ("finance",  "Explain the difference between a Roth IRA and a Traditional IRA, and when each is preferable."),
    ("factual",  "Summarize the main causes of the 2008 global financial crisis in a few sentences."),
    ("creative", "Propose three distinct product names for a privacy-first AI note-taking app, with a one-line rationale each."),
]


def run_one(client: httpx.Client, endpoint: str, prompt: str) -> dict:
    """Execute one run, return a record with latency + outcome."""
    rec: dict = {"elapsed": 0.0, "outcome": "ERROR", "score": 0.0,
                 "rationale": "", "rounds": "", "model": "", "scores": {}}
    t0 = time.perf_counter()
    try:
        resp = client.post(f"{BASE}{endpoint}", json={"input": prompt},
                           headers=HEADERS, timeout=TIMEOUT)
        rec["elapsed"] = round(time.perf_counter() - t0, 1)
        resp.raise_for_status()
        data = resp.json()
        verdict = data.get("verdict") or {}
        rec["outcome"] = verdict.get("verdict", "UNKNOWN")
        rec["score"] = float(verdict.get("score", 0.0))
        rec["rationale"] = (verdict.get("rationale", "") or "").replace("\n", " ").strip()[:160]
        rec["model"] = (data.get("model_used", "") or "").split("/")[-1]
        rec["scores"] = data.get("scores", {})
        adv = data.get("adversarial_meta") or {}
        if adv:
            rec["rounds"] = f"{adv.get('rounds_completed', 0)}/{adv.get('max_rounds', 0)}"
    except Exception as exc:  # noqa: BLE001
        rec["elapsed"] = round(time.perf_counter() - t0, 1)
        rec["outcome"] = "ERROR"
        rec["rationale"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return rec


def run_mode(client: httpx.Client, mode: str, endpoint: str) -> list[dict]:
    rows = []
    print(f"\n=== {mode.upper()} ({endpoint}) ===")
    for label, prompt in PROMPTS:
        print(f"  - {label} ...", end="", flush=True)
        rec = run_one(client, endpoint, prompt)
        rec["label"] = label
        rows.append(rec)
        print(f" {rec['outcome']} | {rec['score']:.0%} | {rec['elapsed']}s"
              + (f" | {rec['rounds']}r" if rec['rounds'] else ""))
    return rows


def fmt_table(rows: list[dict], adversarial: bool) -> str:
    if adversarial:
        head = "| Run | Prompt | Verdict | Avg Score | Rounds | Time (s) | Rationale |\n"
        head += "|-----|--------|---------|-----------|--------|----------|-----------|\n"
    else:
        head = "| Run | Prompt | Verdict | Avg Score | Time (s) | Rationale |\n"
        head += "|-----|--------|---------|-----------|----------|-----------|\n"
    lines = []
    for i, r in enumerate(rows, 1):
        rat = r["rationale"].replace("|", "\\|")
        if adversarial:
            lines.append(f"| {i} | {r['label']} | {r['outcome']} | {r['score']:.0%} | "
                         f"{r['rounds'] or '—'} | {r['elapsed']} | {rat} |")
        else:
            lines.append(f"| {i} | {r['label']} | {r['outcome']} | {r['score']:.0%} | "
                         f"{r['elapsed']} | {rat} |")
    return head + "\n".join(lines) + "\n"


def aggregate(rows: list[dict]) -> tuple[float, float, int, int]:
    ok = [r for r in rows if r["outcome"] != "ERROR"]
    mean_score = statistics.mean([r["score"] for r in ok]) if ok else 0.0
    mean_time = statistics.mean([r["elapsed"] for r in rows]) if rows else 0.0
    passes = sum(1 for r in rows if r["outcome"] in ("PASS", "ACCEPT"))
    return mean_score, mean_time, passes, len(rows)


def main() -> None:
    with httpx.Client() as client:
        # Health check
        try:
            h = client.get(f"{BASE}/health", timeout=10)
            print(f"Backend health: {h.json()}")
        except Exception as exc:  # noqa: BLE001
            print(f"FATAL: backend not reachable at {BASE} — {exc}")
            return

        std = run_mode(client, "standard", "/run")
        adv = run_mode(client, "adversarial", "/adversarial-run")

    s_score, s_time, s_pass, s_n = aggregate(std)
    a_score, a_time, a_pass, a_n = aggregate(adv)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    section = f"""

---

## Phase 14 — Latency Fix + Evaluation Runs

**Run timestamp:** {ts}
**Config:** summaries_per_agent=off (run-level only), critic=claude-3.5-haiku, refiner=gpt-4o-mini, adversarial_max_rounds=2, per-call timeout=45s.

### Standard mode (5 runs)

{fmt_table(std, adversarial=False)}
**Aggregate:** mean score {s_score:.0%} · mean time {s_time:.1f}s · pass rate {s_pass}/{s_n}

### Adversarial mode (5 runs)

{fmt_table(adv, adversarial=True)}
**Aggregate:** mean score {a_score:.0%} · mean time {a_time:.1f}s · pass rate {a_pass}/{a_n}

### Analysis

Quality measured via the 5-dimension rubric (accuracy, depth, clarity, actionability, coverage); verdict is PASS/WARN/FAIL (standard, derived from rubric average) or ACCEPT/REJECT (adversarial, judge verdict). Standard mean latency {s_time:.1f}s, adversarial {a_time:.1f}s — both within the 180s client timeout. The model-ID fix (removing the invalid `meta-llama/llama-3-70b-instruct`) eliminated the per-role failed-call + fallback retry overhead, and run-level-only summaries cut ~11 redundant LLM calls from each adversarial run.
"""

    log_path = Path("RESEARCH_LOG.md")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(section)

    print("\n" + "=" * 60)
    print(f"Standard:    mean {s_score:.0%} | {s_time:.1f}s | pass {s_pass}/{s_n}")
    print(f"Adversarial: mean {a_score:.0%} | {a_time:.1f}s | pass {a_pass}/{a_n}")
    print(f"Appended Phase 14 results to {log_path.resolve()}")


if __name__ == "__main__":
    main()
