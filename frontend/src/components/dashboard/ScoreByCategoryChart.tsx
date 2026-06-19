"use client";
import React from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import type { BenchmarkRun } from "../../lib/api";
import { CATEGORIES, modeColor, glassTooltip, axisTick, PALETTE } from "./theme";

/** Grouped bars: mean score per category, split by mode. */
export function ScoreByCategoryChart({ runs }: { runs: BenchmarkRun[] }) {
  const data = CATEGORIES.map((cat) => {
    const row: Record<string, number | string> = { category: cat };
    for (const mode of ["standard", "adversarial"] as const) {
      const rs = runs.filter((r) => r.category === cat && r.mode === mode && r.score != null);
      if (rs.length) {
        const mean = rs.reduce((a, r) => a + (r.score! <= 1 ? r.score! * 100 : r.score!), 0) / rs.length;
        row[mode] = Math.round(mean);
      }
    }
    return row;
  });

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} barGap={4} barCategoryGap="28%">
        <defs>
          {(["standard", "adversarial"] as const).map((m) => (
            <linearGradient key={m} id={`grad-${m}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={modeColor(m)} stopOpacity={0.95} />
              <stop offset="100%" stopColor={modeColor(m)} stopOpacity={0.45} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={PALETTE.grid} vertical={false} />
        <XAxis dataKey="category" tick={axisTick} axisLine={false} tickLine={false} className="capitalize" />
        <YAxis tick={axisTick} axisLine={false} tickLine={false} domain={[0, 100]} unit="%" />
        <Tooltip contentStyle={glassTooltip} cursor={{ fill: "rgba(203,166,247,0.05)" }} />
        <Legend wrapperStyle={{ fontSize: 11, color: PALETTE.subtle }} iconType="circle" />
        <Bar dataKey="standard" fill="url(#grad-standard)" radius={[6, 6, 0, 0]} name="Standard" />
        <Bar dataKey="adversarial" fill="url(#grad-adversarial)" radius={[6, 6, 0, 0]} name="Adversarial" />
      </BarChart>
    </ResponsiveContainer>
  );
}
