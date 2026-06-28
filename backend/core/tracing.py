"""
Phase 19 — LangSmith tracing wiring (optional, Cloud-Run-safe).

LangChain/LangGraph auto-emit traces when the LANGCHAIN_* environment variables are
set. This module bridges the typed settings (config.py) into os.environ exactly once,
and ONLY when an API key is present. With no key, tracing stays fully off and nothing
in the hot path changes — safe for the free-tier Cloud Run deploy.
"""
from __future__ import annotations

import os

import structlog

from .config import settings

log = structlog.get_logger()

_configured = False


def configure_langsmith() -> bool:
    """Export LANGCHAIN_* env vars for LangChain/LangGraph. Returns True if tracing on.

    Idempotent. No-op (returns False) unless both langchain_tracing_v2 is true and an
    API key is configured.
    """
    global _configured
    if _configured:
        return os.environ.get("LANGCHAIN_TRACING_V2") == "true"
    _configured = True

    if not (settings.langchain_tracing_v2 and settings.langchain_api_key):
        log.info("langsmith_tracing_disabled")
        return False

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
    os.environ["LANGCHAIN_ENDPOINT"] = settings.langchain_endpoint
    log.info("langsmith_tracing_enabled", project=settings.langchain_project)
    return True
