"""Domain-specific document sources for RAG ingestion."""
from __future__ import annotations

from typing import AsyncIterator

import httpx


# PEP index for code review domain
PEP_URLS = [
    "https://peps.python.org/pep-0008/",   # Style Guide
    "https://peps.python.org/pep-0020/",   # Zen of Python
    "https://peps.python.org/pep-0257/",   # Docstring conventions
]

# SEC EDGAR full-text search for finance domain
SEC_EDGAR_FULL_TEXT = "https://efts.sec.gov/LATEST/search-index?q={query}&dateRange=custom&startdt=2023-01-01&forms=10-K"


async def fetch_pep_docs() -> AsyncIterator[tuple[str, str]]:
    """Yield (text, source_label) for each PEP."""
    async with httpx.AsyncClient(timeout=30) as client:
        for url in PEP_URLS:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                yield resp.text, url
            except Exception as e:
                print(f"Warning: could not fetch {url}: {e}")


async def fetch_sec_filing(ticker: str, cik: str) -> tuple[str, str]:
    """Fetch the latest 10-K filing text for a given CIK from SEC EDGAR."""
    url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "fable-bot research@fable.ai"}) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    company_name = data.get("name", ticker)
    # Return metadata stub; real implementation would fetch actual filing text
    return f"Company: {company_name}\nTicker: {ticker}\nCIK: {cik}", f"SEC 10-K {ticker}"
