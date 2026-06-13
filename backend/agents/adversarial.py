"""
Adversarial multi-LLM agent roles.

Each agent is bound to a specific LLM via complete_for_role(), which reads from
ROLE_MODEL_MAP in the router. The adv: prefix on role names prevents collision
with the standard pipeline agents registered on the same AgentBus.

Pipeline order: planner → actor → critic → validator → refiner → judge
The planner runs once; the remaining five repeat for up to max_rounds iterations,
controlled by the Judge's ACCEPT/REJECT verdict.
"""
from __future__ import annotations

from ..core.bus import AgentMessage, TaskContext
from .base import BaseAgent

# Per-role token budgets — keeps costs predictable
_TOKEN_BUDGETS: dict[str, int] = {
    "adv:planner":   600,
    "adv:actor":     2048,
    "adv:critic":    1024,
    "adv:validator": 1024,
    "adv:refiner":   512,
    # P14: bumped 1024→2560 — judge emits verdict+rationale+unresolved+final_answer
    # in one JSON blob; 1024 truncated mid-string on long answers → parse failures.
    "adv:judge":     2560,
}


class BaseAdversarialAgent(BaseAgent):
    """
    Base for all adversarial pipeline agents.
    Routes to role-specific LLM and embeds round metadata in the message.

    When ELM declarations are present in TaskContext.metadata["elm_declarations"],
    the agent reads its own RoleDeclaration for task-aware system_prompt, token_budget,
    and model_assignment. Falls back to class-level defaults when no declaration exists.
    """

    def _get_declaration(self, ctx: TaskContext):
        """Look up this agent's ELM declaration from TaskContext, if present."""
        pipeline_decl = ctx.metadata.get("elm_declarations")
        if pipeline_decl is None:
            return None
        return pipeline_decl.get_declaration(self.role)

    async def __call__(self, ctx: TaskContext) -> AgentMessage:
        prompt = self.build_prompt(ctx)

        # ELM-aware: read dynamic declaration if available, else static defaults
        decl = self._get_declaration(ctx)
        system = decl.system_prompt if decl else self.system_prompt
        max_tok = decl.token_budget if decl else _TOKEN_BUDGETS.get(self.role, 1024)
        model_override = decl.model_assignment if decl else None

        # Per-user router (multi-user mode) wins; fall back to the registration-time singleton.
        router = ctx.metadata.get("router") or self.router
        response = await router.complete_for_role(
            role=self.role,
            system=system,
            user=prompt,
            max_tokens=max_tok,
            model_override=model_override,
        )
        return AgentMessage(
            role=self.role,
            content=response.content,
            metadata={
                "model": response.model,
                "usage": response.usage,
                "round": ctx.metadata.get("adversarial_round", 0),
                "elm_driven": decl is not None,
            },
        )

    def _last_by_role(self, ctx: TaskContext, role: str) -> str:
        """Return the most recent message content from a given role."""
        return next(
            (m.content for m in reversed(ctx.history) if m.role == role), ""
        )


# ---------------------------------------------------------------------------
# Planner — runs once; sets strategy for all downstream agents
# ---------------------------------------------------------------------------

class PlannerAgent(BaseAdversarialAgent):
    role = "adv:planner"
    system_prompt = (
        "You are an orchestrator who decomposes complex tasks into a clear execution plan.\n"
        "Output exactly these four sections:\n\n"
        "OBJECTIVE: One-sentence restatement of the user's goal.\n\n"
        "SUB-TASKS:\n1. ...\n2. ...\n(3–6 concrete, testable sub-tasks)\n\n"
        "SUCCESS CRITERIA: Specific, measurable conditions that define a correct final answer.\n\n"
        "CONSTRAINTS: Domain rules, limits, or assumptions the other agents must respect.\n\n"
        "Be concise and precise. Every downstream agent (Actor, Critic, Validator, Refiner, "
        "Judge) will use this plan as their shared frame of reference."
    )

    def build_prompt(self, ctx: TaskContext) -> str:
        parts = [f"## User Task\n{ctx.input}"]
        context = ctx.metadata.get("retrieved_context", "")
        if context:
            parts.append(f"## Relevant Prior Knowledge\n{context}")
        parts.append(f"## Domain\n{ctx.domain}")
        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Actor — generates the primary answer; revises it in subsequent rounds
# ---------------------------------------------------------------------------

class ActorAgent(BaseAdversarialAgent):
    role = "adv:actor"
    system_prompt = (
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
    )

    def build_prompt(self, ctx: TaskContext) -> str:
        plan = self._last_by_role(ctx, "adv:planner")
        prev_actor = self._last_by_role(ctx, "adv:actor")
        critic = self._last_by_role(ctx, "adv:critic")
        validator = self._last_by_role(ctx, "adv:validator")
        refiner = self._last_by_role(ctx, "adv:refiner")

        parts = [
            f"## Original Task\n{ctx.input}",
            f"## Execution Plan\n{plan}",
        ]
        if prev_actor:
            parts.append(f"## Your Previous Response\n{prev_actor}")
        if critic:
            parts.append(f"## Critic's Attacks (address ALL of these)\n{critic}")
        if validator:
            parts.append(f"## Validator's Findings (fix ALL factual issues)\n{validator}")
        if refiner:
            parts.append(f"## Refiner's Improvement Specification\n{refiner}")
        parts.append("Produce your response now.")
        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Adversarial Critic — attacks the Actor's output; finds every flaw
# ---------------------------------------------------------------------------

class AdversarialCriticAgent(BaseAdversarialAgent):
    role = "adv:critic"
    system_prompt = (
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
    )

    def build_prompt(self, ctx: TaskContext) -> str:
        plan = self._last_by_role(ctx, "adv:planner")
        actor = self._last_by_role(ctx, "adv:actor")
        round_num = ctx.metadata.get("adversarial_round", 0)
        return (
            f"## Original Task\n{ctx.input}\n\n"
            f"## Planner's Success Criteria\n{plan}\n\n"
            f"## Actor's Response (Round {round_num + 1})\n{actor}\n\n"
            "Attack the Actor's response. Find every flaw."
        )


# ---------------------------------------------------------------------------
# Validator — checks ALL agents' outputs for factual accuracy and consistency
# ---------------------------------------------------------------------------

class ValidatorAgent(BaseAdversarialAgent):
    role = "adv:validator"
    system_prompt = (
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
    )

    def build_prompt(self, ctx: TaskContext) -> str:
        plan = self._last_by_role(ctx, "adv:planner")
        actor = self._last_by_role(ctx, "adv:actor")
        critic = self._last_by_role(ctx, "adv:critic")
        context = ctx.metadata.get("retrieved_context", "")

        parts = [f"## Original Task\n{ctx.input}"]
        if context:
            parts.append(f"## Grounding Context (source of truth)\n{context}")
        parts += [
            f"## Planner Output\n{plan}",
            f"## Actor Output\n{actor}",
            f"## Critic Output\n{critic}",
            "Validate all of the above.",
        ]
        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Refiner — produces a surgical improvement specification for the Actor
# ---------------------------------------------------------------------------

class RefinerAgent(BaseAdversarialAgent):
    role = "adv:refiner"
    system_prompt = (
        "You are a precision refiner. You do NOT rewrite the Actor's answer — you direct the "
        "Actor's next revision with a structured specification.\n\n"
        "Output exactly three sections:\n\n"
        "CRITICAL_FIXES:\n- <specific change the Actor MUST make — one per line>\n\n"
        "ENHANCEMENTS:\n- <optional improvements beyond the minimum — one per line>\n\n"
        "PRESERVE:\n- <elements of the Actor's response that are correct — do not touch these>\n\n"
        "If the Critic found NO_FLAWS and the Validator found ALL_VALID, output:\n"
        "CRITICAL_FIXES: none\nENHANCEMENTS: none\nPRESERVE: all\n\n"
        "Be surgical. Every line must be actionable."
    )

    def build_prompt(self, ctx: TaskContext) -> str:
        actor = self._last_by_role(ctx, "adv:actor")
        critic = self._last_by_role(ctx, "adv:critic")
        validator = self._last_by_role(ctx, "adv:validator")
        return (
            f"## Original Task\n{ctx.input}\n\n"
            f"## Actor's Current Response\n{actor}\n\n"
            f"## Critic's Attack\n{critic}\n\n"
            f"## Validator's Findings\n{validator}\n\n"
            "Produce the improvement specification."
        )


# ---------------------------------------------------------------------------
# Judge — final arbitration; decides ACCEPT or REJECT; writes final answer
# ---------------------------------------------------------------------------

class JudgeAgent(BaseAdversarialAgent):
    role = "adv:judge"
    system_prompt = (
        "You are the final arbiter. Determine whether the Actor's current response satisfies "
        "the original task given the Planner's success criteria, the Critic's concerns, and the "
        "Validator's findings.\n\n"
        "You MUST output a single raw JSON object — no markdown, no explanation, just JSON:\n"
        "{\n"
        '  "verdict": "ACCEPT" or "REJECT",\n'
        '  "score": <float from 0.0 to 1.0>,\n'
        '  "rationale": "<1–3 sentences explaining your decision>",\n'
        '  "unresolved_issues": ["<issue1>", "<issue2>"],\n'
        '  "final_answer": "<complete polished answer for the user — only populate if ACCEPT>"\n'
        "}\n\n"
        "ACCEPT when: score >= 0.80 AND no Critical-severity issues remain unresolved.\n"
        "REJECT when: Critical issues remain OR score < 0.80 AND another round is available.\n\n"
        "The final_answer field is what the user sees — write it as a standalone, polished "
        "deliverable. Do not reference agents, rounds, or the review process.\n\n"
        "IMPORTANT: On the final round, you MUST set verdict to ACCEPT regardless of quality, "
        "and produce the best possible final_answer given all available information."
    )

    def build_prompt(self, ctx: TaskContext) -> str:
        plan = self._last_by_role(ctx, "adv:planner")
        actor = self._last_by_role(ctx, "adv:actor")
        critic = self._last_by_role(ctx, "adv:critic")
        validator = self._last_by_role(ctx, "adv:validator")
        refiner = self._last_by_role(ctx, "adv:refiner")
        round_num = ctx.metadata.get("adversarial_round", 0)
        max_rounds = ctx.metadata.get("adversarial_max_rounds", 2)
        is_final = (round_num + 1) >= max_rounds

        parts = [
            f"## Original Task\n{ctx.input}",
            f"## Planner's Success Criteria\n{plan}",
            f"## Actor's Response\n{actor}",
            f"## Critic's Findings\n{critic}",
            f"## Validator's Findings\n{validator}",
            f"## Refiner's Specification\n{refiner}",
            (
                f"## Round\nThis is round {round_num + 1} of {max_rounds}. "
                + ("THIS IS THE FINAL ROUND — you MUST output verdict: ACCEPT."
                   if is_final else
                   "Another round is available if you REJECT.")
            ),
        ]
        return "\n\n".join(parts)
