"use client";
import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

export interface StatusPillData {
  isLoading: boolean;
  verdict?: { label: string; score: number; accepted: boolean } | null;
  model?: string;
  totalRuns?: number;
  taskId?: string;
  recycled?: { similarity: number; goldenRunId: string } | null;
}

/**
 * One adaptive status pill. Shows the single most relevant live state
 * (running → verdict → model). Click expands a glass popover with the rest.
 */
export function StatusPill(d: StatusPillData) {
  const [open, setOpen] = useState(false);

  // Priority: running > verdict > model > idle
  let primary: React.ReactNode = null;
  let tint = "#9494aa";
  if (d.isLoading) {
    primary = <span>● running…</span>;
    tint = "#cba6f7";
  } else if (d.verdict) {
    tint = d.verdict.accepted ? "#a6e3c4" : "#e3a6c9";
    primary = <span>{d.verdict.accepted ? "✓" : "✗"} {Math.round(d.verdict.score * 100)}%</span>;
  } else if (d.model) {
    primary = <span>{d.model.split("/").pop()}</span>;
  } else {
    primary = <span style={{ color: "#45455d" }}>idle</span>;
  }

  const hasDetail = !!(d.model || d.totalRuns || d.taskId || d.recycled);

  return (
    <div className="relative">
      <button
        onClick={() => hasDetail && setOpen((o) => !o)}
        className="text-[10px] font-mono px-2.5 py-1 rounded-full transition-all"
        style={{
          background: `${tint}12`,
          color: tint,
          boxShadow: `0 0 0 1px ${tint}28`,
          cursor: hasDetail ? "pointer" : "default",
        }}
        title={d.verdict ? "Click for run details" : undefined}
      >
        {primary}{hasDetail && <span style={{ opacity: 0.5 }}> ▸</span>}
      </button>

      <AnimatePresence>
        {open && hasDetail && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.96 }}
            transition={{ type: "spring", stiffness: 420, damping: 30 }}
            className="absolute right-0 mt-2 glass p-3 z-50 text-[11px] font-mono whitespace-nowrap"
            style={{ minWidth: 160 }}
          >
            {d.model && <Row label="model" value={d.model.split("/").pop() ?? ""} />}
            {d.totalRuns != null && d.totalRuns > 0 && <Row label="runs" value={String(d.totalRuns)} />}
            {d.taskId && <Row label="task" value={`#${d.taskId.slice(0, 6)}`} />}
            {d.recycled && <Row label="recycled" value={`♻ ${Math.round(d.recycled.similarity * 100)}%`} color="#f0c9a6" />}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Row({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex items-center justify-between gap-4 py-0.5">
      <span style={{ color: "#6b6b8a" }}>{label}</span>
      <span style={{ color: color ?? "#cdd6f4" }}>{value}</span>
    </div>
  );
}
