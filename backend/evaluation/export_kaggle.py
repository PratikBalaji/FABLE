"""Kaggle benchmark dataset + reproducer notebook export for F.A.B.L.E.

Builds a Kaggle-ready artifact from the 60 Preliminary Eval Test Cases:
  - benchmark_v1.csv     (60 rows: id, mode, category, prompt, score, verdict,
                          latency, tokens_in, tokens_out, cost_usd)
  - benchmark_v1.jsonl   (raw run records)
  - fable_benchmark_v1.ipynb  (reproducer notebook)

Then pushes both to the user's Kaggle account via the Kaggle Public API v1.

Credential handling:
    Accepts ``{"username": str, "key": str}`` at request time (BYOK-style,
    identical to the OpenRouter BYOK pattern in core/credentials.py).
    Credentials are NEVER logged or persisted outside the encrypted store.

Usage (from backend route)::

    from backend.evaluation.export_kaggle import build_and_push

    result = await build_and_push(
        kaggle_creds={"username": "alice", "key": "..."},
        dataset_slug="fable-benchmark-v1",
    )
    # result: {"dataset_url": "...", "kernel_url": "..."}
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import textwrap
import tempfile
from pathlib import Path
from typing import Any

import nbformat
from nbformat.v4 import new_notebook, new_code_cell, new_markdown_cell

from ..core.pii import redact_text_sync

logger = logging.getLogger(__name__)

_YAML_PATH = Path("benchmarks/benchmark_v1.yaml")
_RESULTS_GLOB = "data/benchmarks/results/benchmark_v1_*.json"


# ---------------------------------------------------------------------------
# Dataset builders
# ---------------------------------------------------------------------------

def _load_benchmark_data() -> dict[str, Any]:
    """Load benchmark yaml + latest results JSON (if any)."""
    try:
        import yaml
    except ImportError:
        raise RuntimeError("PyYAML required: pip install pyyaml")

    if not _YAML_PATH.exists():
        raise FileNotFoundError(f"Benchmark not found at {_YAML_PATH}")

    with open(_YAML_PATH, encoding="utf-8") as f:
        bench = yaml.safe_load(f)

    # Try to find the most recent results JSON
    results: dict[str, list] = {"standard": [], "adversarial": [], "montecarlo": []}
    result_files = sorted(Path(".").glob(_RESULTS_GLOB))
    if result_files:
        with open(result_files[-1], encoding="utf-8") as f:
            raw = json.load(f)
        results["standard"] = raw.get("standard", [])
        results["adversarial"] = raw.get("adversarial", [])
        results["montecarlo"] = raw.get("montecarlo", [])

    return {"bench": bench, "results": results}


def build_csv(data: dict[str, Any]) -> str:
    """Build the benchmark CSV (60 rows) as a string."""
    bench = data["bench"]
    results = data["results"]
    finished = bench.get("finished_runs", [])
    shared = bench.get("shared_questions", [])
    mc_cases = bench.get("montecarlo", [])

    # Build lookup dicts for results
    std_by_id = {r.get("id"): r for r in results["standard"]}
    adv_by_id = {r.get("id"): r for r in results["adversarial"]}
    mc_by_id  = {r.get("id"): r for r in results["montecarlo"]}

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=[
        "run_id", "mode", "category", "prompt",
        "verdict", "score", "rounds", "latency_s",
        "tokens_in", "tokens_out", "cost_usd", "status",
    ])
    writer.writeheader()

    # Finished Phase-14 rows
    for run in finished:
        writer.writerow({
            "run_id": run["run_id"],
            "mode": run["mode"],
            "category": run["category"],
            "prompt": redact_text_sync(run["prompt"])[:200],
            "verdict": run["verdict"],
            "score": run["score"],
            "rounds": run.get("rounds") or "",
            "latency_s": run["latency_s"],
            "tokens_in": "",
            "tokens_out": "",
            "cost_usd": "",
            "status": "done",
        })

    # Shared questions — standard
    for q in shared:
        r = std_by_id.get(q["id"], {})
        writer.writerow({
            "run_id": f"STD-{q['id']}",
            "mode": "standard",
            "category": q["category"],
            "prompt": redact_text_sync(q["prompt"])[:200],
            "verdict": r.get("outcome", "PENDING"),
            "score": r.get("score", ""),
            "rounds": "",
            "latency_s": r.get("elapsed", ""),
            "tokens_in": (r.get("usage") or {}).get("input", ""),
            "tokens_out": (r.get("usage") or {}).get("output", ""),
            "cost_usd": r.get("cost_usd", ""),
            "status": "done" if r else "pending",
        })

    # Shared questions — adversarial
    for q in shared:
        r = adv_by_id.get(q["id"], {})
        writer.writerow({
            "run_id": f"ADV-{q['id']}",
            "mode": "adversarial",
            "category": q["category"],
            "prompt": redact_text_sync(q["prompt"])[:200],
            "verdict": r.get("outcome", "PENDING"),
            "score": r.get("score", ""),
            "rounds": r.get("rounds", ""),
            "latency_s": r.get("elapsed", ""),
            "tokens_in": (r.get("usage") or {}).get("input", ""),
            "tokens_out": (r.get("usage") or {}).get("output", ""),
            "cost_usd": r.get("cost_usd", ""),
            "status": "done" if r else "pending",
        })

    # Monte Carlo
    for mc in mc_cases:
        r = mc_by_id.get(mc["id"], {})
        writer.writerow({
            "run_id": mc["id"],
            "mode": "montecarlo",
            "category": mc["category"],
            "prompt": redact_text_sync(mc.get("prompt", ""))[:200],
            "verdict": f"consensus={r.get('consensus','PENDING')}",
            "score": r.get("consensus", ""),
            "rounds": f"{mc['n_variants']} variants",
            "latency_s": r.get("elapsed", ""),
            "tokens_in": "",
            "tokens_out": "",
            "cost_usd": r.get("cost_usd", ""),
            "status": "done" if r.get("outcome") == "OK" else "pending",
        })

    return buf.getvalue()


def build_jsonl(data: dict[str, Any]) -> str:
    """Build raw JSONL of all run records."""
    bench = data["bench"]
    results = data["results"]
    lines = []
    for run in bench.get("finished_runs", []):
        lines.append(json.dumps(run))
    for mode, key in [("standard", "standard"), ("adversarial", "adversarial"), ("montecarlo", "montecarlo")]:
        for r in results.get(key, []):
            lines.append(json.dumps({"mode": mode, **r}))
    return "\n".join(lines)


def build_reproducer_notebook(data: dict[str, Any]) -> nbformat.NotebookNode:
    """Build a Kaggle-ready reproducer notebook."""
    bench = data["bench"]
    nb = new_notebook()
    cells = []

    cells.append(new_markdown_cell(textwrap.dedent("""\
        # F.A.B.L.E. — 60 Preliminary Eval Test Cases: Reproducer Notebook

        **Framework for Adversarial Benchmarking & Logic Evaluation**

        This notebook loads the F.A.B.L.E. benchmark dataset and reproduces the evaluation
        runs against the three pipeline modes: Standard, Adversarial, and Monte Carlo.

        > ⚠️ Requires a running F.A.B.L.E. backend (see Quick Start) and valid API keys.
    """)))

    cells.append(new_code_cell(textwrap.dedent("""\
        # Install dependencies
        !pip install -q httpx pyyaml pandas matplotlib seaborn
        print("Dependencies installed.")
    """)))

    cells.append(new_code_cell(textwrap.dedent("""\
        import pandas as pd
        import json, pathlib

        # Load the benchmark dataset (bundled with this Kaggle dataset)
        df = pd.read_csv("/kaggle/input/fable-benchmark-v1/benchmark_v1.csv")
        print(f"Loaded {len(df)} rows across {df['mode'].nunique()} modes")
        df.head(10)
    """)))

    cells.append(new_markdown_cell("## Configuration\n\nSet your F.A.B.L.E. backend URL and API key."))

    cells.append(new_code_cell(textwrap.dedent("""\
        import os
        BASE_URL = os.environ.get("FABLE_API_URL", "http://localhost:8000")
        HEADERS = {"X-FABLE-Request": "1", "Content-Type": "application/json"}
        print(f"Backend: {BASE_URL}")
    """)))

    cells.append(new_markdown_cell("## Run Standard Mode (20 prompts)"))

    cells.append(new_code_cell(textwrap.dedent("""\
        import httpx, time

        PROMPTS_STD = df[df['mode'].isin(['standard', 'done']) & (df['status'] == 'pending')][
            ['run_id', 'category', 'prompt']
        ].to_dict('records')

        std_results = []
        with httpx.Client(timeout=240) as client:
            for row in PROMPTS_STD[:5]:  # demo: first 5; remove [:5] for full run
                t0 = time.time()
                resp = client.post(f"{BASE_URL}/run",
                                   json={"input": row["prompt"]},
                                   headers=HEADERS)
                elapsed = round(time.time() - t0, 1)
                data = resp.json()
                verdict = data.get("verdict") or {}
                std_results.append({
                    "run_id": row["run_id"],
                    "category": row["category"],
                    "outcome": verdict.get("verdict", "ERROR"),
                    "score": verdict.get("score", 0),
                    "latency_s": elapsed,
                })
                print(f"[{row['run_id']}] {verdict.get('verdict','?')} {verdict.get('score',0):.0%} {elapsed}s")

        std_df = pd.DataFrame(std_results)
        std_df
    """)))

    cells.append(new_markdown_cell("## Score & Latency Visualisation"))

    cells.append(new_code_cell(textwrap.dedent("""\
        import matplotlib.pyplot as plt

        finished = df[df['status'] == 'done'].copy()
        finished['score'] = pd.to_numeric(finished['score'], errors='coerce')

        fig, axes = plt.subplots(1, 2, figsize=(12, 4))

        # Score by mode
        finished.groupby('mode')['score'].mean().plot(
            kind='bar', ax=axes[0], color=['#89b4fa','#cba6f7','#a6e3a1'])
        axes[0].set_title('Mean Score by Mode (Phase-14 finished)')
        axes[0].set_ylabel('Score')
        axes[0].set_ylim(0, 1)

        # Latency by mode
        finished.groupby('mode')['latency_s'].mean().plot(
            kind='bar', ax=axes[1], color=['#89b4fa','#cba6f7','#a6e3a1'])
        axes[1].set_title('Mean Latency by Mode (s)')
        axes[1].set_ylabel('Seconds')

        plt.tight_layout()
        plt.savefig('fable_benchmark_chart.png', dpi=150)
        plt.show()
        print("Chart saved.")
    """)))

    cells.append(new_markdown_cell("## Leaderboard (Score × Category × Mode)"))

    cells.append(new_code_cell(textwrap.dedent("""\
        import seaborn as sns

        pivot = finished.pivot_table(
            values='score', index='category', columns='mode', aggfunc='mean')
        print(pivot.round(2))

        plt.figure(figsize=(8, 4))
        sns.heatmap(pivot, annot=True, fmt='.0%', cmap='RdYlGn', vmin=0, vmax=1)
        plt.title('F.A.B.L.E. Score Heatmap — Category × Mode')
        plt.tight_layout()
        plt.savefig('fable_heatmap.png', dpi=150)
        plt.show()
    """)))

    nb.cells = cells
    nb.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    return nb


# ---------------------------------------------------------------------------
# Kaggle API push
# ---------------------------------------------------------------------------

async def push_to_kaggle(
    kaggle_creds: dict[str, str],
    dataset_slug: str,
    tmp_dir: Path,
) -> dict[str, str]:
    """Push dataset + notebook to Kaggle via their REST API.

    Uses kaggle library (pip install kaggle) with creds supplied at call time
    (never written to ~/.kaggle/kaggle.json to avoid polluting shared envs).
    """
    try:
        from kaggle.api.kaggle_api_extended import KaggleApiExtended
    except ImportError:
        raise RuntimeError("kaggle package not installed: pip install kaggle")

    username = kaggle_creds["username"]
    key = kaggle_creds["key"]

    # Inject creds into environment for the Kaggle SDK
    import os
    env_backup = {}
    try:
        for k, v in [("KAGGLE_USERNAME", username), ("KAGGLE_KEY", key)]:
            env_backup[k] = os.environ.get(k)
            os.environ[k] = v

        api = KaggleApiExtended()
        api.authenticate()

        # Dataset metadata
        meta = {
            "title": "F.A.B.L.E. 60 Preliminary Eval Test Cases",
            "id": f"{username}/{dataset_slug}",
            "licenses": [{"name": "CC0-1.0"}],
            "resources": [
                {"path": "benchmark_v1.csv",  "description": "60-row benchmark results"},
                {"path": "benchmark_v1.jsonl", "description": "Raw run records"},
            ],
        }
        meta_path = tmp_dir / "dataset-metadata.json"
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        def _push() -> dict[str, str]:
            try:
                # Create or version the dataset
                api.dataset_create_version(
                    folder=str(tmp_dir),
                    version_notes="Auto-pushed by F.A.B.L.E. export",
                    quiet=True,
                    convert_to_csv=False,
                    delete_old_versions=False,
                )
                dataset_url = f"https://www.kaggle.com/datasets/{username}/{dataset_slug}"

                # Push notebook as a kernel
                kernel_meta = {
                    "id": f"{username}/fable-benchmark-v1-reproducer",
                    "title": "F.A.B.L.E. Benchmark Reproducer",
                    "code_file": "fable_benchmark_v1.ipynb",
                    "language": "python",
                    "kernel_type": "notebook",
                    "is_private": False,
                    "enable_gpu": False,
                    "enable_internet": True,
                    "dataset_sources": [f"{username}/{dataset_slug}"],
                }
                kernel_meta_path = tmp_dir / "kernel-metadata.json"
                kernel_meta_path.write_text(json.dumps(kernel_meta, indent=2), encoding="utf-8")

                api.kernels_push(folder=str(tmp_dir), quiet=True)
                kernel_url = (f"https://www.kaggle.com/code/{username}/"
                              "fable-benchmark-v1-reproducer")
                return {"dataset_url": dataset_url, "kernel_url": kernel_url}
            except Exception as exc:
                logger.error("kaggle_push_failed: %s", exc)
                raise RuntimeError(f"Kaggle push failed: {exc}") from exc

        return await asyncio.get_event_loop().run_in_executor(None, _push)
    finally:
        # Restore env
        for k, v in env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

async def build_and_push(
    kaggle_creds: dict[str, str],
    dataset_slug: str = "fable-benchmark-v1",
) -> dict[str, str]:
    """Build dataset artifacts and push to Kaggle. Returns URLs."""
    data = _load_benchmark_data()

    with tempfile.TemporaryDirectory(prefix="fable_kaggle_") as tmp:
        tmp_dir = Path(tmp)

        # Write CSV
        (tmp_dir / "benchmark_v1.csv").write_text(build_csv(data), encoding="utf-8")

        # Write JSONL
        (tmp_dir / "benchmark_v1.jsonl").write_text(build_jsonl(data), encoding="utf-8")

        # Write notebook
        nb = build_reproducer_notebook(data)
        nb_path = tmp_dir / "fable_benchmark_v1.ipynb"
        nbformat.write(nb, str(nb_path))

        logger.info("kaggle_artifacts_built tmp=%s", tmp)

        # Push
        urls = await push_to_kaggle(kaggle_creds, dataset_slug, tmp_dir)

    logger.info("kaggle_push_complete dataset=%s kernel=%s",
                urls.get("dataset_url"), urls.get("kernel_url"))
    return urls
