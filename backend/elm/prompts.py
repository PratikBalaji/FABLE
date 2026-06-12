"""
Meta-prompts for the ELM role declaration engine.

The ELM receives a structured prompt describing the task, domain, available roles,
and available models, then outputs a JSON array of RoleDeclarations.
"""
from __future__ import annotations

from ..core.config import settings


def build_declaration_prompt(task_input: str, domain: str) -> str:
    """
    Build the meta-prompt that instructs the ELM to generate role declarations.

    The prompt is designed for structured JSON output from small instruction-tuned
    models (Phi-3-mini). It's constrained and explicit to minimize parse failures.
    """
    # Truncate task input to fit 4k context window
    truncated = task_input[:1500] if len(task_input) > 1500 else task_input

    available_models = {
        "planner": settings.planner_model,
        "actor": settings.actor_model,
        "critic": settings.adv_critic_model,
        "validator": settings.validator_model,
        "refiner": settings.refiner_model,
        "judge": settings.judge_model,
    }
    model_list = "\n".join(f"  - {k}: {v}" for k, v in available_models.items())

    return f"""You are a pipeline orchestrator for an adversarial multi-LLM system called F.A.B.L.E.
Your job is to configure each agent role for the given task.

TASK:
{truncated}

DOMAIN: {domain}

AVAILABLE ROLES (with adv: prefix):
  - adv:planner (execution_order=0): Decomposes task into sub-tasks and success criteria
  - adv:actor (execution_order=1): Generates the primary response
  - adv:critic (execution_order=2): Adversarially attacks the actor's response
  - adv:validator (execution_order=3): Checks factual accuracy and consistency
  - adv:refiner (execution_order=4): Produces improvement specification for actor
  - adv:judge (execution_order=5): Final arbitration — ACCEPT or REJECT

AVAILABLE MODELS:
{model_list}

OUTPUT FORMAT — a JSON array with exactly one object per role:
[
  {{
    "role_name": "adv:planner",
    "system_prompt": "task-specific system prompt (2-4 sentences)",
    "model_assignment": "model-id from available models",
    "token_budget": 600,
    "activation": true,
    "execution_order": 0
  }}
]

RULES:
1. adv:planner, adv:actor, and adv:judge MUST always have activation=true
2. For simple factual queries, adv:critic and adv:validator MAY be deactivated (activation=false)
3. For code tasks, adv:validator system_prompt should focus on code correctness, not factual claims
4. For creative/writing tasks, adv:critic should be less adversarial, more constructive
5. For analysis/research tasks, adv:validator should emphasize sourcing and evidence
6. Token budgets: planner 400-800, actor 1024-4096, critic 512-1536, validator 512-1536, refiner 256-768, judge 512-1536
7. System prompts should be specific to the task domain, not generic
8. Keep system prompts concise (2-4 sentences each)

Output ONLY the JSON array. No explanation, no markdown fences."""


# Domain-specific hints that the ELM can use to specialize prompts
DOMAIN_HINTS: dict[str, str] = {
    "code_review": "Focus on code correctness, security, performance. Validator checks for bugs.",
    "finance": "Emphasize numerical accuracy, sourcing of claims, regulatory compliance.",
    "research": "Prioritize factual accuracy, citation quality, logical rigor.",
    "creative": "Balance quality with creative freedom. Critic should be constructive.",
    "general": "Standard adversarial review. All roles at default intensity.",
}
