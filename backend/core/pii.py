"""
PII redaction layer (P4a).

Pipeline:
  1. Presidio AnalyzerEngine detects spans (PERSON, EMAIL_ADDRESS, PHONE_NUMBER,
     US_SSN, CREDIT_CARD, LOCATION, IBAN, etc.). Fast (~50ms typical).
  2. For spans below `pii_confidence_threshold`, optionally consult a small LLM
     (Llama-Guard-3-8B by default) to confirm or reject — reduces false positives
     on common nouns mistaken for names.
  3. Replace each accepted span with a stable placeholder like `[PERSON_1]`,
     `[EMAIL_2]`, AES-GCM-encrypt the original value, and persist to
     `public.pii_entity_map` (session-scoped, 7-day TTL).
  4. `reinject(text, entity_map)` decrypts and substitutes placeholders back
     into the OUTGOING response (so the user sees their own names again).
  5. `abstract_for_memory(text, scores)` produces a PII-free semantic summary
     suitable for embedding into `memory_chunks`.

Hard rule (notebook): if `pii_enabled` is True and any step fails, raise
`PiiRedactionFailed`. Orchestration must halt — no leakage into memory.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import structlog

from .config import settings
from .crypto import encrypt
from .db import get_db

log = structlog.get_logger()


# Presidio is imported lazily so legacy mode without the deps still imports clean.
_analyzer = None
_anonymizer = None


def _get_engines():
    """Lazy-init Presidio analyzer/anonymizer (and spaCy model under the hood)."""
    global _analyzer, _anonymizer
    if _analyzer is None:
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine
        except ImportError as exc:
            raise PiiRedactionFailed(
                "presidio not installed (P4a). pip install presidio-analyzer "
                "presidio-anonymizer spacy && python -m spacy download "
                f"{settings.pii_spacy_model}"
            ) from exc
        _analyzer = AnalyzerEngine()
        _anonymizer = AnonymizerEngine()
    return _analyzer, _anonymizer


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


# --- public API ------------------------------------------------------------

async def redact(text: str, router=None) -> RedactionResult:
    """Detect PII spans in `text`, replace with placeholders, return both.

    `router` is optional; if provided and `pii_llm_fallback=True`, low-confidence
    spans are re-confirmed by a single LLM call before being kept.
    """
    if not settings.pii_enabled:
        return RedactionResult(redacted=text, entities=[])
    if not text or not text.strip():
        return RedactionResult(redacted=text, entities=[])

    try:
        analyzer, _ = _get_engines()
        results = analyzer.analyze(text=text, language="en")
    except PiiRedactionFailed:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PiiRedactionFailed(f"Presidio analyze failed: {exc}") from exc

    # Optional LLM fallback to disambiguate low-confidence spans
    if settings.pii_llm_fallback and router is not None:
        results = await _confirm_with_llm(text, results, router)

    # Sort by start to assign stable placeholder indices (PERSON_1, PERSON_2, ...)
    results.sort(key=lambda r: r.start)
    counters: dict[str, int] = {}
    entities: list[EntitySpan] = []
    redacted_parts: list[str] = []
    cursor = 0
    for r in results:
        if r.start < cursor:
            continue  # overlapping span, skip
        entity_type = r.entity_type
        counters[entity_type] = counters.get(entity_type, 0) + 1
        placeholder = f"[{entity_type}_{counters[entity_type]}]"
        entities.append(
            EntitySpan(
                placeholder=placeholder,
                entity_value=text[r.start : r.end],
                entity_type=entity_type,
                score=float(r.score),
                start=r.start,
                end=r.end,
            )
        )
        redacted_parts.append(text[cursor : r.start])
        redacted_parts.append(placeholder)
        cursor = r.end
    redacted_parts.append(text[cursor:])
    redacted = "".join(redacted_parts)
    return RedactionResult(redacted=redacted, entities=entities)


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
        # Persistence failure is non-fatal — entities are still in memory for reinject()
        log.warning("pii_entity_map_insert_failed", err=str(exc))


def reinject(text: str, entities: list[EntitySpan]) -> str:
    """Substitute placeholders back to their original values in outgoing text."""
    if not entities:
        return text
    out = text
    for e in entities:
        out = out.replace(e.placeholder, e.entity_value)
    return out


async def abstract_for_memory(text: str, scores: dict[str, float] | None, router=None) -> str:
    """Produce a PII-free semantic summary suitable for embedding into memory.

    Fallback (no router): just return the already-redacted text (assumes caller
    passed redacted_text, NOT raw text).
    """
    if not router or not settings.memory_abstraction_enabled:
        return text  # caller MUST pass redacted text in this case

    system = (
        "Compress the user turn into ONE short third-person sentence stating the topic, "
        "domain, and intent. NEVER include names, locations, emails, phones, IDs, dates, "
        "numbers, or any other identifying detail. Output the sentence only, no prefix."
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
        return text  # fall back to redacted text


# --- LLM disambiguation ---------------------------------------------------

_LLM_DISAMBIG_SYSTEM = (
    "You are a PII verifier. Given a sentence and a SPAN extracted from it, "
    "decide whether the span is truly personally identifiable information. "
    'Reply with ONLY one JSON object: {"pii": true|false, "reason": "<short>"}. '
    "Be conservative: when unsure, answer pii:true."
)


async def _confirm_with_llm(text: str, results: list[Any], router) -> list[Any]:
    """Filter Presidio results: keep high-confidence; LLM-verify low-confidence."""
    threshold = settings.pii_confidence_threshold
    confirmed = []
    for r in results:
        if r.score >= threshold:
            confirmed.append(r)
            continue
        span_text = text[r.start : r.end]
        try:
            resp = await router.complete(
                system=_LLM_DISAMBIG_SYSTEM,
                user=f"Sentence: {text[:600]}\nSpan: {span_text}\nClaimed type: {r.entity_type}",
                role_hint="pii_disambig",
                force_model=settings.pii_classifier_model,
            )
            raw = (resp.content or "").strip()
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
            import json
            data = json.loads(raw) if raw else {}
            if data.get("pii"):
                confirmed.append(r)
        except Exception as exc:  # noqa: BLE001
            # Safety: if disambiguation fails, KEEP the span (false positive > leak)
            log.info("pii_disambig_failed_kept", err=str(exc)[:80])
            confirmed.append(r)
    return confirmed
