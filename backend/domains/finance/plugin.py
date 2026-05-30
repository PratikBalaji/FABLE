"""Finance domain — registers domain-specific agents and pipeline."""
from __future__ import annotations

from ...core.bus import AgentBus, TaskContext
from ...router.model_router import ModelRouter
from ...agents.roles import AnalystAgent, CriticAgent, SynthesizerAgent

PIPELINE = ["analyst", "critic", "synthesizer"]

FINANCE_ANALYST_SYSTEM = """You are a CFA-level financial analyst.
Given a query about a company, market, or instrument, produce a structured analysis:
- Investment Thesis (bull/bear)
- Key Financial Metrics (revenue growth, margins, debt/equity, FCF)
- Risk Factors (macro, sector, company-specific)
- Comparable Peers
- Data Sources Referenced
Use only information provided in context. Flag any knowledge gaps."""

FINANCE_CRITIC_SYSTEM = """You are a risk officer reviewing a financial analysis.
Challenge assumptions, identify data gaps, question projections, highlight regulatory
or ESG risks not addressed, and flag any survivorship bias or cherry-picked metrics.
Be specific and quantitative where possible."""

FINANCE_SYNTH_SYSTEM = """You are a portfolio manager synthesizing a financial analysis.
Produce a final investment memo with:
- Executive Summary (3 sentences max)
- Conviction Level: High / Medium / Low with rationale
- Key Risks to Monitor
- Suggested Next Steps (additional due diligence, catalysts to watch)"""


class FinanceAnalystAgent(AnalystAgent):
    system_prompt = FINANCE_ANALYST_SYSTEM

    def build_prompt(self, ctx: TaskContext) -> str:
        context_block = ctx.metadata.get("retrieved_context", "")
        parts = [f"## Research Query\n{ctx.input}"]
        if context_block:
            parts.append(f"## Filings & Market Data Context\n{context_block}")
        return "\n\n".join(parts)


class FinanceCriticAgent(CriticAgent):
    system_prompt = FINANCE_CRITIC_SYSTEM


class FinanceSynthAgent(SynthesizerAgent):
    system_prompt = FINANCE_SYNTH_SYSTEM


def register(bus: AgentBus, router: ModelRouter) -> None:
    bus.register("analyst", FinanceAnalystAgent(router))
    bus.register("critic", FinanceCriticAgent(router))
    bus.register("synthesizer", FinanceSynthAgent(router))
