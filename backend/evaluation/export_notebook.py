"""Export a F.A.B.L.E. run (or all runs) to a Kaggle-ready .ipynb notebook.

F-033: every emitted text is PII-redacted before it lands in a cell, and export is
ownership-scoped — callers must pass the owning identity_id in multi-user mode, and
records without a matching owner are refused.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import nbformat
from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell

from ..core.config import settings
from ..core.feedback import feedback_store
from ..core.pii import redact_text_sync


def _agent_color(role: str) -> str:
    return {"analyst": "🔵", "critic": "🔴", "synthesizer": "🟢"}.get(role, "⚪")


def _owner_of(run: dict) -> str | None:
    meta = run.get("metadata", {}) or {}
    return meta.get("identity_id") or meta.get("user_id")


def _S(text: str) -> str:
    """Sanitize any text destined for a notebook cell (F-033)."""
    return redact_text_sync(text or "")


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

    # Input (sanitized)
    cells.append(new_markdown_cell(f"## Input\n\n```\n{_S(run.get('metadata', {}).get('input', ''))}\n```"))

    # Agent messages (sanitized)
    for msg in run["messages"]:
        icon = _agent_color(msg["role"])
        cells.append(new_markdown_cell(
            f"## {icon} Agent: `{msg['role'].upper()}`\n\n{_S(msg['content'])}"
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


def export_run(task_id: str, output_dir: str = "./notebooks", *, identity_id: str | None = None) -> Path:
    records = feedback_store.load_all()
    run = next((r for r in records if r["task_id"] == task_id), None)
    if run is None:
        raise ValueError(f"No run found with task_id={task_id}")
    # F-033: ownership check — in multi-user mode an identity may only export its own runs.
    if settings.use_supabase or identity_id is not None:
        owner = _owner_of(run)
        if identity_id is None or owner is None or owner != identity_id:
            raise PermissionError(f"Run {task_id} is not owned by the requesting identity")
    nb = run_to_notebook(run)
    path = Path(output_dir) / f"fable_{task_id[:8]}.ipynb"
    path.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(nb, str(path))
    print(f"Notebook written to {path}")
    return path


def export_all(domain: str | None = None, output_dir: str = "./notebooks", *, identity_id: str | None = None) -> list[Path]:
    records = feedback_store.load_all()
    if domain:
        records = [r for r in records if r["domain"] == domain]
    # F-033: scope to owner in multi-user mode (or whenever an identity is supplied).
    if settings.use_supabase or identity_id is not None:
        records = [r for r in records if _owner_of(r) is not None and _owner_of(r) == identity_id]
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
