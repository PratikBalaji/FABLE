"""Domain-specific document sources for RAG ingestion."""
from __future__ import annotations

import re
from typing import AsyncIterator

import httpx


# PEP index for code review domain
PEP_URLS = [
    "https://peps.python.org/pep-0008/",   # Style Guide
    "https://peps.python.org/pep-0020/",   # Zen of Python
    "https://peps.python.org/pep-0257/",   # Docstring conventions
]

_SEC_HEADERS = {"User-Agent": "fable-research research@fable.ai"}
_MAX_FILING_CHARS = 60_000  # cap per 10-K to keep chunk counts manageable


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace for plain-text RAG ingestion."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    return re.sub(r"\s{2,}", " ", text).strip()


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
    """Fetch the latest 10-K filing text for a given CIK from SEC EDGAR.

    Flow:
      1. GET submissions/{CIK}.json — finds most recent 10-K accession + primary document
      2. GET Archives/edgar/data/{cik}/{accession}/{primary_doc} — actual filing HTML
      3. Strip HTML → plain text → truncate to _MAX_FILING_CHARS
    """
    async with httpx.AsyncClient(timeout=30, headers=_SEC_HEADERS) as client:
        # Step 1: submissions metadata
        sub_url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
        sub_resp = await client.get(sub_url)
        sub_resp.raise_for_status()
        data = sub_resp.json()

        company_name = data.get("name", ticker)
        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        accessions = filings.get("accessionNumber", [])
        primary_docs = filings.get("primaryDocument", [])
        filing_dates = filings.get("filingDate", [])

        # Find most recent 10-K (list is newest-first)
        ten_k_idx: int | None = None
        for i, form in enumerate(forms):
            if form in ("10-K", "10-K/A"):
                ten_k_idx = i
                break

        if ten_k_idx is None:
            # No 10-K found — fall back to company metadata only
            return (
                f"Company: {company_name}\nTicker: {ticker}\nCIK: {cik}\n"
                "(No 10-K filing found in EDGAR recent filings.)",
                f"SEC EDGAR {ticker}",
            )

        accession = accessions[ten_k_idx].replace("-", "")
        primary_doc = primary_docs[ten_k_idx]
        filing_date = filing_dates[ten_k_idx]

        # Step 2: fetch filing document
        filing_url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{primary_doc}"
        )
        filing_resp = await client.get(filing_url)
        filing_resp.raise_for_status()

        # Step 3: strip HTML → truncate
        raw = filing_resp.text
        plain = _strip_html(raw) if "<" in raw else raw
        text = plain[:_MAX_FILING_CHARS]

        header = f"Company: {company_name}\nTicker: {ticker}\nCIK: {cik}\nFiling: 10-K ({filing_date})\n\n"
        return header + text, f"SEC 10-K {ticker} ({filing_date})"
