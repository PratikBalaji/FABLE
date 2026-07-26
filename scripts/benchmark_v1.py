"""
F.A.B.L.E. — 60 Preliminary Eval Test Cases benchmark runner.

Loads benchmarks/benchmark_v1.yaml, runs the 20 shared questions through
/run (standard) and /adversarial-run (adversarial), then the 10 Monte Carlo
prompts through /experiment/run.

DOES NOT re-run the 10 finished Phase-14 results — those are backfilled from
the YAML and included verbatim in the final report.

Usage (backend must be running on :8000):
    python scripts/benchmark_v1.py

Dry-run (validates yaml + scaffolds results file, NO API calls):
    python scripts/benchmark_v1.py --dry-run

Resume an interrupted run (skips cases already in the partial log):
    python scripts/benchmark_v1.py --resume

Cost estimate (pending 50 runs):
    ~$1.10–$2.50 at current OpenRouter pricing (see backend/core/cost.py):
    20 standard @ ~$0.003 + 20 adversarial @ ~$0.030 + 10 Monte Carlo @ ~$0.045.
    NOTE the printed aggregate UNDERSTATES the real bill — it prices a run's total
    token usage against the single `model_used` string the endpoint returns, but an
    adversarial run spans 6-12 calls across 4+ models, and Monte Carlo cost is not
    tracked at all. Budget from the OpenRouter dashboard, not from this output.

Output:
    - benchmarks/BENCHMARK_RESULTS.md  (updated with this run's results)
    - data/benchmarks/results/benchmark_v1_<timestamp>.json  (raw records)
    - data/benchmarks/results/benchmark_v1.partial.jsonl  (crash-safe running log)
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

# Add repo root to path so backend.core.cost is importable.
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import yaml
except ImportError:
    print("FATAL: PyYAML not installed. pip install pyyaml")
    sys.exit(1)

try:
    from backend.core.cost import price as _price_call
    COST_AVAILABLE = True
except ImportError:
    COST_AVAILABLE = False
    def _price_call(model: str, usage: dict) -> float:  # type: ignore[misc]
        return 0.0

BASE = "http://localhost:8000"
HEADERS = {"X-FABLE-Request": "1", "Content-Type": "application/json"}
TIMEOUT = 240.0
YAML_PATH = Path("benchmarks/benchmark_v1.yaml")
RESULTS_DIR = Path("data/benchmarks/results")
RESULTS_MD = Path("benchmarks/BENCHMARK_RESULTS.md")
# Crash-safe incremental log. Every completed case is appended here the moment it
# returns, so killing a 60-minute run never loses the cases already paid for.
PARTIAL_PATH = RESULTS_DIR / "benchmark_v1.partial.jsonl"
# Programme-level progress across the four orchestrator/ensemble configurations.
PROGRAMME_STATE = RESULTS_DIR / "programme_state.json"


def _append_partial(mode: str, rec: dict) -> None:
    """Append one completed case to the partial log. Never raises — a logging
    failure must not abort a run that is costing real money."""
    try:
        PARTIAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(PARTIAL_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"mode": mode, **rec}) + "\n")
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] could not append to partial log: {type(exc).__name__}: {exc}")


def _in_yaml_order(rows: list[dict], order: list[str]) -> list[dict]:
    """Restore YAML case order — a resumed run reloads recovered records first, so
    without this the report rows would be ordered by when they happened to run."""
    rank = {cid: i for i, cid in enumerate(order)}
    return sorted(rows, key=lambda r: rank.get(r.get("id"), len(rank)))


def _flush_results(
    data: dict,
    finished: list[dict],
    shared: list[dict],
    mc_cases: list[dict],
    std_results: list[dict],
    adv_results: list[dict],
    mc_results: list[dict],
    raw_path: Path,
    ts: str,
) -> None:
    """Write the consolidated JSON + markdown report reflecting everything completed
    so far. Called after EVERY case, not just at the end: a 50-case run takes ~45-60
    minutes and an interruption used to leave no human-readable record of work already
    paid for. Both files are small, so rewriting them per case is free next to the API
    calls. Never raises — a reporting failure must not abort a paid run."""
    try:
        std = _in_yaml_order(std_results, [q["id"] for q in shared])
        adv = _in_yaml_order(adv_results, [q["id"] for q in shared])
        mc = _in_yaml_order(mc_results, [m["id"] for m in mc_cases])

        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump({
                "meta": data["meta"],
                "timestamp": ts,
                "complete": len(std) + len(adv) + len(mc) == 50,
                "standard": std,
                "adversarial": adv,
                "montecarlo": mc,
                "finished": finished,
            }, f, indent=2)
        _write_results_md(finished, shared, mc_cases, std, adv, mc, ts)
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] could not flush results: {type(exc).__name__}: {exc}")


def _update_programme_state(raw_path: Path, counts: dict, cost: float) -> None:
    """Track progress across the whole 4-run programme (asyncio / langgraph /
    langchain / ensemble), keyed by the runtime config the backend reports. Lets work
    resume across sessions without needing to remember which runs already happened."""
    try:
        import urllib.request
        cfg = {}
        try:
            with urllib.request.urlopen(f"{BASE}/config/runtime", timeout=5) as r:
                cfg = json.loads(r.read().decode())
        except Exception:  # noqa: BLE001
            pass
        key = f"{cfg.get('orchestrator', 'unknown')}-ensemble{cfg.get('adversarial_ensemble_size', '?')}"

        state = {}
        if PROGRAMME_STATE.exists():
            try:
                state = json.loads(PROGRAMME_STATE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                state = {}
        runs = state.setdefault("runs", {})
        entry = runs.setdefault(key, {"started": datetime.now(timezone.utc).isoformat()})
        entry.update({
            "config": cfg,
            "results_file": str(raw_path),
            "completed": counts,
            "cost_usd_reported": round(cost, 4),
            "done": sum(counts.values()) == 50,
            "updated": datetime.now(timezone.utc).isoformat(),
        })
        state["note"] = (
            "cost_usd_reported is a LOWER BOUND (single-model pricing, MC untracked) — "
            "reconcile against the OpenRouter dashboard"
        )
        PROGRAMME_STATE.parent.mkdir(parents=True, exist_ok=True)
        PROGRAMME_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] could not update programme state: {type(exc).__name__}: {exc}")


def _load_partial() -> dict[str, list[dict]]:
    """Read the partial log back into {mode: [rec, ...]}. Skips corrupt lines
    (a run killed mid-write can leave one truncated trailing line)."""
    out: dict[str, list[dict]] = {"standard": [], "adversarial": [], "montecarlo": []}
    if not PARTIAL_PATH.exists():
        return out
    for line in PARTIAL_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            print(f"  [warn] skipping corrupt partial-log line: {line[:60]}...")
            continue
        mode = rec.pop("mode", None)
        if mode in out:
            out[mode].append(rec)
    return out


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_yaml() -> dict:
    with open(YAML_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Run helpers (reused from eval_runs.py pattern)
# ---------------------------------------------------------------------------

def run_standard(client: httpx.Client, prompt: str) -> dict:
    rec: dict = {"elapsed": 0.0, "outcome": "ERROR", "score": 0.0,
                 "rationale": "", "model": "", "usage": {}, "cost_usd": 0.0}
    t0 = time.perf_counter()
    try:
        resp = client.post(f"{BASE}/run", json={"input": prompt},
                           headers=HEADERS, timeout=TIMEOUT)
        rec["elapsed"] = round(time.perf_counter() - t0, 1)
        resp.raise_for_status()
        data = resp.json()
        verdict = data.get("verdict") or {}
        rec["outcome"] = verdict.get("verdict", "UNKNOWN")
        rec["score"] = float(verdict.get("score", 0.0))
        rec["rationale"] = (verdict.get("rationale", "") or "").replace("\n", " ")[:160]
        rec["model"] = data.get("model_used", "")
        rec["usage"] = data.get("usage", {}) or {}
        rec["cost_usd"] = _price_call(rec["model"], rec["usage"])
    except Exception as exc:  # noqa: BLE001
        rec["elapsed"] = round(time.perf_counter() - t0, 1)
        rec["rationale"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return rec


def run_adversarial(client: httpx.Client, prompt: str) -> dict:
    rec: dict = {"elapsed": 0.0, "outcome": "ERROR", "score": 0.0,
                 "rationale": "", "rounds": "", "forced_accept": False,
                 "model": "", "usage": {}, "cost_usd": 0.0}
    t0 = time.perf_counter()
    try:
        resp = client.post(f"{BASE}/adversarial-run", json={"input": prompt},
                           headers=HEADERS, timeout=TIMEOUT)
        rec["elapsed"] = round(time.perf_counter() - t0, 1)
        resp.raise_for_status()
        data = resp.json()
        verdict = data.get("verdict") or {}
        rec["outcome"] = verdict.get("verdict", "UNKNOWN")
        rec["score"] = float(verdict.get("score", 0.0))
        rec["rationale"] = (verdict.get("rationale", "") or "").replace("\n", " ")[:160]
        rec["model"] = data.get("model_used", "")
        adv = data.get("adversarial_meta") or {}
        if adv:
            rec["rounds"] = f"{adv.get('rounds_completed',0)}/{adv.get('max_rounds',0)}"
            # Phase 19 finding: the Judge's system prompt forces ACCEPT on the final
            # round regardless of quality. rounds==max_rounds + verdict==ACCEPT means
            # this run's ACCEPT is not an organic Judge decision (see AdversarialMeta
            # in backend/api/schemas.py for the same computation server-side).
            rec["forced_accept"] = bool(adv.get("forced_accept", False))
        rec["usage"] = data.get("usage", {}) or {}
        rec["cost_usd"] = _price_call(rec["model"], rec["usage"])
    except Exception as exc:  # noqa: BLE001
        rec["elapsed"] = round(time.perf_counter() - t0, 1)
        rec["rationale"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return rec


def run_montecarlo(client: httpx.Client, prompt: str, n_variants: int) -> dict:
    rec: dict = {"elapsed": 0.0, "outcome": "ERROR", "consensus": 0.0,
                 "divergence_pairs": 0, "models": [], "cost_usd": 0.0}
    t0 = time.perf_counter()
    try:
        resp = client.post(
            f"{BASE}/experiment/run",
            json={"input": prompt, "n_variants": n_variants},
            headers=HEADERS, timeout=TIMEOUT,
        )
        rec["elapsed"] = round(time.perf_counter() - t0, 1)
        resp.raise_for_status()
        data = resp.json()
        rec["outcome"] = "OK"
        rec["consensus"] = round(float(data.get("consensus_score", 0.0)), 3)
        rec["divergence_pairs"] = len(data.get("divergence_pairs", []))
        rec["models"] = data.get("models", [])
        rec["per_model_consensus"] = data.get("per_model_consensus", {})
        # cost: sum across variants × models (rough: no granular usage from MC endpoint)
        rec["cost_usd"] = 0.0  # MC endpoint doesn't return per-call usage yet
    except Exception as exc:  # noqa: BLE001
        rec["elapsed"] = round(time.perf_counter() - t0, 1)
        rec["rationale"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return rec


# ---------------------------------------------------------------------------
# Markdown table formatters
# ---------------------------------------------------------------------------

def _row_std(i: int, q: dict, r: dict) -> str:
    rat = r.get("rationale", "").replace("|", "\\|")[:100]
    cost = f"${r.get('cost_usd', 0.0):.4f}"
    return (f"| {i} | {q['id']} | {q['category']} | {r['outcome']} | "
            f"{r['score']:.0%} | {r['elapsed']}s | {cost} | {rat} |")


def _row_adv(i: int, q: dict, r: dict) -> str:
    rat = r.get("rationale", "").replace("|", "\\|")[:100]
    cost = f"${r.get('cost_usd', 0.0):.4f}"
    return (f"| {i} | {q['id']} | {q['category']} | {r['outcome']} | "
            f"{r['score']:.0%} | {r.get('rounds','—')} | {r['elapsed']}s | {cost} | {rat} |")


def _row_mc(i: int, mc: dict, r: dict) -> str:
    models = "+".join(m.split("/")[-1] for m in r.get("models", []))
    cost = f"${r.get('cost_usd', 0.0):.4f}"
    return (f"| {i} | {mc['id']} | {mc['category']} | {r.get('consensus', '—'):.3f} | "
            f"{r.get('divergence_pairs', '—')} | {r['elapsed']}s | {cost} | {models} |")


def _row_finished(run: dict) -> str:
    cost_note = "—"
    rnd = run.get("rounds") or "—"
    return (f"| {run['run_id']} | {run['category']} | {run['mode']} | "
            f"{run['verdict']} | {run['score']:.0%} | {rnd} | "
            f"{run['latency_s']}s | {cost_note} |")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(dry_run: bool = False, resume: bool = False) -> None:
    # Windows consoles (and any redirected stdout) default to cp1252 and raise
    # UnicodeEncodeError on the →/≈/— glyphs used below. Without this the script dies
    # AFTER all 50 paid runs complete but before the report is written. Same guard as
    # scripts/seed_rag.py.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

    data = load_yaml()
    shared = data["shared_questions"]
    mc_cases = data["montecarlo"]
    finished = data["finished_runs"]

    print(f"Loaded {len(shared)} shared questions, {len(mc_cases)} MC cases, "
          f"{len(finished)} finished runs.")
    print(f"Dry-run: {dry_run} | Resume: {resume}")

    if dry_run:
        print("\n[DRY RUN] YAML valid. Scaffolding results file...")
        _write_results_md(
            finished, shared, mc_cases,
            std_results=None, adv_results=None, mc_results=None,
            ts="DRY-RUN",
        )
        print(f"Scaffold written to {RESULTS_MD}")
        return

    # Resume: reload anything a previous (killed) invocation already paid for.
    if resume:
        prior = _load_partial()
        std_results = prior["standard"]
        adv_results = prior["adversarial"]
        mc_results = prior["montecarlo"]
        print(f"Resuming — recovered {len(std_results)} standard, "
              f"{len(adv_results)} adversarial, {len(mc_results)} MC from {PARTIAL_PATH}")
    else:
        if PARTIAL_PATH.exists():
            # Don't silently mix two runs' records together.
            stale = PARTIAL_PATH.with_suffix(f".jsonl.superseded-{int(time.time())}")
            PARTIAL_PATH.rename(stale)
            print(f"Existing partial log moved aside → {stale}")
        std_results, adv_results, mc_results = [], [], []

    done_std = {r.get("id") for r in std_results}
    done_adv = {r.get("id") for r in adv_results}
    done_mc = {r.get("id") for r in mc_results}

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RESULTS_DIR / f"benchmark_v1_{ts.replace(' ', '_').replace(':', '')}.json"

    def _checkpoint() -> None:
        """Persist everything completed so far — survives a kill at any point."""
        _flush_results(data, finished, shared, mc_cases,
                       std_results, adv_results, mc_results, raw_path, ts)
        _update_programme_state(
            raw_path,
            {"standard": len(std_results), "adversarial": len(adv_results),
             "montecarlo": len(mc_results)},
            sum(r.get("cost_usd", 0.0) for r in std_results)
            + sum(r.get("cost_usd", 0.0) for r in adv_results),
        )

    with httpx.Client() as client:
        try:
            h = client.get(f"{BASE}/health", timeout=10)
            print(f"Backend health: {h.json()}")
        except Exception as exc:  # noqa: BLE001
            print(f"FATAL: backend not reachable at {BASE} — {exc}")
            return

        # Standard runs (20)
        print("\n=== STANDARD MODE (20 runs) ===")
        for q in shared:
            if q["id"] in done_std:
                print(f"  [{q['id']}] {q['category']} ... SKIP (already recorded)")
                continue
            print(f"  [{q['id']}] {q['category']} ...", end="", flush=True)
            r = run_standard(client, q["prompt"])
            r["id"] = q["id"]
            std_results.append(r)
            _append_partial("standard", r)
            _checkpoint()
            print(f" {r['outcome']} | {r['score']:.0%} | {r['elapsed']}s | ${r['cost_usd']:.4f}")

        # Adversarial runs (20)
        print("\n=== ADVERSARIAL MODE (20 runs) ===")
        for q in shared:
            if q["id"] in done_adv:
                print(f"  [{q['id']}] {q['category']} ... SKIP (already recorded)")
                continue
            print(f"  [{q['id']}] {q['category']} ...", end="", flush=True)
            r = run_adversarial(client, q["prompt"])
            r["id"] = q["id"]
            adv_results.append(r)
            _append_partial("adversarial", r)
            _checkpoint()
            print(f" {r['outcome']} | {r['score']:.0%} | {r.get('rounds','—')} | "
                  f"{r['elapsed']}s | ${r['cost_usd']:.4f}")

        # Monte Carlo runs (10)
        print("\n=== MONTE CARLO MODE (10 runs) ===")
        for mc in mc_cases:
            if mc["id"] in done_mc:
                print(f"  [{mc['id']}] {mc['category']} ... SKIP (already recorded)")
                continue
            # Resolve prompt from shared_questions
            sid = mc["shared_id"]
            q = next((x for x in shared if x["id"] == sid), None)
            prompt = q["prompt"] if q else mc.get("prompt", "")
            print(f"  [{mc['id']}] {mc['category']} ({mc['n_variants']} variants)...",
                  end="", flush=True)
            r = run_montecarlo(client, prompt, mc["n_variants"])
            r["id"] = mc["id"]
            mc_results.append(r)
            _append_partial("montecarlo", r)
            _checkpoint()
            print(f" consensus={r.get('consensus','?'):.3f} | {r['elapsed']}s")

    # Final flush (the loops already checkpoint after every case).
    _checkpoint()
    std_results = _in_yaml_order(std_results, [q["id"] for q in shared])
    adv_results = _in_yaml_order(adv_results, [q["id"] for q in shared])
    mc_results = _in_yaml_order(mc_results, [m["id"] for m in mc_cases])
    print(f"\nRaw results → {raw_path}")

    # Print aggregates
    def _agg(rows: list[dict]) -> tuple[float, float, int, int]:
        ok = [r for r in rows if r.get("outcome") not in ("ERROR", None)]
        mean_score = statistics.mean([r["score"] for r in ok]) if ok else 0.0
        mean_time = statistics.mean([r["elapsed"] for r in rows]) if rows else 0.0
        passes = sum(1 for r in rows if r.get("outcome") in ("PASS","ACCEPT","OK"))
        return mean_score, mean_time, passes, len(rows)

    s_score, s_time, s_pass, s_n = _agg(std_results)
    a_score, a_time, a_pass, a_n = _agg(adv_results)
    total_cost = (sum(r.get("cost_usd",0.0) for r in std_results)
                + sum(r.get("cost_usd",0.0) for r in adv_results))

    print("\n" + "="*60)
    print(f"Standard    : mean {s_score:.0%} | {s_time:.1f}s | pass {s_pass}/{s_n}")
    print(f"Adversarial : mean {a_score:.0%} | {a_time:.1f}s | pass {a_pass}/{a_n}")
    print(f"Total cost  : ${total_cost:.4f} (excl. MC — no per-call usage returned)")

    print(f"Results markdown → {RESULTS_MD}")
    print(f"Programme state  → {PROGRAMME_STATE}")


def _write_results_md(
    finished: list[dict],
    shared: list[dict],
    mc_cases: list[dict],
    std_results: list[dict] | None,
    adv_results: list[dict] | None,
    mc_results: list[dict] | None,
    ts: str,
) -> None:
    RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# F.A.B.L.E. — 60 Preliminary Eval Test Cases: Results",
        "",
        f"**Suite version:** v1  |  **Generated:** {ts}",
        "",
        "| Dimension | Value |",
        "|-----------|-------|",
        "| Total cases | 60 |",
        "| Finished (Phase-14) | 10 |",
        "| Pending standard | 20 |",
        "| Pending adversarial | 20 |",
        "| Pending Monte Carlo | 10 |",
        "",
        "> **Dataset feasibility:** With n=20 prompts per mode, confidence intervals",
        "> are wide (~±15% at 95% CI via bootstrap). McNemar tests require paired",
        "> samples (identical prompts in both modes ✓). Results should be read as",
        "> directional signal, not statistically powered conclusions.",
        "> See `scripts/benchmark/stats.py` for bootstrap CI and McNemar utilities.",
        "",
        "---",
        "",
        "## Finished Runs — Phase 14 (10 runs, 2026-06-13) — LEGACY PROMPT SET",
        "",
        "> **Not comparable to the tables above.** These ran against the *original* v1",
        "> prompts, which were rewritten on 2026-07-26 to be discriminative (interacting",
        "> constraints, planted false premises, corpus-grounded docqa). Different prompts",
        "> means different difficulty, so these scores must never be pooled with, or",
        "> trended against, the current suite. Retained only as a record of the",
        "> Phase-14 latency debugging batch.",
        "",
        "| Run | Category | Mode | Verdict | Score | Rounds | Latency | Cost |",
        "|-----|----------|------|---------|-------|--------|---------|------|",
    ]
    for run in finished:
        lines.append(_row_finished(run))

    lines += [
        "",
        "**Standard aggregate (Phase-14, legacy prompts):** mean score 82% · mean time 32.8s · pass rate 4/5",
        "**Adversarial aggregate (Phase-14, legacy prompts):** mean score 80% · mean time 72.3s · accept rate 5/5",
        "",
        "---",
        "",
        "## Standard Mode — 20 Runs",
        "",
        "| # | ID | Category | Verdict | Score | Latency | Cost | Rationale |",
        "|---|-----|----------|---------|-------|---------|------|-----------|",
    ]
    if std_results:
        for i, (q, r) in enumerate(zip(shared, std_results), 1):
            lines.append(_row_std(i, q, r))
    else:
        for i, q in enumerate(shared, 1):
            lines.append(f"| {i} | {q['id']} | {q['category']} | PENDING | — | — | — | — |")

    lines += [
        "",
        "---",
        "",
        "## Adversarial Mode — 20 Runs",
        "",
        "| # | ID | Category | Verdict | Score | Rounds | Latency | Cost | Rationale |",
        "|---|-----|----------|---------|-------|--------|---------|------|-----------|",
    ]
    if adv_results:
        for i, (q, r) in enumerate(zip(shared, adv_results), 1):
            lines.append(_row_adv(i, q, r))
    else:
        for i, q in enumerate(shared, 1):
            lines.append(f"| {i} | {q['id']} | {q['category']} | PENDING | — | — | — | — | — |")

    lines += [
        "",
        "---",
        "",
        "## Monte Carlo Mode — 10 Runs",
        "",
        "| # | ID | Category | Consensus | Div. Pairs | Latency | Cost | Models |",
        "|---|-----|----------|-----------|------------|---------|------|--------|",
    ]
    if mc_results:
        for i, (mc, r) in enumerate(zip(mc_cases, mc_results), 1):
            lines.append(_row_mc(i, mc, r))
    else:
        for i, mc in enumerate(mc_cases, 1):
            lines.append(f"| {i} | {mc['id']} | {mc['category']} | PENDING | — | — | — | — |")

    lines += [
        "",
        "---",
        "",
        "## Token Cost Analysis",
        "",
        "Cost computed via `backend/core/cost.py` using per-model USD/1M token rates.",
        "",
        "| Mode | Est. input tokens/run | Est. output tokens/run | Est. cost/run |",
        "|------|-----------------------|------------------------|---------------|",
        "| Standard    | ~2,000 | ~500 | ~$0.003 |",
        "| Adversarial | ~8,000 | ~2,000 | ~$0.030 |",
        "| Monte Carlo | ~12,000 | ~3,000 | ~$0.045 |",
        "",
        "> Estimates based on Phase-14 run logs. Actual cost logged per run by the runner.",
        "",
        "---",
        "",
        "*Generated by `scripts/benchmark_v1.py`. "
        "Source: `benchmarks/benchmark_v1.yaml`. "
        "Raw JSON in `data/benchmarks/results/`.*",
    ]

    RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FABLE 60-case benchmark runner")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate yaml and write placeholder markdown; no API calls")
    parser.add_argument("--resume", action="store_true",
                        help="Recover completed cases from the partial log and skip them")
    args = parser.parse_args()
    main(dry_run=args.dry_run, resume=args.resume)
