"""
Report generation — turns raw benchmark results into LaTeX tables, publication figures, and a
markdown summary. Numbers are computed from the results; nothing is hand-entered.
"""
from __future__ import annotations

from pathlib import Path

from .stats import bootstrap_ci, bootstrap_diff_ci, mcnemar_exact, judge_validation

_TABLES = Path("paper/tables")
_FIGURES = Path("paper/figures")


def _acc(rows: list[dict]) -> list[float]:
    return [1.0 if r["correct"] else 0.0 for r in rows]


def compute_summary(by_cond: dict[str, list[dict]]) -> dict:
    """Per-condition accuracy + CI, paired std-vs-adv McNemar + diff CI, judge validation."""
    summary: dict = {"conditions": {}, "pairwise": {}, "judge": {}}
    for cond, rows in by_cond.items():
        ci = bootstrap_ci(_acc(rows))
        summary["conditions"][cond] = {
            "n": len(rows),
            "accuracy": round(ci["mean"], 4),
            "ci_lo": round(ci["lo"], 4),
            "ci_hi": round(ci["hi"], 4),
            "mean_latency_s": round(sum(r["latency_s"] for r in rows) / max(len(rows), 1), 1),
        }

    if "standard" in by_cond and "adversarial" in by_cond:
        # align by item id for the paired test
        s = {r["id"]: r for r in by_cond["standard"]}
        a = {r["id"]: r for r in by_cond["adversarial"]}
        ids = sorted(set(s) & set(a))
        sc = [s[i]["correct"] for i in ids]
        ac = [a[i]["correct"] for i in ids]
        summary["pairwise"]["std_vs_adv"] = {
            **mcnemar_exact(sc, ac),
            **bootstrap_diff_ci([float(x) for x in sc], [float(x) for x in ac]),
            "n_paired": len(ids),
        }

    for cond in ("standard", "adversarial"):
        if cond in by_cond:
            rows = by_cond[cond]
            summary["judge"][cond] = judge_validation(
                [r["verdict_good"] for r in rows], [r["correct"] for r in rows]
            )
    return summary


# ---------------------------------------------------------------------------
# LaTeX tables
# ---------------------------------------------------------------------------

def _fmt_pct(x: float) -> str:
    return f"{100*x:.1f}\\%"


def latex_accuracy_table(summary: dict) -> str:
    order = [c for c in ("single", "standard", "adversarial") if c in summary["conditions"]]
    label = {"single": "Single-LLM", "standard": "Standard", "adversarial": "Adversarial"}
    lines = [
        "\\begin{table}[t]", "\\centering",
        "\\caption{GSM8K accuracy with 95\\% bootstrap CIs and mean latency.}",
        "\\label{tab:gsm8k-acc}",
        "\\begin{tabular}{@{}lcccr@{}}", "\\toprule",
        "Mode & $n$ & Accuracy & 95\\% CI & Latency (s) \\\\", "\\midrule",
    ]
    for c in order:
        s = summary["conditions"][c]
        lines.append(
            f"{label[c]} & {s['n']} & {_fmt_pct(s['accuracy'])} & "
            f"[{_fmt_pct(s['ci_lo'])}, {_fmt_pct(s['ci_hi'])}] & {s['mean_latency_s']} \\\\"
        )
    lines += ["\\bottomrule", "\\end{tabular}", "\\end{table}", ""]
    return "\n".join(lines)


def latex_judge_table(summary: dict) -> str:
    lines = [
        "\\begin{table}[t]", "\\centering",
        "\\caption{LLM verdict validated against GSM8K ground truth "
        "(verdict $\\in\\{$PASS, ACCEPT$\\}$ as a predictor of correctness).}",
        "\\label{tab:judge-val}",
        "\\begin{tabular}{@{}lccccc@{}}", "\\toprule",
        "Mode & $n$ & Precision & Recall & F1 & Cohen's $\\kappa$ \\\\", "\\midrule",
    ]
    for cond, lab in (("standard", "Standard"), ("adversarial", "Adversarial")):
        j = summary["judge"].get(cond)
        if j:
            lines.append(f"{lab} & {j['n']} & {j['precision']:.2f} & {j['recall']:.2f} & "
                         f"{j['f1']:.2f} & {j['kappa']:.2f} \\\\")
    lines += ["\\bottomrule", "\\end{tabular}", "\\end{table}", ""]
    return "\n".join(lines)


def latex_significance_note(summary: dict) -> str:
    p = summary.get("pairwise", {}).get("std_vs_adv")
    if not p:
        return ""
    return (
        f"% Paired McNemar (n={p['n_paired']}): b01={p['b01']}, b10={p['b10']}, "
        f"p={p['p_value']}. Adv-minus-Std accuracy diff={p['diff']:+.3f} "
        f"95\\% CI [{p['lo']:+.3f}, {p['hi']:+.3f}].\n"
    )


# ---------------------------------------------------------------------------
# Figures (matplotlib if available; else a pgfplots .tex fallback)
# ---------------------------------------------------------------------------

def accuracy_figure(summary: dict) -> str:
    _FIGURES.mkdir(parents=True, exist_ok=True)
    order = [c for c in ("single", "standard", "adversarial") if c in summary["conditions"]]
    labels = {"single": "Single-LLM", "standard": "Standard", "adversarial": "Adversarial"}
    accs = [summary["conditions"][c]["accuracy"] for c in order]
    los = [summary["conditions"][c]["accuracy"] - summary["conditions"][c]["ci_lo"] for c in order]
    his = [summary["conditions"][c]["ci_hi"] - summary["conditions"][c]["accuracy"] for c in order]
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(4.2, 3.0))
        x = range(len(order))
        ax.bar(x, accs, yerr=[los, his], capsize=5, color=["#9aa0a6", "#4c78a8", "#9b5fb0"])
        ax.set_xticks(list(x))
        ax.set_xticklabels([labels[c] for c in order])
        ax.set_ylabel("GSM8K accuracy")
        ax.set_ylim(0, 1)
        ax.set_title("Accuracy with 95% bootstrap CI")
        fig.tight_layout()
        out = _FIGURES / "accuracy.pdf"
        fig.savefig(out)
        plt.close(fig)
        return str(out)
    except Exception:  # noqa: BLE001 — matplotlib missing or headless issue
        # pgfplots fallback (.tex) — compiles on Overleaf with no extra dep
        coords = " ".join(f"({labels[c]},{summary['conditions'][c]['accuracy']:.3f})" for c in order)
        tex = (
            "% pgfplots fallback — \\usepackage{pgfplots} on Overleaf\n"
            "\\begin{tikzpicture}\\begin{axis}[ybar, ymin=0, ymax=1, symbolic x coords={"
            + ",".join(labels[c] for c in order) + "}, xtick=data, ylabel={GSM8K accuracy}]\n"
            f"\\addplot coordinates {{{coords}}};\n\\end{{axis}}\\end{{tikzpicture}}\n"
        )
        (_FIGURES / "accuracy.tex").write_text(tex, encoding="utf-8")
        return str(_FIGURES / "accuracy.tex")


def write_all(summary: dict) -> dict:
    _TABLES.mkdir(parents=True, exist_ok=True)
    (_TABLES / "gsm8k_accuracy.tex").write_text(
        latex_accuracy_table(summary) + "\n" + latex_significance_note(summary), encoding="utf-8")
    (_TABLES / "judge_validation.tex").write_text(latex_judge_table(summary), encoding="utf-8")
    fig = accuracy_figure(summary)
    return {"tables": ["paper/tables/gsm8k_accuracy.tex", "paper/tables/judge_validation.tex"],
            "figure": fig}


def markdown_summary(summary: dict, meta: dict) -> str:
    lines = ["\n\n---\n\n## Phase 19 — GSM8K Benchmark\n",
             f"**Run:** {meta.get('timestamp','')} · provider={meta.get('provider')} "
             f"· model={meta.get('model')} · n={meta.get('n')} × {meta.get('seeds')} seed(s)\n",
             "| Mode | n | Accuracy | 95% CI | Latency (s) |",
             "|------|---|----------|--------|-------------|"]
    for c in ("single", "standard", "adversarial"):
        s = summary["conditions"].get(c)
        if s:
            lines.append(f"| {c} | {s['n']} | {100*s['accuracy']:.1f}% | "
                         f"[{100*s['ci_lo']:.1f}, {100*s['ci_hi']:.1f}] | {s['mean_latency_s']} |")
    p = summary.get("pairwise", {}).get("std_vs_adv")
    if p:
        lines.append(f"\n**McNemar std-vs-adv:** b01={p['b01']}, b10={p['b10']}, "
                     f"p={p['p_value']}; adv−std diff {p['diff']:+.3f} "
                     f"95% CI [{p['lo']:+.3f}, {p['hi']:+.3f}] (n={p['n_paired']}).")
    for cond in ("standard", "adversarial"):
        j = summary["judge"].get(cond)
        if j:
            lines.append(f"\n**Judge validation ({cond}):** precision {j['precision']:.2f}, "
                         f"recall {j['recall']:.2f}, F1 {j['f1']:.2f}, κ {j['kappa']:.2f} "
                         f"(TP={j['tp']} FP={j['fp']} FN={j['fn']} TN={j['tn']}).")
    return "\n".join(lines) + "\n"
