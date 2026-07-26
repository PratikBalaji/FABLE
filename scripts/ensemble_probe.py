"""
Ensemble consensus-reducer probe — small-N budget substitute for the full
Run-4 (ensemble=5, 60-case) programme entry.

Context: OpenRouter spend on Runs 1-3 came in far above the printed cost
estimate (real ~$5.8/run vs the script's own understated total), leaving too
little budget for a full 60-case ensemble=5 pass. This probe exercises the
same consensus-reducer code path (`_run_adversarial_ensemble` in
backend/core/adversarial_lifecycle.py) on 5 representative adversarial cases
(one per category) with ADVERSARIAL_ENSEMBLE_SIZE=2, so the mechanism is
demonstrated on live data without the full spend.

NOT part of the 60-case suite and NOT pooled with benchmark_v1 results —
written to its own file and reported under its own heading.

Usage (backend must be running with ADVERSARIAL_ENSEMBLE_SIZE=2):
    python scripts/ensemble_probe.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

BASE = "http://localhost:8000"
HEADERS = {"X-FABLE-Request": "1", "Content-Type": "application/json"}
TIMEOUT = 300.0
OUT_PATH = Path("data/benchmarks/results/ensemble_probe.json")

# One case per category — mid-range difficulty, not the C1/D1/D3 outliers
# already flagged as unstable across Runs 1-3.
PROBE_IDS = ["C2", "R2", "F2", "D2", "W2"]


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

    data = yaml.safe_load(open("benchmarks/benchmark_v1.yaml", encoding="utf-8"))
    shared = {q["id"]: q for q in data["shared_questions"]}

    results = []
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client() as client:
        try:
            h = client.get(f"{BASE}/health", timeout=10)
            print(f"Backend health: {h.json()}")
            cfg = client.get(f"{BASE}/config/runtime", timeout=10).json()
            print(f"Runtime config: {cfg}")
            if cfg.get("adversarial_ensemble_size", 1) < 2:
                print("FATAL: backend not running with ADVERSARIAL_ENSEMBLE_SIZE>=2")
                return
        except Exception as exc:  # noqa: BLE001
            print(f"FATAL: backend not reachable — {exc}")
            return

        for cid in PROBE_IDS:
            q = shared[cid]
            print(f"  [{cid}] {q['category']} ...", end="", flush=True)
            t0 = time.perf_counter()
            rec = {"id": cid, "category": q["category"]}
            try:
                resp = client.post(f"{BASE}/adversarial-run", json={"input": q["prompt"]},
                                    headers=HEADERS, timeout=TIMEOUT)
                elapsed = round(time.perf_counter() - t0, 1)
                resp.raise_for_status()
                d = resp.json()
                verdict = d.get("verdict") or {}
                meta = d.get("adversarial_meta") or {}
                ens = d.get("ensemble_meta") or {}
                rec.update({
                    "elapsed": elapsed,
                    "outcome": verdict.get("verdict", "UNKNOWN"),
                    "score": float(verdict.get("score", 0.0)),
                    "ensemble_meta": ens,
                })
                print(f" {rec['outcome']} | {rec['score']:.0%} | "
                      f"consensus_used={ens.get('consensus_used')} | "
                      f"group_size={ens.get('consensus_group_size')}/{ens.get('ensemble_size')} | "
                      f"{elapsed}s")
            except Exception as exc:  # noqa: BLE001
                rec.update({"elapsed": round(time.perf_counter() - t0, 1),
                            "outcome": "ERROR", "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
                print(f" ERROR: {rec['error']}")
            results.append(rec)
            # Flush after every case — same durability principle as benchmark_v1.py.
            OUT_PATH.write_text(json.dumps({
                "note": "5-case ensemble=2 probe, NOT part of the 60-case suite",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "ensemble_size": cfg.get("adversarial_ensemble_size"),
                "results": results,
            }, indent=2), encoding="utf-8")

    print(f"\nProbe results -> {OUT_PATH}")


if __name__ == "__main__":
    main()
