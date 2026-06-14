"""
Monte Carlo Experiment Mode (Phase 13).

Prompt robustness testing + inter-model consensus measurement with self-improvement.

Flow:
  1. Paraphrase generator (gpt-4o-mini) produces N prompt variants.
  2. Each variant is sent to M models in parallel.
  3. All responses are embedded (text-embedding-3-small).
  4. Cosine similarity matrix computed across all (variant × model) responses.
  5. Consensus score + divergence pairs returned.
  6. Consensus signal fed into knowledge_engine as model reliability update.

Reuses: embed_batch, ModelRouter, knowledge_engine, pii.redact.
Cost:   ~4 variants × 3 models × 500 tokens ≈ 6k tokens/run (~$0.006 at OR prices).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

import numpy as np

from ..core.config import settings
from ..core.embeddings import embed_batch
from ..core.knowledge_engine import knowledge_engine
from ..router.model_router import ModelRouter, router as default_router

# Default models sampled — chosen for diversity (reasoning + generation + speed)
_DEFAULT_MODELS: list[str] = [
    settings.planner_model,   # Claude Sonnet — structured reasoning
    settings.actor_model,     # GPT-4o — strong generation
    settings.adv_critic_model, # Claude Haiku — fast adversarial
]

_PARAPHRASE_SYSTEM = (
    "You are a prompt paraphrase generator. Given a user prompt, produce exactly "
    "{n} distinct paraphrased variants. Requirements:\n"
    "- Variant 1: formal, precise academic phrasing\n"
    "- Variant 2: informal, conversational\n"
    "- Variant 3: adversarial — reframe as a challenge or edge-case probe\n"
    "- Variant 4+: direct question form, progressively shorter\n"
    "Output ONLY a JSON array of strings: [\"variant1\", \"variant2\", ...]\n"
    "No markdown, no explanation, no extra keys."
)

_RESPONSE_SYSTEM = (
    "You are a helpful, precise AI assistant. Answer the user's question clearly and concisely."
)


@dataclass
class MonteCarloResult:
    prompt: str
    variants: list[str]
    models: list[str]
    responses: list[list[str]]          # [variant_idx][model_idx] = response text
    similarity_matrix: list[list[float]] # (n_variants * n_models) × (n_variants * n_models)
    consensus_score: float              # mean pairwise cosine similarity (0–1)
    divergence_pairs: list[dict]        # pairs where similarity < threshold
    per_model_consensus: dict[str, float]  # avg consensus per model


async def _generate_variants(
    prompt: str,
    n: int,
    router: ModelRouter,
) -> list[str]:
    """Generate n paraphrased variants of the prompt."""
    import json
    import re

    try:
        resp = await router.complete(
            system=_PARAPHRASE_SYSTEM.format(n=n),
            user=prompt,
            force_model=settings.secondary_model,  # gpt-4o-mini: cheap + reliable JSON
        )
        raw = (resp.content or "").strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        variants = json.loads(raw)
        if isinstance(variants, list) and all(isinstance(v, str) for v in variants):
            return variants[:n]
    except Exception:
        pass
    # Fallback: return slight rewording using string manipulation
    return [
        prompt,
        f"Please explain: {prompt}",
        f"What are the implications of: {prompt}",
        f"Briefly address: {prompt}",
    ][:n]


async def run_monte_carlo(
    prompt: str,
    n_variants: int = 4,
    models: list[str] | None = None,
    router: ModelRouter | None = None,
    divergence_threshold: float = 0.70,
) -> MonteCarloResult:
    """Run Monte Carlo prompt robustness experiment.

    Args:
        prompt:               Original user prompt (already PII-redacted by route layer).
        n_variants:           Number of paraphrased variants (1–8, default 4).
        models:               Model IDs to compare. Defaults to [planner, actor, critic].
        router:               ModelRouter (uses per-user BYOK if provided by route layer).
        divergence_threshold: Pairs below this cosine similarity are flagged as divergent.
    """
    _router = router or default_router
    _models = models or _DEFAULT_MODELS
    n_variants = max(1, min(8, n_variants))

    # Step 1: Generate paraphrase variants
    variants = await _generate_variants(prompt, n=n_variants, router=_router)

    # Step 2: Fan-out — all (variant, model) pairs in parallel
    async def _query(variant: str, model: str) -> str:
        try:
            resp = await _router.complete(
                system=_RESPONSE_SYSTEM,
                user=variant,
                force_model=model,
            )
            return (resp.content or "").strip()
        except Exception:
            return ""

    tasks = [_query(v, m) for v in variants for m in _models]
    flat_responses = await asyncio.gather(*tasks)

    # Reshape into [variant][model]
    n_models = len(_models)
    responses: list[list[str]] = [
        list(flat_responses[i * n_models : (i + 1) * n_models])
        for i in range(len(variants))
    ]

    # Step 3: Embed all responses (non-fatal — degrade to empty matrix on failure)
    all_texts = list(flat_responses)
    try:
        embeddings = embed_batch(all_texts)  # list of 384-d vectors
    except Exception:  # noqa: BLE001
        embeddings = []

    if not embeddings:
        emb_matrix = np.zeros((1, 1), dtype=np.float32)
    else:
        emb_matrix = np.array(embeddings, dtype=np.float32)
        # L2-normalise for cosine similarity via dot product
        norms = np.linalg.norm(emb_matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        emb_matrix = emb_matrix / norms

    # Step 4: Full cosine similarity matrix
    sim_matrix = (emb_matrix @ emb_matrix.T).tolist()  # (N×N)
    n_total = len(all_texts)

    # Step 5: Consensus score (mean of upper-triangle, excluding diagonal)
    if n_total > 1:
        upper = [
            sim_matrix[i][j]
            for i in range(n_total)
            for j in range(i + 1, n_total)
        ]
        consensus_score = float(np.mean(upper)) if upper else 0.0
    else:
        consensus_score = 1.0

    # Divergence pairs
    divergence_pairs: list[dict] = []
    for i in range(n_total):
        for j in range(i + 1, n_total):
            sim = sim_matrix[i][j]
            if sim < divergence_threshold:
                vi, mi = divmod(i, n_models)
                vj, mj = divmod(j, n_models)
                divergence_pairs.append({
                    "idx_a": i, "idx_b": j,
                    "similarity": round(sim, 4),
                    "variant_a": variants[vi] if vi < len(variants) else "",
                    "model_a": _models[mi],
                    "variant_b": variants[vj] if vj < len(variants) else "",
                    "model_b": _models[mj],
                })

    # Per-model consensus (avg similarity of this model's responses vs all others)
    per_model_consensus: dict[str, float] = {}
    for m_idx, model in enumerate(_models):
        model_indices = [v_idx * n_models + m_idx for v_idx in range(len(variants))]
        other_indices = [k for k in range(n_total) if k not in model_indices]
        if model_indices and other_indices:
            sims = [sim_matrix[i][j] for i in model_indices for j in other_indices]
            per_model_consensus[model] = float(np.mean(sims)) if sims else 0.0

    # Step 6: Feed signal into knowledge engine (non-fatal)
    try:
        for model in _models:
            knowledge_engine.ingest_run(
                input_text=prompt,
                output=f"[monte_carlo consensus={consensus_score:.3f}]",
                domain="experiment",
                model_used=model,
                scores={"consensus": consensus_score, "divergence": 1.0 - consensus_score},
            )
    except Exception:  # noqa: BLE001
        pass

    return MonteCarloResult(
        prompt=prompt,
        variants=variants,
        models=_models,
        responses=responses,
        similarity_matrix=sim_matrix,
        consensus_score=round(consensus_score, 4),
        divergence_pairs=divergence_pairs,
        per_model_consensus={k: round(v, 4) for k, v in per_model_consensus.items()},
    )
