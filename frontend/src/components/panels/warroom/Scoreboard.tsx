"use client";
import React, { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { AdversarialMeta } from "@/lib/api";

interface ScoreboardProps {
  mode: "standard" | "adversarial";
  isLoading: boolean;
  revealedCount: number;
  pipelineLength: number;
  adversarialMeta: AdversarialMeta | null;
}

/** Minimalist glassmorphic scoreboard: stage/round progress + elapsed timer. */
export function Scoreboard({ mode, isLoading, revealedCount, pipelineLength, adversarialMeta }: ScoreboardProps) {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (isLoading) {
      startRef.current = Date.now();
      setElapsed(0);
      timerRef.current = setInterval(() => {
        setElapsed(Math.floor((Date.now() - (startRef.current ?? Date.now())) / 1000));
      }, 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isLoading]);

  const formatTime = (s: number) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

  const stageLabel =
    mode === "adversarial"
      ? `Round ${adversarialMeta?.rounds_completed ?? 0}/${adversarialMeta?.max_rounds ?? 2}`
      : `Stage ${Math.min(revealedCount, pipelineLength)}/${pipelineLength}`;

  const isRunning = isLoading || revealedCount > 0;

  return (
    <AnimatePresence>
      {isRunning && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.3 }}
          className="flex items-center gap-4 px-4 py-2 font-mono text-xs"
          style={{
            background: "rgba(10,10,22,0.85)",
            backdropFilter: "blur(32px)",
            WebkitBackdropFilter: "blur(32px)",
            borderRadius: 999,
            boxShadow: "0 0 0 1px rgba(180,160,232,0.09), 0 4px 28px rgba(0,0,0,0.55)",
          }}
        >
          {/* Pulse dot */}
          <span
            className="w-2 h-2 rounded-full"
            style={{
              background: isLoading ? "#cba6f7" : "#a6e3a1",
              boxShadow: isLoading ? "0 0 6px #cba6f7" : "0 0 6px #a6e3a1",
              animation: isLoading ? "ping 1.2s cubic-bezier(0,0,0.2,1) infinite" : undefined,
            }}
          />

          {/* Stage / Round */}
          <span className="text-subtext uppercase tracking-widest">{stageLabel}</span>

          <span className="text-surface1">|</span>

          {/* Timer */}
          <span className="text-accent tabular-nums">{formatTime(elapsed)}</span>

          {isLoading && (
            <span className="text-overlay0 animate-pulse">processing…</span>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
