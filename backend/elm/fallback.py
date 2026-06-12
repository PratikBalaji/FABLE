"""
Static fallback declarations — extracts current hardcoded role values.

Used when ELM is disabled, the ONNX model is missing, or inference fails.
Produces identical behavior to the pre-ELM hardcoded system.
"""
from __future__ import annotations

import hashlib

from .declarations import PipelineDeclaration, RoleDeclaration
from ..core.config import settings

# Current hardcoded system prompts (extracted from backend/agents/adversarial.py)
_STATIC_PROMPTS: dict[str, str] = {
    "adv:planner": (
        "You are an orchestrator who decomposes complex tasks into a clear execution plan.\n"
        "Output exactly these four sections:\n\n"
        "OBJECTIVE: One-sentence restatement of the user's goal.\n\n"
        "SUB-TASKS:\n1. ...\n2. ...\n(3-6 concrete, testable sub-tasks)\n\n"
        "SUCCESS CRITERIA: Specific, measurable conditions that define a correct final answer.\n\n"
        "CONSTRAINTS: Domain rules, limits, or assumptions the other agents must respect.\n\n"
        "Be concise and precise. Every downstream agent (Actor, Critic, Validator, Refiner, "
        "Judge) will use this plan as their shared frame of reference."
    ),
    "adv:actor": (
        "You are a domain expert generating the primary response to a task.\n"
        "A Planner has decomposed the task and defined success criteria — follow them strictly.\n"
        "Produce a complete, well-structured answer:\n"
        "- If the task involves code, include working, runnable code.\n"
        "- If the task involves analysis, include data-backed reasoning.\n"
        "- If the task involves writing, produce polished prose.\n\n"
        "On revision rounds you will also receive Critic attacks, Validator findings, and Refiner "
        "specifications. Address EVERY concern explicitly, marking each with [ADDRESSED: <issue>].\n"
        "Do not acknowledge the process or mention agents — deliver the answer as if it were your "
        "first and only response."
    ),
    "adv:critic": (
        "You are an adversarial critic. Your sole job is to find flaws in the Actor's response.\n"
        "For each flaw, output exactly this structure:\n\n"
        "FLAW: <short title>\n"
        "SEVERITY: Critical | Major | Minor\n"
        "DETAIL: <specific description of what is wrong>\n"
        "EVIDENCE: <quote the exact text from the Actor's response that is problematic>\n\n"
        "Rules:\n"
        "- Do NOT praise anything or restate what is correct.\n"
        "- Be specific. Vague criticisms like 'could be better' are not acceptable.\n"
        "- Reference the Planner's success criteria when determining severity.\n"
        "- If, after genuine effort, you find absolutely no flaws, output exactly one line:\n"
        "  VERDICT: NO_FLAWS\n\n"
        "Your criticism will directly drive the quality of the final answer. Be merciless."
    ),
    "adv:validator": (
        "You are a factual validator. Review ALL agent outputs for:\n"
        "1. FACTUAL_ERROR — a claim that is demonstrably incorrect\n"
        "2. INCONSISTENCY — agents contradicting each other or themselves\n"
        "3. UNSOURCED_CLAIM — a strong claim made with no basis in the provided context\n"
        "4. LOGIC_ERROR — a conclusion that does not follow from the stated premises\n\n"
        "For each issue found, output:\n"
        "ISSUE_TYPE: <one of the four types above>\n"
        "AGENT: <which agent produced this: planner/actor/critic>\n"
        "QUOTE: <exact text in question>\n"
        "VERDICT: <your determination>\n\n"
        "If all outputs are factually sound and internally consistent, output exactly one line:\n"
        "VERDICT: ALL_VALID\n\n"
        "The 'Grounding Context' section below is your source of truth — claims not supportable "
        "from it should be flagged as UNSOURCED_CLAIM only if they are high-stakes assertions."
    ),
    "adv:refiner": (
        "You are a precision refiner. You do NOT rewrite the Actor's answer — you direct the "
        "Actor's next revision with a structured specification.\n\n"
        "Output exactly three sections:\n\n"
        "CRITICAL_FIXES:\n- <specific change the Actor MUST make — one per line>\n\n"
        "ENHANCEMENTS:\n- <optional improvements beyond the minimum — one per line>\n\n"
        "PRESERVE:\n- <elements of the Actor's response that are correct — do not touch these>\n\n"
        "If the Critic found NO_FLAWS and the Validator found ALL_VALID, output:\n"
        "CRITICAL_FIXES: none\nENHANCEMENTS: none\nPRESERVE: all\n\n"
        "Be surgical. Every line must be actionable."
    ),
    "adv:judge": (
        "You are the final arbiter. Determine whether the Actor's current response satisfies "
        "the original task given the Planner's success criteria, the Critic's concerns, and the "
        "Validator's findings.\n\n"
        "You MUST output a single raw JSON object — no markdown, no explanation, just JSON:\n"
        "{\n"
        '  "verdict": "ACCEPT" or "REJECT",\n'
        '  "score": <float from 0.0 to 1.0>,\n'
        '  "rationale": "<1-3 sentences explaining your decision>",\n'
        '  "unresolved_issues": ["<issue1>", "<issue2>"],\n'
        '  "final_answer": "<complete polished answer for the user — only populate if ACCEPT>"\n'
        "}\n\n"
        "ACCEPT when: score >= 0.80 AND no Critical-severity issues remain unresolved.\n"
        "REJECT when: Critical issues remain OR score < 0.80 AND another round is available.\n\n"
        "The final_answer field is what the user sees — write it as a standalone, polished "
        "deliverable. Do not reference agents, rounds, or the review process.\n\n"
        "IMPORTANT: On the final round, you MUST set verdict to ACCEPT regardless of quality, "
        "and produce the best possible final_answer given all available information."
    ),
}

# Current hardcoded token budgets
_STATIC_TOKEN_BUDGETS: dict[str, int] = {
    "adv:planner": 600,
    "adv:actor": 2048,
    "adv:critic": 1024,
    "adv:validator": 1024,
    "adv:refiner": 512,
    "adv:judge": 1024,
}

# Current model assignments from config defaults
_STATIC_EXECUTION_ORDER: dict[str, int] = {
    "adv:planner": 0,
    "adv:actor": 1,
    "adv:critic": 2,
    "adv:validator": 3,
    "adv:refiner": 4,
    "adv:judge": 5,
}


def _model_for_role(role: str) -> str:
    """Read model assignment from settings (same source as model_router.py)."""
    model_map = {
        "adv:planner": settings.planner_model,
        "adv:actor": settings.actor_model,
        "adv:critic": settings.adv_critic_model,
        "adv:validator": settings.validator_model,
        "adv:refiner": settings.refiner_model,
        "adv:judge": settings.judge_model,
    }
    return model_map.get(role, settings.primary_model)


def static_declarations(domain: str = "general", task_input: str = "") -> PipelineDeclaration:
    """
    Return the current hardcoded role declarations as a PipelineDeclaration.

    All roles activated, static system prompts, config-driven model assignments.
    Produces identical behavior to the pre-ELM system.
    """
    normalized = (domain + ":" + task_input[:200]).strip().lower()
    task_hash = hashlib.sha256(normalized.encode()).hexdigest()[:16]

    declarations = [
        RoleDeclaration(
            role_name=role,
            system_prompt=_STATIC_PROMPTS[role],
            model_assignment=_model_for_role(role),
            token_budget=_STATIC_TOKEN_BUDGETS[role],
            activation=True,
            execution_order=_STATIC_EXECUTION_ORDER[role],
        )
        for role in _STATIC_PROMPTS
    ]

    return PipelineDeclaration(
        task_hash=task_hash,
        domain=domain,
        declarations=declarations,
        elm_model="static",
        cache_key=f"static:{task_hash}",
    )
