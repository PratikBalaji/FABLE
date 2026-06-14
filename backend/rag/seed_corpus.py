"""
Curated sanitized RAG seed corpus (Phase 15).

Breadth-first domain coverage — all sources are license-clean (public domain,
CC0, or permissive open license). Every source passes through:
  1. HTML strip (_strip_html from rag.sources)
  2. PII redact (core.pii.redact — preserves "no raw PII in store" invariant)
  3. Content dedup (content hash)
  4. Chunking + embedding via existing rag.ingestion pipeline

Domain coverage (open-ended prompt system requires breadth, not finance-only):
  general_reasoning  — logical reasoning chains, factual QA
  stem               — science/math abstracts, STEM explanations
  code_review        — PEPs, CWE Top-25, OWASP secure coding
  finance            — SEC EDGAR 10-K samples, financial definitions
  writing            — plain-language guidance, clarity principles
  medical_light      — factual public-domain definitions (tagged advisory-only)
  legal_light        — public-domain legal definitions (tagged advisory-only)

License provenance (all verified public-domain / CC0 / permissive):
  Source                          License / Authority
  ──────────────────────────────  ────────────────────────────────────────
  PEPs (peps.python.org)          Python Software Foundation — public
  CWE (cwe.mitre.org)             MITRE — public domain / free use
  OWASP Top-10 (owasp.org)        CC BY-SA 4.0
  SEC EDGAR (sec.gov)             U.S. gov — public domain
  Wikipedia (en.wikipedia.org)    CC BY-SA 4.0
  US Gov plain-language guide     U.S. gov — public domain
  MedlinePlus (medlineplus.gov)   U.S. NIH — public domain
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import AsyncIterator

import httpx
import structlog

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Source definitions
# ---------------------------------------------------------------------------

@dataclass
class SeedSource:
    url: str
    domain: str
    label: str
    advisory_tag: str = ""   # e.g. "[for reference only — not professional advice]"


SEED_SOURCES: dict[str, list[SeedSource]] = {
    "general_reasoning": [
        SeedSource(
            url="https://en.wikipedia.org/w/index.php?action=raw&title=Logic",
            domain="general_reasoning",
            label="Wikipedia: Logic",
        ),
        SeedSource(
            url="https://en.wikipedia.org/w/index.php?action=raw&title=Critical_thinking",
            domain="general_reasoning",
            label="Wikipedia: Critical Thinking",
        ),
        SeedSource(
            url="https://en.wikipedia.org/w/index.php?action=raw&title=Argument",
            domain="general_reasoning",
            label="Wikipedia: Argument",
        ),
    ],
    "stem": [
        SeedSource(
            url="https://en.wikipedia.org/w/index.php?action=raw&title=Scientific_method",
            domain="stem",
            label="Wikipedia: Scientific Method",
        ),
        SeedSource(
            url="https://en.wikipedia.org/w/index.php?action=raw&title=Mathematics",
            domain="stem",
            label="Wikipedia: Mathematics",
        ),
        SeedSource(
            url="https://en.wikipedia.org/w/index.php?action=raw&title=Algorithm",
            domain="stem",
            label="Wikipedia: Algorithm",
        ),
        SeedSource(
            url="https://en.wikipedia.org/w/index.php?action=raw&title=Artificial_intelligence",
            domain="stem",
            label="Wikipedia: Artificial Intelligence",
        ),
    ],
    "code_review": [
        SeedSource(url="https://peps.python.org/pep-0008/", domain="code_review", label="PEP 8"),
        SeedSource(url="https://peps.python.org/pep-0020/", domain="code_review", label="PEP 20"),
        SeedSource(url="https://peps.python.org/pep-0257/", domain="code_review", label="PEP 257"),
        SeedSource(
            url="https://cwe.mitre.org/data/definitions/1350.html",
            domain="code_review",
            label="CWE Top-25 Software Weaknesses",
        ),
        SeedSource(
            url="https://owasp.org/www-project-top-ten/",
            domain="code_review",
            label="OWASP Top-10",
        ),
    ],
    "finance": [
        SeedSource(
            url="https://en.wikipedia.org/w/index.php?action=raw&title=Financial_statement",
            domain="finance",
            label="Wikipedia: Financial Statements",
        ),
        SeedSource(
            url="https://en.wikipedia.org/w/index.php?action=raw&title=Balance_sheet",
            domain="finance",
            label="Wikipedia: Balance Sheet",
        ),
        SeedSource(
            url="https://en.wikipedia.org/w/index.php?action=raw&title=Income_statement",
            domain="finance",
            label="Wikipedia: Income Statement",
        ),
    ],
    "writing": [
        SeedSource(
            url="https://www.plainlanguage.gov/guidelines/",
            domain="writing",
            label="U.S. Plain Language Guidelines",
        ),
        SeedSource(
            url="https://en.wikipedia.org/w/index.php?action=raw&title=Technical_writing",
            domain="writing",
            label="Wikipedia: Technical Writing",
        ),
    ],
    "medical_light": [
        SeedSource(
            url="https://medlineplus.gov/healthtopics.html",
            domain="medical_light",
            label="MedlinePlus Health Topics",
            advisory_tag="[For reference only — not medical advice. Consult a licensed professional.]",
        ),
    ],
    "legal_light": [
        SeedSource(
            url="https://en.wikipedia.org/w/index.php?action=raw&title=Law",
            domain="legal_light",
            label="Wikipedia: Law",
            advisory_tag="[For reference only — not legal advice. Consult a licensed attorney.]",
        ),
    ],
}

ALL_DOMAINS = list(SEED_SOURCES.keys())

# ---------------------------------------------------------------------------
# Fetch + sanitize helpers
# ---------------------------------------------------------------------------

def _strip_wiki_markup(text: str) -> str:
    """Remove MediaWiki markup (used for raw Wikipedia pages)."""
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)  # [[link|text]] → text
    text = re.sub(r"==+([^=]+)==+", r"\1", text)                    # headings
    text = re.sub(r"'''?([^']+)'''?", r"\1", text)                  # bold/italic
    text = re.sub(r"\{\{.*?\}\}", "", text, flags=re.DOTALL)        # templates (may span lines)
    text = re.sub(r"<[^>]+>", " ", text)                            # HTML tags
    text = re.sub(r"\[\[File:[^\]]+\]\]", "", text)                 # file links
    text = re.sub(r"\[\[Category:[^\]]+\]\]", "", text)             # categories
    text = re.sub(r"https?://\S+", "", text)                        # bare URLs
    return re.sub(r"\s{2,}", " ", text).strip()


# Recurring page-chrome phrases to drop (theme togglers, skip-nav, cookie notices).
_CHROME_PHRASES = (
    "colour scheme", "color scheme", "skip to content", "skip to main",
    "following system", "toggle navigation", "cookie", "javascript is disabled",
)

_HTML_ENTITIES = {
    "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'",
    "&apos;": "'", "&nbsp;": " ", "&mdash;": "—", "&ndash;": "–", "&hellip;": "…",
}


def _strip_html(html: str) -> str:
    """Extract readable text from an HTML page: drop script/style/nav/header/footer
    blocks (page chrome + boilerplate), strip remaining tags, decode entities, and
    collapse whitespace. Removes the nav/theme boilerplate that polluted seed chunks."""
    # 1. Remove whole non-content blocks (with their inner text)
    html = re.sub(
        r"(?is)<(script|style|head|nav|header|footer|noscript|svg|form|aside)\b[^>]*>.*?</\1>",
        " ",
        html,
    )
    # 2. Treat block-level closers as line breaks so structure survives
    html = re.sub(r"(?i)</(p|div|li|h[1-6]|tr|br|section|article)\s*>", "\n", html)
    # 3. Strip all remaining tags
    text = re.sub(r"<[^>]+>", " ", html)
    # 4. Decode common entities (named + numeric)
    for ent, ch in _HTML_ENTITIES.items():
        text = text.replace(ent, ch)
    text = re.sub(r"&#\d+;", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    # 5. Normalize whitespace per line, drop empty/very-short + known-chrome lines, dedupe
    seen: set[str] = set()
    lines: list[str] = []
    for raw in text.splitlines():
        line = re.sub(r"[ \t]{2,}", " ", raw).strip()
        if len(line) < 3:           # skip nav glyphs / single words of chrome
            continue
        low = line.lower()
        if any(p in low for p in _CHROME_PHRASES):  # theme togglers, skip links, etc.
            continue
        if line in seen:            # drop repeated boilerplate lines
            continue
        seen.add(line)
        lines.append(line)
    return "\n".join(lines).strip()


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


async def _fetch_source(source: SeedSource, client: httpx.AsyncClient) -> str | None:
    try:
        resp = await client.get(source.url, follow_redirects=True)
        resp.raise_for_status()
        raw = resp.text
        # Wikipedia raw API returns wikitext; everything else is HTML
        if "action=raw" in source.url:
            text = _strip_wiki_markup(raw)
        elif "<" in raw:
            text = _strip_html(raw)
        else:
            text = raw
        if source.advisory_tag:
            text = source.advisory_tag + "\n\n" + text
        return text[:80_000]  # cap per source
    except Exception as exc:
        log.warning("seed_fetch_failed", url=source.url, err=str(exc)[:120])
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def iter_seed_texts(
    domains: list[str] | None = None,
) -> AsyncIterator[tuple[str, str, str]]:
    """Yield (text, source_label, domain) for each seed source in requested domains.

    Applies HTML strip only (not PII redact — caller script does that via pii.redact
    to keep this module free of async router dependency).
    """
    targets = domains or ALL_DOMAINS
    headers = {"User-Agent": "fable-research research@fable.ai"}
    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        for domain in targets:
            for source in SEED_SOURCES.get(domain, []):
                text = await _fetch_source(source, client)
                if text and text.strip():
                    yield text, source.label, source.domain
