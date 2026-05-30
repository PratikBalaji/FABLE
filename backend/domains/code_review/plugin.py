"""Code Review domain — registers domain-specific agents and pipeline."""
from __future__ import annotations

from ...core.bus import AgentBus, TaskContext
from ...router.model_router import ModelRouter
from ...agents.roles import AnalystAgent, CriticAgent, SynthesizerAgent

PIPELINE = ["analyst", "critic", "synthesizer"]

CODE_ANALYST_SYSTEM = """You are an expert code reviewer acting as analyst.
Review the submitted code or diff for: correctness, security vulnerabilities,
performance bottlenecks, style guide violations (PEP 8), and test coverage gaps.
Structure output as:
- Summary
- Issues Found (severity: critical/major/minor)
- Positive Observations
- Open Questions"""

CODE_CRITIC_SYSTEM = """You are a senior engineer critiquing a code review analysis.
Identify: missed bugs, incorrect severity ratings, false positives, missing context,
and any security issues overlooked. Be specific — reference line-level concerns where possible."""

CODE_SYNTH_SYSTEM = """You are a tech lead synthesizing a code review.
Produce a final review comment ready to post on a pull request. Include:
- Overall verdict (Approve / Request Changes / Comment)
- Prioritized action items (numbered)
- Inline suggestions where helpful
- Encouragement for what was done well"""


class CodeReviewAnalystAgent(AnalystAgent):
    system_prompt = CODE_ANALYST_SYSTEM

    def build_prompt(self, ctx: TaskContext) -> str:
        context_block = ctx.metadata.get("retrieved_context", "")
        parts = [f"## Code / Diff to Review\n```\n{ctx.input}\n```"]
        if context_block:
            parts.append(f"## Style Guide Context\n{context_block}")
        return "\n\n".join(parts)


class CodeReviewCriticAgent(CriticAgent):
    system_prompt = CODE_CRITIC_SYSTEM


class CodeReviewSynthAgent(SynthesizerAgent):
    system_prompt = CODE_SYNTH_SYSTEM


def register(bus: AgentBus, router: ModelRouter) -> None:
    bus.register("analyst", CodeReviewAnalystAgent(router))
    bus.register("critic", CodeReviewCriticAgent(router))
    bus.register("synthesizer", CodeReviewSynthAgent(router))
