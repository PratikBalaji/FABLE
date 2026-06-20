"use client";
import React from "react";
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from "recharts";
import type { BenchmarkRun } from "../../lib/api";
import { modeColor, glassTooltip, axisTick, PALETTE, MODES } from "./theme";

/** Per-mode cost bar + cumulative cost line. */
export function CostBreakdown({ runs }: { runs: BenchmarkRun[] }) {
  let cumulative = 0;
  const data = MODES.map((mode) => {
    const cost = runs
      .filter((r) => r.mode === mode && r.cost_usd != null)
      .reduce((a, r) => a + (r.cost_usd as number), 0);
    cumulative += cost;
    return {
      mode,
      cost: Number(cost.toFixed(4)),
      cumulative: Number(cumulative.toFixed(4)),
    };
  });

  const allZero = data.every((d) => d.cost === 0);

  return (
    <div>
      {allZero && (
        <div className="text-[11px] mb-2" style={{ color: "#6b6b8a" }}>
          No priced runs yet — cost populates once the benchmark runner executes.
        </div>
      )}
      <ResponsiveContainer width="100%" height={210}>
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: -8 }}>
          <defs>
            <linearGradient id="cost-grad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={PALETTE.accent} stopOpacity={0.9} />
              <stop offset="100%" stopColor={PALETTE.accent} stopOpacity={0.4} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={PALETTE.grid} vertical={false} />
          <XAxis dataKey="mode" tick={axisTick} axisLine={false} tickLine={false} className="capitalize" />
          <YAxis tick={axisTick} axisLine={false} tickLine={false} unit="$" />
          <Tooltip contentStyle={glassTooltip} cursor={{ fill: "rgba(203,166,247,0.05)" }}
                   formatter={(v: number) => `$${v.toFixed(4)}`} />
          <Legend wrapperStyle={{ fontSize: 11, color: PALETTE.subtle }} iconType="circle" />
          <Bar dataKey="cost" fill="url(#cost-grad)" radius={[6, 6, 0, 0]} name="Cost / mode" />
          <Line type="monotone" dataKey="cumulative" stroke={modeColor("montecarlo")}
                strokeWidth={2} dot={{ r: 3 }} name="Cumulative" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
