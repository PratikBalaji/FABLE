"""OpenTelemetry tracing for F.A.B.L.E.

Gated by OTEL_ENABLED env var (default: false — no behaviour change, $0 stack).
When enabled: spans are written to a local OTLP-compatible JSON file AND the
console, so any Jaeger/OTLP collector can be pointed at the file without restart.

Usage::

    # .env or shell
    OTEL_ENABLED=true
    OTEL_TRACES_FILE=./data/traces/fable_traces.jsonl  # optional

    # In any module
    from backend.core.telemetry import get_tracer, record_llm_span

    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("my_operation") as span:
        span.set_attribute("model", "gpt-4o-mini")
        ...

The module is import-safe when OTEL_ENABLED=false — a no-op tracer is returned.
"""
from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger(__name__)

_ENABLED = os.getenv("OTEL_ENABLED", "false").lower() in ("1", "true", "yes")
_TRACES_FILE = Path(os.getenv("OTEL_TRACES_FILE", "./data/traces/fable_traces.jsonl"))
_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "fable-backend")

# ---------------------------------------------------------------------------
# OTel bootstrap (only runs when OTEL_ENABLED=true)
# ---------------------------------------------------------------------------
_tracer_provider: Any = None
_tracer_cache: dict[str, Any] = {}

if _ENABLED:
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
            SimpleSpanProcessor,
        )
        from opentelemetry.sdk.resources import Resource

        # File exporter — writes OTLP-JSON to local file (OTLP-collector-ready)
        class _FileSpanExporter:
            """Appends span JSON to a local JSONL file."""

            def __init__(self, path: Path) -> None:
                self._path = path
                self._path.parent.mkdir(parents=True, exist_ok=True)

            def export(self, spans: Any) -> Any:
                from opentelemetry.sdk.trace.export import SpanExportResult

                try:
                    with open(self._path, "a", encoding="utf-8") as f:
                        for span in spans:
                            record = {
                                "trace_id": format(span.context.trace_id, "032x"),
                                "span_id": format(span.context.span_id, "016x"),
                                "name": span.name,
                                "start_time": span.start_time,
                                "end_time": span.end_time,
                                "duration_ms": (span.end_time - span.start_time) / 1_000_000
                                if span.end_time and span.start_time else None,
                                "status": str(span.status.status_code),
                                "attributes": dict(span.attributes or {}),
                                "service": _SERVICE_NAME,
                            }
                            f.write(json.dumps(record) + "\n")
                    return SpanExportResult.SUCCESS
                except Exception as exc:
                    logger.warning("otel_file_export_failed: %s", exc)
                    return SpanExportResult.FAILURE

            def shutdown(self) -> None:
                pass

            def force_flush(self, timeout_millis: int = 30000) -> bool:
                return True

        resource = Resource.create({"service.name": _SERVICE_NAME})
        provider = TracerProvider(resource=resource)

        # Console span processor (human-readable during dev)
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        # File span processor (OTLP-ready JSONL)
        provider.add_span_processor(BatchSpanProcessor(_FileSpanExporter(_TRACES_FILE)))

        trace.set_tracer_provider(provider)
        _tracer_provider = provider
        logger.info("otel_enabled service=%s file=%s", _SERVICE_NAME, _TRACES_FILE)
    except ImportError:
        logger.warning("opentelemetry-sdk not installed; OTEL_ENABLED=true has no effect. "
                       "Install: pip install opentelemetry-sdk opentelemetry-exporter-otlp")
        _ENABLED = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_enabled() -> bool:
    return _ENABLED


def get_tracer(name: str) -> Any:
    """Return an OTel tracer (or a no-op tracer when disabled)."""
    if not _ENABLED:
        return _NoOpTracer()
    if name not in _tracer_cache:
        from opentelemetry import trace
        _tracer_cache[name] = trace.get_tracer(name)
    return _tracer_cache[name]


@contextmanager
def llm_span(
    tracer: Any,
    operation: str,
    model: str,
    role: str = "",
) -> Generator[Any, None, None]:
    """Context manager that wraps an LLM call in an OTel span.

    Attaches ``model``, ``role``, and (after the call) ``tokens.input``,
    ``tokens.output``, ``cost.usd`` attributes. Use as::

        with llm_span(tracer, "router.complete", model="gpt-4o-mini", role="critic") as span:
            resp = await router.complete(...)
            annotate_span(span, resp.model, resp.usage)
    """
    if not _ENABLED:
        yield _NoOpSpan()
        return
    with tracer.start_as_current_span(f"fable.llm.{operation}") as span:
        span.set_attribute("llm.model", model)
        span.set_attribute("llm.role", role)
        span.set_attribute("service.name", _SERVICE_NAME)
        yield span


def annotate_span(span: Any, model: str, usage: dict[str, int]) -> None:
    """Attach token + cost attributes to an open span after an LLM response."""
    if not _ENABLED or isinstance(span, _NoOpSpan):
        return
    try:
        from .cost import price
        usd = price(model, usage)
        span.set_attribute("llm.tokens.input", usage.get("input", 0))
        span.set_attribute("llm.tokens.output", usage.get("output", 0))
        span.set_attribute("llm.cost.usd", round(usd, 6))
        span.set_attribute("llm.model.resolved", model)
    except Exception:
        pass


def record_run_event(
    span: Any,
    event: str,
    attrs: dict[str, Any] | None = None,
) -> None:
    """Add a named event to an open span."""
    if not _ENABLED or isinstance(span, _NoOpSpan):
        return
    try:
        span.add_event(event, attributes=attrs or {})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# No-op stubs (used when OTEL_ENABLED=false)
# ---------------------------------------------------------------------------

class _NoOpSpan:
    def set_attribute(self, *_: Any, **__: Any) -> None: ...
    def add_event(self, *_: Any, **__: Any) -> None: ...
    def __enter__(self) -> "_NoOpSpan": return self
    def __exit__(self, *_: Any) -> None: ...


class _NoOpTracer:
    def start_as_current_span(self, name: str, **_: Any) -> "_NoOpSpanCtx":
        return _NoOpSpanCtx()
    def start_span(self, *_: Any, **__: Any) -> _NoOpSpan:
        return _NoOpSpan()


class _NoOpSpanCtx:
    def __enter__(self) -> _NoOpSpan: return _NoOpSpan()
    def __exit__(self, *_: Any) -> None: ...


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"OTel enabled: {is_enabled()}")
    t = get_tracer("test")
    with llm_span(t, "test_call", model="openai/gpt-4o-mini", role="critic") as s:
        annotate_span(s, "openai/gpt-4o-mini", {"input": 100, "output": 50})
        record_run_event(s, "test.event", {"key": "value"})
    print("No-op tracer test passed.")
