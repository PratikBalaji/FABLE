"""Export a F.A.B.L.E. run (or all runs) to a Kaggle-ready .ipynb notebook."""
from __future__ import annotations

import textwrap
from pathlib import Path

import nbformat
from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell

from ..core.feedback import feedback_store


def _agent_color(role: str) -> str:
    return {"analyst": "🔵", "critic": "🔴", "synthesizer": "🟢"}.get(role, "⚪")


def run_to_notebook(run: dict) -> nbformat.NotebookNode:
    nb = new_notebook()
    cells = []

    # Title
    cells.append(new_markdown_cell(
        f"# F.A.B.L.E. Run — {run['domain'].replace('_', ' ').title()}\n"
        f"**Task ID:** `{run['task_id']}`  \n"
        f"**Pipeline:** {' → '.join(run['pipeline'])}  \n"
        f"**Timestamp:** {run['messages'][0]['timestamp'] if run['messages'] else 'N/A'}"
    ))

    # Setup cell
    cells.append(new_code_cell(textwrap.dedent("""
        # F.A.B.L.E. Demo — run this cell to install dependencies
        # !pip install anthropic openai sentence-transformers faiss-cpu fastapi uvicorn
        print("F.A.B.L.E. — Federated Agent Bus & Lifecycle Engine")
    """).strip()))

    # Input
    cells.append(new_markdown_cell(f"## Input\n\n```\n{run.get('metadata', {}).get('input', '')}\n```"))

    # Agent messages
    for msg in run["messages"]:
        icon = _agent_color(msg["role"])
        cells.append(new_markdown_cell(
            f"## {icon} Agent: `{msg['role'].upper()}`\n\n{msg['content']}"
        ))

    # Scores
    if run.get("scores"):
        scores_md = "\n".join(f"- **{k}**: {v:.2f}" for k, v in run["scores"].items())
        cells.append(new_markdown_cell(f"## Evaluation Scores\n\n{scores_md}"))

    nb.cells = cells
    nb.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    return nb


def export_run(task_id: str, output_dir: str = "./notebooks") -> Path:
    records = feedback_store.load_all()
    run = next((r for r in records if r["task_id"] == task_id), None)
    if run is None:
        raise ValueError(f"No run found with task_id={task_id}")
    nb = run_to_notebook(run)
    path = Path(output_dir) / f"fable_{task_id[:8]}.ipynb"
    path.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(nb, str(path))
    print(f"Notebook written to {path}")
    return path


def export_all(domain: str | None = None, output_dir: str = "./notebooks") -> list[Path]:
    records = feedback_store.load_all()
    if domain:
        records = [r for r in records if r["domain"] == domain]
    paths = []
    for run in records:
        nb = run_to_notebook(run)
        fname = f"fable_{run['domain']}_{run['task_id'][:8]}.ipynb"
        path = Path(output_dir) / fname
        path.parent.mkdir(parents=True, exist_ok=True)
        nbformat.write(nb, str(path))
        paths.append(path)
    print(f"Exported {len(paths)} notebooks to {output_dir}")
    return paths
