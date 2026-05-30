"""CLI: ingest text files or URLs into the vector store."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import httpx

from .pipeline import vector_store


def ingest_file(path: str, source_label: str | None = None) -> int:
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    label = source_label or Path(path).name
    n = vector_store.ingest(text, metadata={"source": label})
    print(f"Ingested {n} chunks from {label}")
    return n


async def ingest_url(url: str) -> int:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        text = resp.text
    n = vector_store.ingest(text, metadata={"source": url})
    print(f"Ingested {n} chunks from {url}")
    return n


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest documents into F.A.B.L.E. RAG store")
    parser.add_argument("sources", nargs="+", help="File paths or URLs to ingest")
    parser.add_argument("--label", help="Override source label for all inputs")
    args = parser.parse_args()

    total = 0
    for src in args.sources:
        if src.startswith("http://") or src.startswith("https://"):
            total += asyncio.run(ingest_url(src))
        else:
            total += ingest_file(src, args.label)
    print(f"\nTotal chunks ingested: {total}")


if __name__ == "__main__":
    main()
