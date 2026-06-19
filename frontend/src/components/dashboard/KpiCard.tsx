"use client";
import React from "react";
import { motion } from "framer-motion";
import { ResponsiveContainer, AreaChart, Area } from "recharts";

interface KpiCardProps {
  label: string;
  value: string;
  sublabel?: string;
  accent?: string;            // hex for glow + sparkline
  spark?: number[];           // optional sparkline series
  delta?: { value: string; positive: boolean };
}

/** Glass KPI tile with a soft glow + optional sparkline. */
export function KpiCard({ label, value, sublabel, accent = "#cba6f7", spark, delta }: KpiCardProps) {
  const sparkData = (spark ?? []).map((v, i) => ({ i, v }));
  const gradId = `kpi-${label.replace(/\s+/g, "")}`;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="glass hover-lift relative overflow-hidden p-4"
      style={{ boxShadow: `0 0 0 1px rgba(180,160,232,0.07), 0 8px 40px rgba(0,0,0,0.6), 0 0 24px ${accent}14` }}
    >
      <div className="flex items-start justify-between">
        <span className="text-[10px] uppercase tracking-wider" style={{ color: "#6b6b8a" }}>
          {label}
        </span>
        {delta && (
          <span className="text-[10px] font-mono" style={{ color: delta.positive ? "#a6e3c4" : "#e3a6c9" }}>
            {delta.positive ? "▲" : "▼"} {delta.value}
          </span>
        )}
      </div>
      <div className="mt-1 font-semibold tabular-nums" style={{ fontSize: 26, color: "#e8e8f5" }}>
        {value}
      </div>
      {sublabel && (
        <div className="text-[11px] mt-0.5" style={{ color: "#6b6b8a" }}>{sublabel}</div>
      )}
      {sparkData.length > 1 && (
        <div className="absolute bottom-0 left-0 right-0 h-8 opacity-70">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={sparkData} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={accent} stopOpacity={0.4} />
                  <stop offset="100%" stopColor={accent} stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area type="monotone" dataKey="v" stroke={accent} strokeWidth={1.5}
                    fill={`url(#${gradId})`} isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </motion.div>
  );
}
