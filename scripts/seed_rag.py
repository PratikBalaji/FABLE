"""
Seed the FABLE RAG store with curated, sanitized, license-clean corpora.

Usage:
    python scripts/seed_rag.py                   # all domains
    python scripts/seed_rag.py --domain code_review
    python scripts/seed_rag.py --domain finance stem writing
    python scripts/seed_rag.py --dry-run          # preview sources, no ingest

Domains: general_reasoning, stem, code_review, finance, writing, medical_light, legal_light

All text passes through:
  1. HTML / wiki-markup strip (seed_corpus.py)
  2. PII redact (core.pii — preserves "no raw PII in store" invariant)
  3. Content-hash dedup (skips chunks already in store)
  4. Chunk + embed + ingest (rag.ingestion)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Add repo root to sys.path so `backend.*` imports work when run from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.rag.seed_corpus import ALL_DOMAINS, SEED_SOURCES, iter_seed_texts
from backend.core.pii import redact


async def _ingest_text(text: str, source: str, domain: str, dry_run: bool) -> int:
    """PII-redact → ingest; returns chunks_added (0 on dry-run or error)."""
    if dry_run:
        return 0

    # PII redact (no router — regex layer only; LLM layer skipped in script context)
    try:
        result = await redact(text, router=None)
        clean = result.redacted
    except Exception as exc:
        print(f"  ⚠ PII redact error for {source}: {exc}")
        clean = text  # non-fatal — proceed with original

    # Lazy import to avoid loading the full stack at parse time
    from backend.rag.pipeline import vector_store
    try:
        chunks = vector_store.ingest(clean, metadata={"source": f"seed:{domain}:{source}"})
        return chunks
    except Exception as exc:
        print(f"  ✗ Ingest failed for {source}: {exc}")
        return 0


async def main() -> None:
    # Windows consoles default to cp1252 and crash on ✓/→/— glyphs — force UTF-8.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Seed FABLE RAG with curated corpora.")
    parser.add_argument(
        "--domain",
        nargs="*",
        default=None,
        choices=ALL_DOMAINS + ["all"],
        help="Domains to seed (default: all)",
    )
    parser.add_argument("--dry-run", action="store_true", help="List sources only, do not ingest")
    args = parser.parse_args()

    domains: list[str] | None = None
    if args.domain:
        if "all" in args.domain:
            domains = None
        else:
            domains = args.domain

    target_names = domains or ALL_DOMAINS
    total_sources = sum(len(SEED_SOURCES.get(d, [])) for d in target_names)
    print(f"{'[DRY RUN] ' if args.dry_run else ''}Seeding {total_sources} sources across {len(target_names)} domain(s): {', '.join(target_names)}")
    print()

    total_chunks = 0
    total_sources_ok = 0

    async for text, label, domain in iter_seed_texts(domains):
        word_count = len(text.split())
        if args.dry_run:
            print(f"  ✓ [{domain}] {label} — {word_count:,} words")
            total_sources_ok += 1
            continue

        print(f"  → [{domain}] {label} ({word_count:,} words) … ", end="", flush=True)
        chunks = await _ingest_text(text, label, domain, dry_run=False)
        total_chunks += chunks
        total_sources_ok += 1
        print(f"{chunks} chunks")

    print()
    if args.dry_run:
        print(f"Dry run complete: {total_sources_ok} sources would be ingested.")
    else:
        print(f"Seed complete: {total_sources_ok} sources → {total_chunks:,} chunks added to RAG store.")
        print("Tip: run `python scripts/eval_runs.py` to verify retrieval quality on seeded content.")


if __name__ == "__main__":
    asyncio.run(main())
