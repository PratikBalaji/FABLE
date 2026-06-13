"use client";
import React from "react";
import { motion, AnimatePresence } from "framer-motion";

interface ScorePillsProps {
  scores: Record<string, number>;
  visible: boolean;
}

function scoreColor(pct: number): string {
  if (pct >= 78) return "#a8d4a8"; // muted green
  if (pct >= 52) return "#cfc07a"; // muted amber
  return "#cc8080";                 // muted red
}

/**
 * Floating pill cluster that floats above the composer when a run completes.
 * One pill per rubric dimension, stagger-spring-in.
 */
export function ScorePills({ scores, visible }: ScorePillsProps) {
  const entries = Object.entries(scores);

  return (
    <AnimatePresence>
      {visible && entries.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 8, transition: { duration: 0.18 } }}
          transition={{ type: "spring", stiffness: 340, damping: 28 }}
          className="flex flex-wrap justify-center gap-2"
        >
          {entries.map(([label, value], i) => {
            const pct = Math.round(value * 100);
            const color = scoreColor(pct);
            return (
              <motion.div
                key={label}
                initial={{ opacity: 0, scale: 0.82, y: 8 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.88 }}
                transition={{
                  type: "spring",
                  stiffness: 380,
                  damping: 28,
                  delay: i * 0.06,
                }}
                className="flex items-center gap-1.5 rounded-full px-3 py-1.5 select-none"
                style={{
                  background: "rgba(10,10,22,0.88)",
                  backdropFilter: "blur(24px)",
                  WebkitBackdropFilter: "blur(24px)",
                  boxShadow: `0 0 0 1px rgba(180,160,232,0.10), 0 0 14px ${color}14`,
                }}
              >
                <span
                  className="w-1.5 h-1.5 rounded-full flex-none"
                  style={{ background: color, boxShadow: `0 0 5px ${color}` }}
                />
                <span className="text-[10px] font-sans capitalize" style={{ color: "#9494aa" }}>
                  {label}
                </span>
                <span className="text-[11px] font-mono font-semibold" style={{ color }}>
                  {pct}%
                </span>
              </motion.div>
            );
          })}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
