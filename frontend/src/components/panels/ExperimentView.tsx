import React from "react";
import { motion } from "framer-motion";
import type { MonteCarloResponse } from "@/lib/api";
import UserPromptBubble from "./UserPromptBubble";

interface Props {
  result: MonteCarloResponse | null;
  isLoading: boolean;
  error?: string | null;
  prompt?: string;
}

function modelShortName(id: string): string {
  return id.split("/").pop() ?? id;
}

function scoreColor(v: number): string {
  if (v >= 0.85) return "#a6e3a1";
  if (v >= 0.70) return "#f9e2af";
  return "#f38ba8";
}

export default function ExperimentView({ result, isLoading, error, prompt }: Props) {
  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 text-[#cdd6f4]/40">
        <motion.div
          className="w-8 h-8 rounded-full border-2 border-[#cba6f7] border-t-transparent"
          animate={{ rotate: 360 }}
          transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
        />
        <span className="text-xs font-mono">Running Monte Carlo…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-2 px-6 text-center">
        <span className="text-3xl">⚠️</span>
        <span className="text-xs font-mono text-[#f38ba8]">{error}</span>
        <span className="text-[10px] font-mono text-[#cdd6f4]/30">The experiment request failed. Try again.</span>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-2 text-[#cdd6f4]/30">
        <span className="text-3xl">⚗️</span>
        <span className="text-xs font-mono">Submit a prompt to run the experiment</span>
      </div>
    );
  }

  const { variants, models, responses, similarity_matrix, consensus_score,
          divergence_pairs, per_model_consensus } = result;
  const n = variants.length * models.length;
  const consensusCol = scoreColor(consensus_score);

  return (
    <div className="flex flex-col gap-6 p-4 h-full overflow-y-auto">
      {prompt && <UserPromptBubble prompt={prompt} />}
      {/* Header */}
      <div className="flex items-center gap-3">
        <span className="text-[10px] font-mono text-[#cdd6f4]/40 uppercase tracking-widest">Monte Carlo</span>
        <div
          className="ml-auto px-3 py-1 rounded-full text-xs font-mono font-bold"
          style={{
            background: `${consensusCol}15`,
            color: consensusCol,
            boxShadow: `0 0 0 1px ${consensusCol}30`,
          }}
        >
          Consensus {Math.round(consensus_score * 100)}%
        </div>
      </div>

      {/* Per-model consensus chips */}
      <div className="flex flex-wrap gap-2">
        {models.map((m) => {
          const score = per_model_consensus[m] ?? 0;
          const col = scoreColor(score);
          return (
            <div
              key={m}
              className="px-2 py-0.5 rounded text-[10px] font-mono"
              style={{ background: `${col}12`, color: col, border: `1px solid ${col}30` }}
            >
              {modelShortName(m)} {Math.round(score * 100)}%
            </div>
          );
        })}
      </div>

      {/* Response grid */}
      <div className="grid gap-2" style={{ gridTemplateColumns: `120px repeat(${models.length}, 1fr)` }}>
        {/* Header row */}
        <div />
        {models.map((m) => (
          <div key={m} className="text-[10px] font-mono text-[#cdd6f4]/50 text-center truncate px-1">
            {modelShortName(m)}
          </div>
        ))}

        {/* Data rows */}
        {variants.map((variant, vi) => (
          <React.Fragment key={vi}>
            <div
              className="text-[10px] font-mono text-[#cdd6f4]/40 leading-tight self-start pt-1 truncate"
              title={variant}
            >
              {variant.slice(0, 40)}{variant.length > 40 ? "…" : ""}
            </div>
            {(responses[vi] ?? []).map((resp, mi) => (
              <div
                key={mi}
                className="rounded p-2 text-[10px] text-[#cdd6f4]/80 leading-relaxed max-h-24 overflow-y-auto"
                style={{ background: "rgba(180,160,232,0.04)", border: "1px solid rgba(180,160,232,0.08)" }}
              >
                {resp || <span className="text-[#cdd6f4]/20 italic">no response</span>}
              </div>
            ))}
          </React.Fragment>
        ))}
      </div>

      {/* Similarity heatmap */}
      <div className="flex flex-col gap-2">
        <span className="text-[10px] font-mono text-[#cdd6f4]/40 uppercase tracking-widest">Similarity Heatmap</span>
        <div
          className="grid gap-px"
          style={{ gridTemplateColumns: `repeat(${n}, 1fr)` }}
        >
          {similarity_matrix.map((row, i) =>
            row.map((val, j) => {
              const col = scoreColor(val);
              return (
                <div
                  key={`${i}-${j}`}
                  className="aspect-square rounded-sm"
                  style={{ background: i === j ? "rgba(180,160,232,0.15)" : `${col}${Math.round(val * 255).toString(16).padStart(2, "0")}` }}
                  title={`[${i}↔${j}] ${(val * 100).toFixed(1)}%`}
                />
              );
            })
          )}
        </div>
      </div>

      {/* Divergence pairs */}
      {divergence_pairs.length > 0 && (
        <div className="flex flex-col gap-2">
          <span className="text-[10px] font-mono text-[#f38ba8]/70 uppercase tracking-widest">
            Divergence Pairs ({divergence_pairs.length})
          </span>
          {divergence_pairs.slice(0, 5).map((p, i) => (
            <div
              key={i}
              className="rounded p-2 text-[10px] font-mono"
              style={{ background: "rgba(243,139,168,0.06)", border: "1px solid rgba(243,139,168,0.15)" }}
            >
              <span className="text-[#f38ba8]">{(p.similarity * 100).toFixed(1)}%</span>
              {" · "}
              <span className="text-[#cdd6f4]/50">{modelShortName(p.model_a)}</span>
              {" vs "}
              <span className="text-[#cdd6f4]/50">{modelShortName(p.model_b)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
