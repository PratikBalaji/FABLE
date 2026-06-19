"use client";
import React from "react";
import type { BenchmarkRun } from "../../lib/api";

/** Dataset feasibility: sample size, Wilson CI, McNemar power note. */
export function FeasibilityCard({ runs }: { runs: BenchmarkRun[] }) {
  const done = runs.filter((r) => r.status === "done").length;
  const pending = runs.filter((r) => r.status === "pending").length;
  const n = done;
  const ciWidth = n > 0 ? Math.round(1.96 * Math.sqrt(0.25 / n) * 100) : null;

  return (
    <div className="text-[13px]" style={{ color: "#cdd6f4", lineHeight: 1.7 }}>
      <div className="flex gap-4 mb-3">
        <Stat label="Completed" value={String(done)} color="#a6e3c4" />
        <Stat label="Pending" value={String(pending)} color="#f0c9a6" />
        {ciWidth != null && <Stat label="95% CI" value={`±${ciWidth}%`} color="#9db4f0" />}
      </div>
      <p className="mt-0" style={{ color: "#9494aa" }}>
        Paired prompts across Standard/Adversarial enable a valid{" "}
        <span style={{ color: "#cba6f7" }}>McNemar</span> comparison. At n=20/mode the test has
        ~80% power to detect a 20% pass-rate gap (α=0.05). Treat results as directional until the
        full 60-case suite runs. Utilities: <code style={{ color: "#cba6f7" }}>scripts/benchmark/stats.py</code>.
      </p>
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider" style={{ color: "#6b6b8a" }}>{label}</div>
      <div className="text-[20px] font-semibold tabular-nums" style={{ color }}>{value}</div>
    </div>
  );
}
