"""
ELM inference engine — runs a local ONNX model to generate role declarations.

Uses onnxruntime-genai for text generation with Phi-3-mini-4k-instruct (INT4 quantized).
The engine is lazy-loaded: the ONNX session is created on first use, not at import time.

When onnxruntime-genai is not installed or the model is not present on disk,
the engine gracefully degrades and get_elm_engine() returns None.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import structlog

from .cache import DeclarationCache
from .declarations import PipelineDeclaration, RoleDeclaration
from .fallback import static_declarations
from .prompts import build_declaration_prompt
from ..core.config import settings

log = structlog.get_logger()

_ENGINE: "ELMEngine | None" = None

# Roles that MUST always be activated regardless of ELM output
_MANDATORY_ROLES = {"adv:planner", "adv:actor", "adv:judge"}


class ELMEngine:
    """
    Local ONNX inference engine for generating adversarial role declarations.

    Wraps onnxruntime-genai for Phi-3-mini text generation. The model is loaded
    lazily on first generate() call.
    """

    def __init__(self, model_path: str, max_tokens: int = 1024) -> None:
        self._model_path = Path(model_path)
        self._max_tokens = max_tokens
        self._model = None
        self._tokenizer = None
        self._cache = DeclarationCache(
            cache_dir=settings.elm_cache_dir,
            ttl_hours=settings.elm_cache_ttl_hours,
        )

    def _ensure_loaded(self) -> bool:
        """Load the ONNX model and tokenizer. Returns True if successful."""
        if self._model is not None:
            return True

        if not self._model_path.exists():
            log.warning("elm_model_not_found", path=str(self._model_path))
            return False

        try:
            import onnxruntime_genai as og

            self._model = og.Model(str(self._model_path))
            self._tokenizer = og.Tokenizer(self._model)
            log.info("elm_model_loaded", path=str(self._model_path))
            return True
        except ImportError:
            log.warning("elm_onnxruntime_genai_not_installed")
            return False
        except Exception:
            log.warning("elm_model_load_failed", path=str(self._model_path), exc_info=True)
            return False

    def generate(self, prompt: str) -> str:
        """Run ONNX inference and return raw text output."""
        if not self._ensure_loaded():
            raise RuntimeError("ELM model not available")

        # _ensure_loaded() guarantees these are set; assert satisfies mypy
        assert self._tokenizer is not None
        assert self._model is not None

        import onnxruntime_genai as og

        tokens = self._tokenizer.encode(prompt)

        params = og.GeneratorParams(self._model)
        params.set_search_options(
            max_length=self._max_tokens,
            temperature=0.3,  # Low temp for structured output
            top_p=0.9,
        )
        params.input_ids = tokens

        generator = og.Generator(self._model, params)
        output_tokens = []

        while not generator.is_done():
            generator.compute_logits()
            generator.generate_next_token()
            new_token = generator.get_next_tokens()[0]
            output_tokens.append(new_token)

        return self._tokenizer.decode(output_tokens)

    def generate_declarations(
        self, task_input: str, domain: str
    ) -> PipelineDeclaration:
        """
        Generate a PipelineDeclaration for the given task.

        Checks cache first. On cache miss, runs ELM inference.
        Falls back to static declarations on any failure.
        """
        # Check cache
        cached = self._cache.get(task_input, domain)
        if cached is not None:
            log.debug("elm_cache_hit", domain=domain)
            return cached

        # Generate via ELM
        prompt = build_declaration_prompt(task_input, domain)

        try:
            raw_output = self.generate(prompt)
            declarations = _parse_declarations(raw_output, domain, task_input)
        except Exception:
            log.warning("elm_generation_failed", exc_info=True)
            return static_declarations(domain=domain, task_input=task_input)

        if declarations is None:
            log.warning("elm_parse_failed", output_preview=raw_output[:200])
            return static_declarations(domain=domain, task_input=task_input)

        # Validate mandatory roles
        declarations = _enforce_mandatory_roles(declarations, domain, task_input)

        # Cache the result
        self._cache.put(declarations, task_input, domain)

        return declarations


def _parse_declarations(
    raw_output: str, domain: str, task_input: str
) -> PipelineDeclaration | None:
    """Parse ELM JSON output into a PipelineDeclaration."""
    # Strip markdown fences if present
    cleaned = re.sub(
        r"^```(?:json)?\s*|\s*```$", "", raw_output.strip(), flags=re.MULTILINE
    ).strip()

    # Try direct parse
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Fallback: find JSON array in output
        match = re.search(r"\[[\s\S]*\]", cleaned)
        if not match:
            return None
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            return None

    if not isinstance(data, list):
        return None

    declarations = []
    for item in data:
        try:
            decl = RoleDeclaration(
                role_name=item["role_name"],
                system_prompt=item["system_prompt"],
                model_assignment=item["model_assignment"],
                token_budget=int(item["token_budget"]),
                activation=bool(item["activation"]),
                execution_order=int(item["execution_order"]),
            )
            declarations.append(decl)
        except (KeyError, ValueError, TypeError):
            continue

    if not declarations:
        return None

    from .cache import DeclarationCache

    cache_key = DeclarationCache.make_key(task_input, domain)

    return PipelineDeclaration(
        task_hash=cache_key[:16],
        domain=domain,
        declarations=declarations,
        elm_model="phi-3-mini-4k-instruct-onnx",
        cache_key=cache_key,
    )


def _enforce_mandatory_roles(
    decl: PipelineDeclaration, domain: str, task_input: str
) -> PipelineDeclaration:
    """Ensure mandatory roles (planner, actor, judge) are always activated."""
    active_roles = {d.role_name for d in decl.declarations if d.activation}
    fallback = static_declarations(domain=domain, task_input=task_input)

    for mandatory_role in _MANDATORY_ROLES:
        if mandatory_role not in active_roles:
            # Role missing or deactivated — inject from fallback
            existing = decl.get_declaration(mandatory_role)
            if existing:
                existing.activation = True
            else:
                fb_decl = fallback.get_declaration(mandatory_role)
                if fb_decl:
                    decl.declarations.append(fb_decl)
            log.warning("elm_mandatory_role_enforced", role=mandatory_role)

    return decl


def get_elm_engine() -> ELMEngine | None:
    """
    Get the singleton ELM engine instance.

    Returns None if ELM is disabled in settings or the model is not available.
    """
    global _ENGINE

    if not settings.elm_enabled:
        return None

    if _ENGINE is None:
        model_path = settings.elm_model_path
        if not Path(model_path).exists():
            log.info("elm_disabled_no_model", path=model_path)
            return None
        _ENGINE = ELMEngine(
            model_path=model_path,
            max_tokens=settings.elm_max_tokens,
        )

    return _ENGINE
