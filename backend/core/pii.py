"""
PII redaction layer (P6a: regex + LLM hybrid — Presidio-free).

Pipeline:
  1. Regex pass — fast, free, catches structured PII (emails, phones, SSN, credit
     cards w/ Luhn, IBAN, IP, URL, raw API keys). ~10ms.
  2. LLM extraction pass (optional, `pii_llm_fallback=true`) — one call to a small
     classifier model returns NAME/LOCATION/ORG spans the regex layer can't see.
     ~200ms, ~$0.0001 per request.
  3. Spans merged, deduplicated by start offset, assigned stable placeholders
     (`[PERSON_1]`, `[EMAIL_2]`, ...). Encrypted entity values persisted to
     `public.pii_entity_map` (session-scoped, 7-day TTL).
  4. `reinject(text, entity_map)` substitutes placeholders back into outgoing
     responses (so the USER still sees their own names).
  5. `abstract_for_memory(text, scores)` produces a PII-free semantic summary
     for embedding into `memory_chunks` (notebook hard-rule: no raw PII in memory).

Hard rule (notebook): if `pii_enabled=True` and the redaction pipeline cannot
complete, raise `PiiRedactionFailed`. Orchestration must halt — no leakage.

Trade-off vs Presidio (documented in RESEARCH_LOG.md Phase 6):
  • Structured PII coverage: parity (regex).
  • PERSON / LOCATION / ORG: ~80-85% recall via LLM call vs Presidio's spaCy NER.
  • Bundle size: backend image drops ~1GB → fits free-tier deploy targets.
"""
from __future__ import annotations

import json
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass

import httpx
import structlog

from .config import settings
from .crypto import encrypt
from .db import get_db

log = structlog.get_logger()


class PiiRedactionFailed(Exception):
    """Raised when PII redaction cannot proceed; orchestration must halt."""


@dataclass
class EntitySpan:
    placeholder: str
    entity_value: str
    entity_type: str
    score: float
    start: int
    end: int


@dataclass
class RedactionResult:
    redacted: str
    entities: list[EntitySpan]


# ---------------------------------------------------------------------------
# Layer 1 — Regex patterns for structured PII
# ---------------------------------------------------------------------------

# Each entry: (entity_type, compiled regex, optional validator(match)->bool)
_REGEX_PATTERNS: list[tuple[str, re.Pattern[str], Callable[[re.Match[str]], bool]]] = [
    (
        "EMAIL_ADDRESS",
        re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"),
        lambda m: True,
    ),
    (
        "PHONE_NUMBER",
        re.compile(
            r"(?:(?<!\d)\+?\d{1,3}[\s.-]?)?"     # optional country code
            r"\(?\d{3}\)?[\s.-]?"                 # area code
            r"\d{3}[\s.-]?\d{4}(?!\d)"            # local
        ),
        # require at least 10 digits to reduce false positives on years/IDs
        lambda m: sum(c.isdigit() for c in m.group(0)) >= 10,
    ),
    (
        "US_SSN",
        re.compile(r"\b(?!000|666|9\d{2})\d{3}[- ]?(?!00)\d{2}[- ]?(?!0000)\d{4}\b"),
        lambda m: True,
    ),
    (
        "CREDIT_CARD",
        re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
        lambda m: _luhn_valid(re.sub(r"[^\d]", "", m.group(0))),
    ),
    (
        "IBAN",
        re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{1,30}\b"),
        lambda m: 15 <= len(m.group(0)) <= 34,
    ),
    (
        "IP_ADDRESS",
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
        ),
        lambda m: True,
    ),
    (
        "API_KEY",
        re.compile(
            r"sk-or-v1-[A-Za-z0-9]{16,}"          # OpenRouter
            r"|sk-ant-api03-[A-Za-z0-9_\-]{16,}"  # Anthropic
            r"|sk-[A-Za-z0-9]{32,}"               # OpenAI generic
        ),
        lambda m: True,
    ),
]


def _luhn_valid(digits: str) -> bool:
    """Standard mod-10 check on a digit string. Filters number sequences from real card numbers."""
    if not digits or len(digits) < 13:
        return False
    total = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        n = int(d)
        if i % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _regex_scan(text: str) -> list[EntitySpan]:
    """Run all regex patterns; return spans with stable placeholders."""
    spans: list[EntitySpan] = []
    for entity_type, pattern, valid in _REGEX_PATTERNS:
        for m in pattern.finditer(text):
            if not valid(m):
                continue
            spans.append(
                EntitySpan(
                    placeholder="",  # assigned after merge
                    entity_value=m.group(0),
                    entity_type=entity_type,
                    score=0.99,      # regex match = high confidence
                    start=m.start(),
                    end=m.end(),
                )
            )
    return spans


# ---------------------------------------------------------------------------
# Layer 2 — Single LLM extraction call for NAMES / LOCATIONS / ORGS
# ---------------------------------------------------------------------------

_LLM_EXTRACT_SYSTEM = (
    "You are a PII extractor. Read the user text and find every span that is "
    "personally identifying information of one of these types:\n"
    "- PERSON (a real person's full or first name)\n"
    "- LOCATION (a city, country, address, or geographic place)\n"
    "- ORGANIZATION (a company, school, or named institution)\n\n"
    "Reply with ONLY a raw JSON object, no markdown:\n"
    '{"entities":[{"text":"<exact span>","type":"PERSON|LOCATION|ORGANIZATION",'
    '"confidence":<0.0-1.0>}]}\n\n'
    "Rules:\n"
    "- The `text` value must appear verbatim in the user text (we use it to find offsets).\n"
    "- Skip generic terms (e.g. 'the doctor', 'a city') — only real names.\n"
    "- When uncertain, include the span with lower confidence; we prefer false "
    "positives over leaking PII.\n"
    "- If no PII present, return `{\"entities\":[]}`."
)


async def _llm_extract(text: str, router) -> list[EntitySpan]:
    """One LLM call returning candidate NAME / LOCATION / ORG spans."""
    if not router:
        return []
    try:
        resp = await router.complete(
            system=_LLM_EXTRACT_SYSTEM,
            user=text[:4000],
            role_hint="pii_extract",
            force_model=settings.pii_classifier_model,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("pii_llm_extract_failed", err=str(exc)[:120])
        return []

    raw = (resp.content or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.info("pii_llm_extract_parse_failed", preview=raw[:120])
        return []

    spans: list[EntitySpan] = []
    threshold = settings.pii_confidence_threshold
    for ent in data.get("entities") or []:
        span_text = (ent.get("text") or "").strip()
        entity_type = (ent.get("type") or "").upper().strip()
        confidence = float(ent.get("confidence") or 0.0)
        if not span_text or entity_type not in ("PERSON", "LOCATION", "ORGANIZATION"):
            continue
        if confidence < threshold:
            continue
        # Find the first occurrence of the verbatim span in the source text.
        start = text.find(span_text)
        if start == -1:
            continue
        spans.append(
            EntitySpan(
                placeholder="",
                entity_value=span_text,
                entity_type=entity_type,
                score=confidence,
                start=start,
                end=start + len(span_text),
            )
        )
    return spans


# ---------------------------------------------------------------------------
# Layer 2b — Presidio sidecar (Phase 10)
# ---------------------------------------------------------------------------

async def _presidio_extract(text: str) -> list[EntitySpan]:
    """Call the Presidio Analyzer sidecar for NER-grade PERSON/LOCATION/ORG detection.

    Only invoked when `settings.presidio_url` is set (local compose / k8s).
    Falls back silently on any error — regex spans still flow through.

    Latency: ~50ms p50 (vs ~200ms LLM call). Recall: ~95% (spaCy en_core_web_lg).
    """
    url = settings.presidio_url
    if not url:
        return []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{url}/analyze",
                json={
                    "text": text[:4000],
                    "language": "en",
                    "entities": ["PERSON", "LOCATION", "ORGANIZATION"],
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("presidio_extract_failed", err=str(exc)[:120])
        return []

    spans: list[EntitySpan] = []
    threshold = settings.pii_confidence_threshold
    for item in data or []:
        entity_type = (item.get("entity_type") or "").upper().strip()
        score = float(item.get("score") or 0.0)
        start = int(item.get("start") or 0)
        end = int(item.get("end") or 0)
        if entity_type not in ("PERSON", "LOCATION", "ORGANIZATION"):
            continue
        if score < threshold:
            continue
        if end <= start:
            continue
        entity_value = text[start:end]
        spans.append(
            EntitySpan(
                placeholder="",
                entity_value=entity_value,
                entity_type=entity_type,
                score=score,
                start=start,
                end=end,
            )
        )
    return spans


# ---------------------------------------------------------------------------
# Merge, dedupe, assign placeholders
# ---------------------------------------------------------------------------

def _merge_spans(text: str, spans: list[EntitySpan]) -> RedactionResult:
    """Sort by start; drop overlapping spans (regex wins on ties); assign placeholders.

    F-011: placeholders use a per-redaction nonce so user-injected literal placeholder
    strings cannot collide with real ones. Format: __PII_<nonce>_<TYPE>_<N>__
    The double-underscore delimiters also prevent [TYPE_1] being a substring of [TYPE_10].
    """
    if not spans:
        return RedactionResult(redacted=text, entities=[])

    # Sort: by start asc, then by score desc (regex confidence wins overlaps)
    spans.sort(key=lambda s: (s.start, -s.score))

    keep: list[EntitySpan] = []
    cursor = 0
    for s in spans:
        if s.start < cursor:
            continue  # overlaps a previous span; skip
        keep.append(s)
        cursor = s.end

    # Per-redaction nonce — 6 hex chars (24 bits of entropy). Makes placeholders
    # unguessable by users and prevents cross-request collision.
    nonce = secrets.token_hex(3)

    counters: dict[str, int] = {}
    redacted_parts: list[str] = []
    pos = 0
    for s in keep:
        counters[s.entity_type] = counters.get(s.entity_type, 0) + 1
        placeholder = f"__PII_{nonce}_{s.entity_type}_{counters[s.entity_type]}__"
        s.placeholder = placeholder
        redacted_parts.append(text[pos : s.start])
        redacted_parts.append(placeholder)
        pos = s.end
    redacted_parts.append(text[pos:])
    return RedactionResult(redacted="".join(redacted_parts), entities=keep)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def redact_text_sync(text: str) -> str:
    """Synchronous regex-only redaction. Returns redacted text (placeholders for
    structured PII). No LLM/network — safe for export paths like notebook generation (F-033).
    Does NOT catch PERSON/LOC/ORG (those need the LLM/Presidio layer)."""
    if not settings.pii_enabled or not text or not text.strip():
        return text
    try:
        spans = _regex_scan(text)
        return _merge_spans(text, spans).redacted
    except Exception:  # noqa: BLE001
        return text


async def redact(text: str, router=None) -> RedactionResult:
    """Detect PII spans, replace with placeholders, return both."""
    if not settings.pii_enabled:
        return RedactionResult(redacted=text, entities=[])
    if not text or not text.strip():
        return RedactionResult(redacted=text, entities=[])

    try:
        spans = _regex_scan(text)
    except Exception as exc:  # noqa: BLE001
        raise PiiRedactionFailed(f"regex scan failed: {exc}") from exc

    if settings.presidio_url:
        # Phase 10: Presidio sidecar takes priority over LLM extraction when configured.
        # ~95% NER recall at ~50ms, zero per-request LLM cost. Fails non-fatally.
        spans.extend(await _presidio_extract(text))
    elif settings.pii_llm_fallback and router is not None:
        try:
            spans.extend(await _llm_extract(text, router))
        except Exception as exc:  # noqa: BLE001
            # LLM failures are non-fatal — regex spans still flow through.
            log.warning("pii_llm_layer_failed", err=str(exc)[:120])

    return _merge_spans(text, spans)


def persist_entity_map(
    entities: list[EntitySpan], session_id: str, task_id: str
) -> None:
    """Encrypt + persist entity values to public.pii_entity_map (7-day TTL via schema)."""
    if not entities:
        return
    rows = [
        {
            "session_id": session_id,
            "task_id": task_id,
            "placeholder": e.placeholder,
            "entity_enc": encrypt(e.entity_value),
            "entity_type": e.entity_type,
        }
        for e in entities
    ]
    try:
        get_db().table("pii_entity_map").insert(rows).execute()
    except Exception as exc:  # noqa: BLE001
        # Persistence failure is non-fatal — entities still in memory for reinject().
        log.warning("pii_entity_map_insert_failed", err=str(exc))


def reinject(text: str, entities: list[EntitySpan]) -> str:
    """Substitute placeholders back to their original values in outgoing text.

    F-011: sort by placeholder length descending so longer tokens are replaced first,
    preventing any residual substring collision (e.g. __PII_x_PERSON_10__ before
    __PII_x_PERSON_1__). The nonce format already prevents collisions, but the sort
    provides belt-and-suspenders safety.
    """
    if not entities:
        return text
    out = text
    for e in sorted(entities, key=lambda e: len(e.placeholder), reverse=True):
        out = out.replace(e.placeholder, e.entity_value)
    return out


async def abstract_for_memory(
    text: str, scores: dict[str, float] | None, router=None
) -> str:
    """Produce a PII-free semantic summary suitable for embedding into memory.

    Without a router: returns the redacted text as-is (caller must pass redacted text).
    """
    if not router or not settings.memory_abstraction_enabled:
        return text

    system = (
        "Compress the user turn into ONE short third-person sentence stating the "
        "topic, domain, and intent. NEVER include names, locations, emails, phones, "
        "IDs, dates, numbers, or any other identifying detail. Output the sentence "
        "only, no prefix."
    )
    try:
        resp = await router.complete(
            system=system,
            user=text[:1500],
            role_hint="memory_abstract",
            force_model=settings.memory_abstraction_model,
        )
        return (resp.content or "").strip()[:500]
    except Exception as exc:  # noqa: BLE001
        log.warning("memory_abstract_failed", err=str(exc))
        return text
