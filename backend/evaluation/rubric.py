"""Rubric-based scorer: uses OpenRouter to rate collaboration output on 5 dimensions."""
from __future__ import annotations

import json
import re

import openai

from ..core.config import settings

_DIMENSIONS = ["accuracy", "depth", "clarity", "actionability", "coverage"]

_SYSTEM = """You are an impartial evaluator of AI-generated analysis.
Score the provided output on each dimension from 0.0 to 1.0.
Return ONLY a JSON object with these exact keys: accuracy, depth, clarity, actionability, coverage.
No explanation, no markdown — raw JSON only."""

_PROMPT_TEMPLATE = """## Task
{task}

## Agent Output to Evaluate
{output}

Score the output."""


async def score(task: str, output: str) -> dict[str, float]:
    client = openai.AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )
    resp = await client.chat.completions.create(
        model=settings.primary_model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _PROMPT_TEMPLATE.format(task=task, output=output)},
        ],
        max_tokens=256,
    )
    raw = (resp.choices[0].message.content or "").strip()
    raw = re.sub(r"^```json\s*|```$", "", raw, flags=re.MULTILINE).strip()
    scores = json.loads(raw)
    return {k: float(scores.get(k, 0.0)) for k in _DIMENSIONS}
