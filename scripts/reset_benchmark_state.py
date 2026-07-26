"""
Reset adaptive state to a declared-clean baseline between benchmark runs.

Why this exists (Phase 19 methodology):
  The knowledge engine, ELM router, and golden-case cache all persist under
  data/knowledge/ and all feed back into subsequent runs:

    - golden_cases.jsonl — lifecycle.py checks this BEFORE the pipeline and, on a
      >=GOLDEN_HIT_THRESHOLD (0.93) match, returns a recycled answer with
      model_used="golden_cache", skipping the pipeline entirely. Runs scoring >=0.75
      are promoted into it. Since the programme runs standard mode twice (asyncio and
      langchain) over the SAME 20 prompts, the second pass would hit at similarity ~1.0
      and recycle all 20 — making the orchestrator comparison meaningless.
    - runs.jsonl / graph.json — feed knowledge_engine.get_best_model_for(), so run N
      influences which model handles run N+1.
    - elm_router.npz — the trained meta-scorer, same feedback concern.

  Each orchestrator run must therefore start from the same empty state, and the
  benchmark programme should additionally run with GOLDEN_CACHE_ENABLED=false.

Usage:
    python scripts/reset_benchmark_state.py            # reset, refusing if no archive
    python scripts/reset_benchmark_state.py --force    # reset even without an archive
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

KNOWLEDGE_DIR = Path("data/knowledge")
PARTIAL_LOG = Path("data/benchmarks/results/benchmark_v1.partial.jsonl")


def main(force: bool = False, keep_partial: bool = False) -> int:
    archives = sorted(Path("data").glob("knowledge.archive-*"))
    if not archives and not force:
        print(
            "REFUSING: no data/knowledge.archive-* found.\n"
            "  data/knowledge/ holds real prior runs. Archive it first:\n"
            "    cp -r data/knowledge data/knowledge.archive-$(date +%F)\n"
            "  ...or re-run with --force if you are certain it is disposable."
        )
        return 1
    if archives:
        print(f"Archive present: {archives[-1]}")

    if KNOWLEDGE_DIR.exists():
        removed = sorted(p.name for p in KNOWLEDGE_DIR.iterdir() if p.is_file())
        shutil.rmtree(KNOWLEDGE_DIR)
        print(f"Cleared {KNOWLEDGE_DIR}/ ({', '.join(removed) if removed else 'was empty'})")
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

    # The partial log is per-run; carrying it into the next orchestrator would make
    # --resume skip cases that this run has not actually executed.
    if PARTIAL_LOG.exists() and not keep_partial:
        PARTIAL_LOG.unlink()
        print(f"Removed stale {PARTIAL_LOG}")

    print(
        "\nState is clean. Remember to run the benchmark with:\n"
        "    GOLDEN_CACHE_ENABLED=false\n"
        "so no run promotes cases that would short-circuit a later one."
    )
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Reset adaptive state between benchmark runs")
    ap.add_argument("--force", action="store_true",
                    help="Clear data/knowledge/ even if no archive exists")
    ap.add_argument("--keep-partial", action="store_true",
                    help="Keep the benchmark partial log (use when resuming the same run)")
    args = ap.parse_args()
    sys.exit(main(force=args.force, keep_partial=args.keep_partial))
