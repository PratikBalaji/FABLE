"use client";
import React, { useEffect, useRef, useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { AgentMessage, AdversarialMeta, VerdictMeta } from "@/lib/api";
import { RoundTable } from "./warroom/RoundTable";
import { Scoreboard } from "./warroom/Scoreboard";
import { VerdictBanner } from "./warroom/VerdictBanner";
import { AgentDetailCard } from "./warroom/AgentDetailCard";

// ─── Role registry ─────────────────────────────────────────────────────────────
const ROLE_META: Record<string, { label: string; color: string }> = {
  // Standard pipeline
  analyst:          { label: "Analyst",   color: "#89b4fa" },
  critic:           { label: "Critic",    color: "#f38ba8" },
  synthesizer:      { label: "Synth",     color: "#a6e3a1" },
  // Adversarial pipeline
  "adv:planner":    { label: "Planner",   color: "#cba6f7" },
  "adv:actor":      { label: "Actor",     color: "#89b4fa" },
  "adv:critic":     { label: "Critic",    color: "#f38ba8" },
  "adv:validator":  { label: "Validator", color: "#f9e2af" },
  "adv:refiner":    { label: "Refiner",   color: "#94e2d5" },
  "adv:judge":      { label: "Judge",     color: "#a6e3a1" },
};

function getRoleMeta(role: string) {
  return ROLE_META[role] ?? { label: role, color: "#6c7086" };
}

// ─── Simulated sequential reveal (unchanged from original) ────────────────────
function useSequentialReveal(messages: AgentMessage[], isLoading: boolean) {
  const [revealed, setRevealed] = useState<AgentMessage[]>([]);
  const [activeRole, setActiveRole] = useState<string | null>(null);
  const prevMessages = useRef<AgentMessage[]>([]);

  useEffect(() => {
    if (isLoading && messages.length === 0) {
      setRevealed([]);
      setActiveRole(null);
      prevMessages.current = [];
      return;
    }
    if (messages.length === 0) return;
    if (messages === prevMessages.current) return;
    prevMessages.current = messages;

    setRevealed([]);
    setActiveRole(null);
    let i = 0;
    const reveal = () => {
      if (i >= messages.length) { setActiveRole(null); return; }
      const msg = messages[i];
      setActiveRole(msg.role);
      setRevealed((prev) => [...prev, msg]);
      i++;
      setTimeout(reveal, i === 1 ? 400 : 280);
    };
    setTimeout(reveal, 150);
  }, [messages, isLoading]);

  return { revealed, activeRole };
}

// ─── Props ────────────────────────────────────────────────────────────────────
interface WarRoomProps {
  messages: AgentMessage[];
  isLoading: boolean;
  mode: "standard" | "adversarial" | "experiment";
  scores: Record<string, number>;
  verdict: VerdictMeta | null;
  runSummary: string;
  finalAnswer: string;
  adversarialMeta: AdversarialMeta | null;
  pipeline: string[];
  prompt?: string;
}

// ─── WarRoom ─────────────────────────────────────────────────────────────────
export default function WarRoom({
  messages,
  isLoading,
  mode,
  scores: _scores,
  verdict,
  runSummary,
  finalAnswer,
  adversarialMeta,
  pipeline,
  prompt,
}: WarRoomProps) {
  const { revealed, activeRole } = useSequentialReveal(messages, isLoading);
  const [selectedRole, setSelectedRole] = useState<string | null>(null);

  const agentOrder =
    mode === "adversarial"
      ? ["adv:planner", "adv:actor", "adv:critic", "adv:validator", "adv:refiner", "adv:judge"]
      : ["analyst", "critic", "synthesizer"];

  const doneRoles = new Set(revealed.map((m) => m.role));

  // Latest message from the active role (for the speech bubble)
  const activeMessage = useMemo<AgentMessage | null>(() => {
    if (!activeRole) return null;
    const all = revealed.filter((m) => m.role === activeRole);
    return all[all.length - 1] ?? null;
  }, [activeRole, revealed]);

  // Messages for the selected detail card
  const selectedMessages = useMemo(
    () => revealed.filter((m) => m.role === selectedRole),
    [revealed, selectedRole],
  );

  const isEmpty = messages.length === 0 && !isLoading;

  return (
    <div className="h-full flex flex-col gap-3 p-4 overflow-hidden relative">
      {/* User prompt — slim strip at top */}
      {prompt && (
        <div
          className="flex-none mx-auto max-w-2xl w-full px-4 py-2 rounded-2xl"
          style={{ background: "rgba(203,166,247,0.07)", boxShadow: "0 0 0 1px rgba(203,166,247,0.18)" }}
        >
          <span className="text-[10px] font-sans font-semibold" style={{ color: "#cba6f7" }}>You</span>
          <p className="text-[11px] font-sans leading-relaxed line-clamp-2" style={{ color: "#cdd6f4" }}>{prompt}</p>
        </div>
      )}
      {/* Scoreboard — top-center */}
      <div className="flex-none flex justify-center">
        <Scoreboard
          mode={mode}
          isLoading={isLoading}
          revealedCount={revealed.length}
          pipelineLength={pipeline.length}
          adversarialMeta={adversarialMeta}
        />
      </div>

      {/* Empty state */}
      {isEmpty && (
        <div className="flex flex-col items-center justify-center flex-1 gap-3 opacity-50">
          <div className="text-5xl">⚔️</div>
          <p className="text-overlay text-xs font-mono text-center max-w-xs">
            {mode === "adversarial"
              ? "Submit a task to watch your agents deliberate at the round table…"
              : "Submit a task to see your agents reason together…"}
          </p>
        </div>
      )}

      {/* Round table — main scene */}
      {!isEmpty && (
        <div className="flex-1 flex flex-col items-center gap-4 overflow-hidden">
          {/* Room atmosphere background */}
          <div className="relative w-full flex justify-center">
            {/* Subtle room vignette */}
            <div
              className="absolute inset-0 rounded-2xl pointer-events-none"
              style={{
                background: "radial-gradient(ellipse at 50% 40%, rgba(203,166,247,0.04) 0%, rgba(17,17,27,0.0) 70%)",
              }}
            />
            <RoundTable
              agentOrder={agentOrder}
              getRoleMeta={getRoleMeta}
              activeRole={activeRole}
              doneRoles={doneRoles}
              activeMessage={activeMessage}
              onCharacterClick={(role) =>
                setSelectedRole((prev) => (prev === role ? null : role))
              }
              width={mode === "adversarial" ? 500 : 380}
              height={280}
            />
          </div>

          {/* Hint */}
          {!isLoading && revealed.length > 0 && !selectedRole && (
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-[10px] font-mono text-overlay0 text-center"
            >
              Click a character to inspect their reasoning
            </motion.p>
          )}

          {/* Verdict banner — appears when run completes */}
          <div className="w-full max-w-lg">
            <VerdictBanner
              verdict={verdict}
              runSummary={runSummary}
              finalAnswer={finalAnswer}
              isLoading={isLoading}
            />
          </div>
        </div>
      )}

      {/* Agent detail card — absolute overlay on the right */}
      {selectedRole && (
        <AgentDetailCard
          role={selectedRole}
          label={getRoleMeta(selectedRole).label}
          color={getRoleMeta(selectedRole).color}
          messages={selectedMessages}
          onClose={() => setSelectedRole(null)}
        />
      )}
    </div>
  );
}
