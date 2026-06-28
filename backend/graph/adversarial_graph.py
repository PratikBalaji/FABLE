"""
Phase 19 — LangGraph orchestrator for the adversarial round loop.

This is a *parallel view* of the same protocol the native AgentBus runs, not a
reimplementation: every node wraps the already-registered agent handler via
`bus.dispatch`, so prompts, models, token budgets, and ELM declarations are identical.
Only the orchestration layer changes — which is exactly what the LangChain-vs-LangGraph
research comparison isolates.

The Planner runs once in the caller (adversarial_lifecycle); this module orchestrates
only the per-round loop and returns the same triple the native loop produces:
    (round_messages, judge_result, rounds_completed)

Graph shape (per the real dependency DAG, width-1):
    actor → critic → validator → refiner → judge
                                              │ conditional edge
                                   ACCEPT / rounds exhausted → END
                                   REJECT  → back to actor (next round)

The `messages` state channel uses an `operator.add` reducer — the fan-in that
accumulates every node's output into the round transcript.

ELM dynamic roles: the node set + edges are built per run from `round_roles`
(`PipelineDeclaration.active_round_roles()`), so ELM-declared pipelines are honored.
`adv:judge` is a mandatory role; if it is somehow absent the graph degrades to a single
linear pass with an empty verdict.

If langgraph is not installed, importing `run_rounds_langgraph` raises ImportError and
the caller falls back to the native asyncio loop.
"""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict

import structlog

from ..core.bus import AgentMessage, TaskContext, bus

log = structlog.get_logger()

# Importing here so a missing optional dep surfaces as ImportError at call import time,
# which adversarial_lifecycle catches to fall back to asyncio.
from langgraph.graph import END, StateGraph  # noqa: E402


class _RoundState(TypedDict, total=False):
    ctx: TaskContext
    messages: Annotated[list[AgentMessage], operator.add]
    round_num: int
    judge_result: dict
    rounds_completed: int


def _node_name(role: str) -> str:
    """LangGraph 1.x forbids ':' in node names — map 'adv:actor' → 'adv_actor'."""
    return role.replace(":", "_")


def _make_node(role: str, first_role: str):
    """Build an async LangGraph node that dispatches one agent role via the bus."""
    from ..core.adversarial_lifecycle import _parse_judge_output

    async def _node(state: _RoundState) -> dict:
        ctx = state["ctx"]
        round_num = state.get("round_num", 0)
        # The first role of a round stamps the round index agents read from metadata.
        if role == first_role:
            ctx.metadata["adversarial_round"] = round_num

        msg = await bus.dispatch(role, ctx)
        out: dict = {"messages": [msg]}

        if role == "adv:judge":
            jr = _parse_judge_output(msg.content)
            out["judge_result"] = jr
            out["rounds_completed"] = round_num + 1
            out["round_num"] = round_num + 1  # advance; router decides continue/end
            log.info(
                "adversarial_judge_verdict",
                round=round_num + 1,
                verdict=jr.get("verdict"),
                score=jr.get("score"),
            )
        return out

    return _node


def _build_graph(round_roles: list[str], max_rounds: int):
    first_role = round_roles[0]
    first_node = _node_name(first_role)
    builder = StateGraph(_RoundState)

    for role in round_roles:
        builder.add_node(_node_name(role), _make_node(role, first_role))

    builder.set_entry_point(first_node)
    # Linear edges between consecutive roles (the width-1 dependency chain).
    for a, b in zip(round_roles, round_roles[1:]):
        builder.add_edge(_node_name(a), _node_name(b))

    if "adv:judge" in round_roles:
        def _route(state: _RoundState) -> str:
            jr = state.get("judge_result", {})
            if jr.get("verdict") == "ACCEPT" or state.get("round_num", 0) >= max_rounds:
                return "end"
            return "continue"

        builder.add_conditional_edges(
            _node_name("adv:judge"), _route, {"continue": first_node, "end": END}
        )
    else:
        builder.add_edge(_node_name(round_roles[-1]), END)

    return builder.compile()


async def run_rounds_langgraph(
    task_ctx: TaskContext,
    round_roles: list[str],
    max_rounds: int,
    *,
    task_id: str,
) -> tuple[list[AgentMessage], dict, int]:
    """Run the adversarial round loop through a LangGraph StateGraph.

    Mirrors the native loop's contract. Recursion limit is sized to the worst case
    (every round runs all roles) plus headroom.
    """
    graph = _build_graph(round_roles, max_rounds)
    recursion_limit = max_rounds * (len(round_roles) + 1) + 10

    log.info("adversarial_langgraph_start", task_id=task_id, max_rounds=max_rounds)
    final_state = await graph.ainvoke(
        {"ctx": task_ctx, "messages": [], "round_num": 0,
         "judge_result": {}, "rounds_completed": 0},
        config={"recursion_limit": recursion_limit},
    )

    return (
        list(final_state.get("messages", [])),
        final_state.get("judge_result", {}),
        final_state.get("rounds_completed", 0),
    )
