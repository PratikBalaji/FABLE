"""Benchmark: compare multi-agent collaboration vs single-agent output."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from ..core.lifecycle import run_task
from ..router.model_router import router as model_router
from ..core.bus import AgentMessage, TaskContext
from .rubric import score


async def _single_agent_run(input_text: str, domain: str) -> str:
    """Run just the analyst (no critic/synthesizer) as a single-agent baseline."""
    from ..agents.roles import AnalystAgent
    agent = AnalystAgent(model_router)
    ctx = TaskContext(task_id="baseline", domain=domain, input=input_text)
    msg: AgentMessage = await agent(ctx)
    return msg.content


async def run_benchmark(test_cases: list[dict[str, Any]], domain: str) -> dict:
    """
    test_cases: list of {"input": str, "label": str}
    Returns per-case and aggregate score comparison.
    """
    results = []

    for case in test_cases:
        text = case["input"]
        label = case.get("label", text[:60])

        # Multi-agent run
        multi_result = await run_task(text, domain)
        multi_output = multi_result["messages"][-1]["content"]  # synthesizer output

        # Single-agent baseline
        single_output = await _single_agent_run(text, domain)

        multi_scores = await score(text, multi_output)
        single_scores = await score(text, single_output)

        results.append({
            "label": label,
            "multi_agent": {"output": multi_output, "scores": multi_scores},
            "single_agent": {"output": single_output, "scores": single_scores},
        })

    def avg(score_dicts: list[dict]) -> dict[str, float]:
        keys = score_dicts[0].keys()
        return {k: sum(d[k] for d in score_dicts) / len(score_dicts) for k in keys}

    multi_avg = avg([r["multi_agent"]["scores"] for r in results])
    single_avg = avg([r["single_agent"]["scores"] for r in results])

    return {
        "domain": domain,
        "n": len(results),
        "multi_agent_avg": multi_avg,
        "single_agent_avg": single_avg,
        "delta": {k: multi_avg[k] - single_avg[k] for k in multi_avg},
        "cases": results,
    }


async def main(test_file: str, domain: str, output_file: str = "benchmark_results.json") -> None:
    cases = json.loads(Path(test_file).read_text())
    results = await run_benchmark(cases, domain)
    Path(output_file).write_text(json.dumps(results, indent=2))
    print(f"Benchmark complete. Results written to {output_file}")
    print(f"Multi-agent avg: {results['multi_agent_avg']}")
    print(f"Single-agent avg: {results['single_agent_avg']}")
    print(f"Delta: {results['delta']}")


if __name__ == "__main__":
    import sys
    asyncio.run(main(sys.argv[1], sys.argv[2]))
