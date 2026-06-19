"use client";
import React from "react";
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from "recharts";
import type { BenchmarkRun } from "../../lib/api";
import { modeColor, glassTooltip, axisTick, PALETTE } from "./theme";

/** Latency vs score scatter, coloured by mode — shows the cost-for-reliability trade. */
export function LatencyDistribution({ runs }: { runs: BenchmarkRun[] }) {
  const pts = runs
    .filter((r) => r.latency_s != null && r.score != null)
    .map((r) => ({
      x: r.latency_s as number,
      y: Math.round((r.score! <= 1 ? r.score! * 100 : r.score!)),
      mode: r.mode,
      id: r.run_id,
    }));

  if (!pts.length) {
    return <div className="text-[12px] py-8 text-center" style={{ color: "#6b6b8a" }}>
      No completed runs match the current filters.
    </div>;
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <ScatterChart margin={{ top: 10, right: 12, bottom: 8, left: -8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={PALETTE.grid} />
        <XAxis type="number" dataKey="x" name="Latency" unit="s" tick={axisTick}
               axisLine={false} tickLine={false} />
        <YAxis type="number" dataKey="y" name="Score" unit="%" domain={[0, 100]}
               tick={axisTick} axisLine={false} tickLine={false} />
        <ZAxis range={[80, 80]} />
        <Tooltip contentStyle={glassTooltip} cursor={{ strokeDasharray: "3 3", stroke: PALETTE.grid }} />
        <Scatter data={pts} isAnimationActive={false}>
          {pts.map((p, i) => (
            <Cell key={i} fill={modeColor(p.mode)} fillOpacity={0.7} />
          ))}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  );
}
