"""
GSM8K benchmark CLI — Standard vs Adversarial A/B on a free LLM provider (Groq by default).

Examples:
    # smoke test (3 questions, 1 seed)
    GROQ_API_KEY=... python -m scripts.benchmark.run_benchmark --n 3 --seeds 1

    # pilot (run this before scaling)
    GROQ_API_KEY=... python -m scripts.benchmark.run_benchmark --n 20 --seeds 1

    # full run
    GROQ_API_KEY=... python -m scripts.benchmark.run_benchmark --n 100 --seeds 2

Outputs: raw JSON in data/benchmarks/results/, LaTeX tables in paper/tables/, a figure in
paper/figures/, and a markdown summary appended to RESEARCH_LOG.md. Embeddings run locally
(set EMBEDDINGS_PROVIDER=local); cost on Groq's free tier is $0.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from .datasets import load_gsm8k
from .providers import build_router, DEFAULT_MODELS
from .runner import run_condition, persist
from .report import compute_summary, write_all, markdown_summary


async def _main_async(args) -> None:
    conditions = ["standard", "adversarial"]
    if not args.no_single:
        conditions.insert(0, "single")

    router = build_router(args.provider, model=args.model, rpm=args.rpm, hetero=False)
    model = args.model or DEFAULT_MODELS[args.provider]

    # Gather all items across seeds (each seed = a distinct sample).
    by_cond: dict[str, list[dict]] = {c: [] for c in conditions}
    for seed in range(args.seeds):
        items = load_gsm8k(args.n, seed=seed)
        print(f"\n=== seed {seed}: {len(items)} GSM8K items ===")
        for cond in conditions:
            rows = await run_condition(cond, items, router,
                                       max_rounds=2 if cond == "adversarial" else None)
            for r in rows:
                r["seed"] = seed
            by_cond[cond].extend(rows)

    meta = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "provider": args.provider, "model": model, "n": args.n, "seeds": args.seeds,
    }
    summary = compute_summary(by_cond)
    persist({"meta": meta, "summary": summary, "raw": by_cond}, tag="gsm8k")

    artifacts = write_all(summary)
    with open("RESEARCH_LOG.md", "a", encoding="utf-8") as f:
        f.write(markdown_summary(summary, meta))

    print("\n" + "=" * 60)
    for c in conditions:
        s = summary["conditions"][c]
        print(f"{c:12s} acc {100*s['accuracy']:.1f}% "
              f"[{100*s['ci_lo']:.1f}, {100*s['ci_hi']:.1f}] | {s['mean_latency_s']}s")
    p = summary.get("pairwise", {}).get("std_vs_adv")
    if p:
        print(f"McNemar p={p['p_value']} | adv-std diff {p['diff']:+.3f} "
              f"[{p['lo']:+.3f},{p['hi']:+.3f}]")
    print(f"Tables: {artifacts['tables']}\nFigure: {artifacts['figure']}")
    print("Markdown summary appended to RESEARCH_LOG.md (Phase 19).")


def main() -> None:
    ap = argparse.ArgumentParser(description="GSM8K Standard-vs-Adversarial benchmark")
    ap.add_argument("--n", type=int, default=100, help="questions per seed")
    ap.add_argument("--seeds", type=int, default=2, help="number of seeds")
    ap.add_argument("--provider", default="groq", choices=["groq", "hf", "openrouter"])
    ap.add_argument("--model", default=None, help="override the single model id")
    ap.add_argument("--rpm", type=int, default=25, help="requests-per-minute throttle")
    ap.add_argument("--no-single", action="store_true", help="skip the single-LLM floor")
    args = ap.parse_args()
    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
