"use client";
import React from "react";
import type { BenchmarkRun } from "../../lib/api";
import { CATEGORIES } from "./theme";

/** Soft heatmap: Monte Carlo consensus by category. */
export function ConsensusHeatmap({ runs }: { runs: BenchmarkRun[] }) {
  const mc = runs.filter((r) => r.mode === "montecarlo");

  const cells = CATEGORIES.map((cat) => {
    const rs = mc.filter((r) => r.category === cat && r.score != null);
    const val = rs.length ? rs.reduce((a, r) => a + (r.score as number), 0) / rs.length : null;
    return { cat, val };
  });

  // soft purple→mint scale, low opacity (no harsh colors)
  const cellColor = (v: number | null): string => {
    if (v == null) return "rgba(12,12,28,0.45)";
    // 0 → muted rose, 0.5 → amber, 1 → mint
    const t = Math.max(0, Math.min(1, v));
    const hue = 0 + t * 150; // rose(0) → mint(150)
    return `hsla(${hue}, 45%, 62%, ${0.18 + t * 0.4})`;
  };

  return (
    <div>
      <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${CATEGORIES.length}, 1fr)` }}>
        {cells.map(({ cat, val }) => (
          <div key={cat} className="rounded-2xl flex flex-col items-center justify-center py-5 transition-all"
               style={{
                 background: cellColor(val),
                 boxShadow: "0 0 0 1px rgba(180,160,232,0.06)",
               }}
               title={`${cat}: ${val == null ? "pending" : val.toFixed(3)}`}>
            <span className="text-[15px] font-semibold tabular-nums" style={{ color: "#e8e8f5" }}>
              {val == null ? "—" : val.toFixed(2)}
            </span>
            <span className="text-[9px] uppercase tracking-wider mt-1 capitalize" style={{ color: "#9494aa" }}>
              {cat}
            </span>
          </div>
        ))}
      </div>
      <div className="text-[10px] mt-2" style={{ color: "#45455d" }}>
        Mean inter-model cosine consensus per category · higher = more wording-robust.
      </div>
    </div>
  );
}
