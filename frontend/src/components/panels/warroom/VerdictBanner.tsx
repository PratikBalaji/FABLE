"use client";
import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { VerdictMeta } from "@/lib/api";

const VERDICT_STYLE: Record<string, { color: string; bg: string; label: string }> = {
  PASS:   { color: "#a6e3a1", bg: "rgba(166,227,161,0.08)", label: "✓ PASS"   },
  WARN:   { color: "#f9e2af", bg: "rgba(249,226,175,0.08)", label: "⚠ WARN"   },
  FAIL:   { color: "#f38ba8", bg: "rgba(243,139,168,0.08)", label: "✗ FAIL"   },
  ACCEPT: { color: "#a6e3a1", bg: "rgba(166,227,161,0.08)", label: "✓ ACCEPT" },
  REJECT: { color: "#f38ba8", bg: "rgba(243,139,168,0.08)", label: "✗ REJECT" },
};

const DEFAULT_STYLE = { color: "#6c7086", bg: "rgba(108,112,134,0.08)", label: "? UNKNOWN" };

interface VerdictBannerProps {
  verdict: VerdictMeta | null;
  runSummary: string;
  finalAnswer: string;
  isLoading: boolean;
}

export function VerdictBanner({ verdict, runSummary, finalAnswer, isLoading }: VerdictBannerProps) {
  const show = !isLoading && verdict && verdict.verdict !== "UNKNOWN";
  const style = verdict ? (VERDICT_STYLE[verdict.verdict] ?? DEFAULT_STYLE) : DEFAULT_STYLE;

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 0, y: 12, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 8, scale: 0.97 }}
          transition={{ type: "spring", stiffness: 280, damping: 24 }}
          className="w-full p-4 space-y-3"
          style={{
            background: `${style.bg}`,
            borderRadius: 24,
            boxShadow: `0 0 0 1px ${style.color}22, 0 8px 40px rgba(0,0,0,0.55)`,
          }}
        >
          {/* Verdict + score */}
          <div className="flex items-center gap-3 flex-wrap">
            <span
              className="text-sm font-bold font-mono"
              style={{
                color: style.color,
                background: `${style.color}12`,
                borderRadius: 999,
                padding: "2px 12px",
                boxShadow: `0 0 0 1px ${style.color}35, 0 0 12px ${style.color}30`,
                textShadow: `0 0 12px ${style.color}80`,
              }}
            >
              {style.label}
            </span>
            {verdict && verdict.score > 0 && (
              <span className="text-xs font-mono text-subtext">
                {Math.round(verdict.score * 100)}% confidence
              </span>
            )}
          </div>

          {/* Rationale */}
          {verdict?.rationale && (
            <p className="text-xs font-mono text-subtext leading-relaxed">{verdict.rationale}</p>
          )}

          {/* Run summary */}
          {runSummary && (
            <div className="pt-1" style={{ borderTop: "1px solid rgba(180,160,232,0.06)" }}>
              <p className="text-[10px] font-mono text-overlay0 uppercase tracking-widest mb-1">Summary</p>
              <p className="text-xs font-mono text-text leading-relaxed">{runSummary}</p>
            </div>
          )}

          {/* Final answer */}
          {finalAnswer && (
            <details className="group">
              <summary className="text-[10px] font-mono text-overlay0 uppercase tracking-widest cursor-pointer list-none flex items-center gap-1">
                <span className="group-open:hidden">▶ Final Answer</span>
                <span className="hidden group-open:inline">▼ Final Answer</span>
              </summary>
              <p className="text-xs font-mono text-text leading-relaxed mt-2 whitespace-pre-wrap max-h-40 overflow-y-auto">
                {finalAnswer}
              </p>
            </details>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
