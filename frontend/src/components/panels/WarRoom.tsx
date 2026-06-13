"use client";
import React, { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { AgentMessage } from "@/lib/api";
import { cn } from "@/components/ui/cn";

// ─── Role registry ────────────────────────────────────────────────────────────
const ROLE_META: Record<
  string,
  { label: string; color: string; glow: string; badge: string; seat: string }
> = {
  // Standard pipeline
  analyst:     { label: "Analyst",   color: "#89b4fa", glow: "shadow-glow-blue",  badge: "bg-blue/15 text-blue border border-blue/20",    seat: "border-blue/40 group-[.active]:border-blue group-[.active]:shadow-glow-blue" },
  critic:      { label: "Critic",    color: "#f38ba8", glow: "shadow-glow-red",   badge: "bg-red/15 text-red border border-red/20",         seat: "border-red/40 group-[.active]:border-red group-[.active]:shadow-glow-red" },
  synthesizer: { label: "Synth",     color: "#a6e3a1", glow: "shadow-glow-green", badge: "bg-green/15 text-green border border-green/20",   seat: "border-green/40 group-[.active]:border-green group-[.active]:shadow-glow-green" },
  // Adversarial pipeline
  "adv:planner":   { label: "Planner",   color: "#cba6f7", glow: "shadow-glow",       badge: "bg-accent/15 text-accent border border-accent/20",  seat: "border-accent/40 group-[.active]:border-accent group-[.active]:shadow-glow" },
  "adv:actor":     { label: "Actor",     color: "#89b4fa", glow: "shadow-glow-blue",  badge: "bg-blue/15 text-blue border border-blue/20",          seat: "border-blue/40 group-[.active]:border-blue group-[.active]:shadow-glow-blue" },
  "adv:critic":    { label: "Critic",    color: "#f38ba8", glow: "shadow-glow-red",   badge: "bg-red/15 text-red border border-red/20",              seat: "border-red/40 group-[.active]:border-red group-[.active]:shadow-glow-red" },
  "adv:validator": { label: "Validator", color: "#f9e2af", glow: "shadow-[0_0_24px_rgba(249,226,175,0.35)]", badge: "bg-yellow/15 text-yellow border border-yellow/20", seat: "border-yellow/40 group-[.active]:border-yellow" },
  "adv:refiner":   { label: "Refiner",   color: "#94e2d5", glow: "shadow-[0_0_24px_rgba(148,226,213,0.35)]", badge: "bg-teal/15 text-teal border border-teal/20", seat: "border-teal/40 group-[.active]:border-teal" },
  "adv:judge":     { label: "Judge",     color: "#a6e3a1", glow: "shadow-glow-green", badge: "bg-green/15 text-green border border-green/20",        seat: "border-green/40 group-[.active]:border-green group-[.active]:shadow-glow-green" },
};

function getRoleMeta(role: string) {
  return ROLE_META[role] ?? {
    label: role,
    color: "#6c7086",
    glow: "",
    badge: "bg-surface0 text-subtext border border-surface1",
    seat: "border-surface1",
  };
}

// ─── Simulated streaming hook ─────────────────────────────────────────────────
// TODO: replace simulated reveal with real SSE when backend streaming is added.
// Stub: useAgentStream(taskId: string) → subscribes to /events/{taskId} SSE endpoint.
function useSequentialReveal(messages: AgentMessage[], isLoading: boolean) {
  const [revealed, setRevealed] = useState<AgentMessage[]>([]);
  const [activeRole, setActiveRole] = useState<string | null>(null);
  const prevMessages = useRef<AgentMessage[]>([]);

  useEffect(() => {
    // Reset on new run
    if (isLoading && messages.length === 0) {
      setRevealed([]);
      setActiveRole(null);
      prevMessages.current = [];
      return;
    }

    if (messages.length === 0) return;
    if (messages === prevMessages.current) return;
    prevMessages.current = messages;

    // Reveal messages one at a time with a 300ms gap
    setRevealed([]);
    setActiveRole(null);

    let i = 0;
    const reveal = () => {
      if (i >= messages.length) {
        setActiveRole(null);
        return;
      }
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

// ─── Agent Seat ───────────────────────────────────────────────────────────────
function AgentSeat({
  role,
  isActive,
  isDone,
}: {
  role: string;
  isActive: boolean;
  isDone: boolean;
}) {
  const meta = getRoleMeta(role);

  return (
    <div
      className={cn(
        "group flex flex-col items-center gap-1.5 p-3 rounded-xl border transition-all duration-300",
        "glass-surface",
        isActive ? "active " + meta.seat : "border-surface0/50",
        isActive && "scale-105",
      )}
    >
      {/* Avatar circle */}
      <div
        className={cn(
          "w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all duration-300",
          isActive
            ? "ring-2 ring-offset-1 ring-offset-crust animate-pulse-glow"
            : "opacity-60"
        )}
        style={{
          background: isActive
            ? `radial-gradient(circle, ${meta.color}33, ${meta.color}11)`
            : "rgba(49,50,68,0.5)",
          border: `1px solid ${meta.color}${isActive ? "80" : "30"}`,
          color: meta.color,
          outline: isActive ? `2px solid ${meta.color}60` : undefined,
        }}
      >
        {isDone ? "✓" : isActive ? "…" : meta.label.charAt(0)}
      </div>

      {/* Role label */}
      <span
        className="text-[9px] font-mono uppercase tracking-widest transition-colors"
        style={{ color: isActive ? meta.color : "#6c7086" }}
      >
        {meta.label}
      </span>

      {/* Thinking indicator */}
      {isActive && (
        <div className="flex gap-0.5">
          <span className="w-1 h-1 rounded-full bg-current animate-thinking-1" style={{ color: meta.color }} />
          <span className="w-1 h-1 rounded-full bg-current animate-thinking-2" style={{ color: meta.color }} />
          <span className="w-1 h-1 rounded-full bg-current animate-thinking-3" style={{ color: meta.color }} />
        </div>
      )}
    </div>
  );
}

// ─── Message card ─────────────────────────────────────────────────────────────
function WarRoomMessage({ msg }: { msg: AgentMessage }) {
  const meta = getRoleMeta(msg.role);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      className="rounded-xl p-4 glass-surface border-l-2 transition-colors duration-200 hover:bg-surface0/20"
      style={{
        borderLeftColor: meta.color,
        boxShadow: `inset 0 0 40px ${meta.color}0d`,
      }}
    >
      <div className="flex items-center gap-2 mb-2">
        <span
          className={cn("text-[10px] font-mono px-2 py-0.5 rounded-full", meta.badge)}
          style={{ textShadow: `0 0 8px ${meta.color}60` }}
        >
          {meta.label.toUpperCase()}
        </span>
        <span className="text-[10px] text-overlay font-mono">
          {new Date(msg.timestamp).toLocaleTimeString()}
        </span>
        {typeof msg.metadata?.model === "string" && (
          <span className="text-[10px] text-overlay/60 font-mono ml-auto">
            {(msg.metadata.model as string).split("/").pop()}
          </span>
        )}
      </div>
      <p className="text-text text-xs font-mono whitespace-pre-wrap leading-relaxed">
        {msg.content}
      </p>
    </motion.div>
  );
}

// ─── Loading skeleton ─────────────────────────────────────────────────────────
function ThinkingSkeleton({ role }: { role: string | null }) {
  const meta = role ? getRoleMeta(role) : null;

  return (
    <div className="rounded-xl p-4 glass-surface border border-surface0/60 animate-pulse">
      <div className="flex items-center gap-2 mb-2">
        {meta && (
          <span
            className="text-[10px] font-mono px-2 py-0.5 rounded-full"
            style={{ background: `${meta.color}15`, color: meta.color, border: `1px solid ${meta.color}30` }}
          >
            {meta.label.toUpperCase()} — THINKING
          </span>
        )}
      </div>
      <div className="space-y-1.5">
        <div className="h-2 bg-surface0/60 rounded w-full" />
        <div className="h-2 bg-surface0/60 rounded w-4/5" />
        <div className="h-2 bg-surface0/60 rounded w-2/3" />
      </div>
    </div>
  );
}

// ─── War Room ─────────────────────────────────────────────────────────────────
interface WarRoomProps {
  messages: AgentMessage[];
  isLoading: boolean;
  mode: "standard" | "adversarial";
}

export default function WarRoom({ messages, isLoading, mode }: WarRoomProps) {
  const { revealed, activeRole } = useSequentialReveal(messages, isLoading);
  const bottomRef = useRef<HTMLDivElement>(null);

  const agentOrder =
    mode === "adversarial"
      ? ["adv:planner", "adv:actor", "adv:critic", "adv:validator", "adv:refiner", "adv:judge"]
      : ["analyst", "critic", "synthesizer"];

  const doneRoles = new Set(revealed.map((m) => m.role));

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [revealed]);

  const isEmpty = messages.length === 0 && !isLoading;

  return (
    <div className="h-full flex flex-col gap-3 p-4 overflow-hidden">
      {/* Agent seats row */}
      <div className="flex-none">
        <div
          className={cn(
            "grid gap-2",
            mode === "adversarial" ? "grid-cols-6" : "grid-cols-3"
          )}
        >
          {agentOrder.map((role) => (
            <AgentSeat
              key={role}
              role={role}
              isActive={activeRole === role}
              isDone={doneRoles.has(role) && activeRole !== role}
            />
          ))}
        </div>
      </div>

      {/* Transcript column */}
      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        {isEmpty && (
          <div className="flex flex-col items-center justify-center h-full gap-3 opacity-50">
            <div className="text-4xl">⚔️</div>
            <p className="text-overlay text-xs font-mono text-center">
              {mode === "adversarial"
                ? "Switch to Adversarial mode and submit a task to watch the agents deliberate..."
                : "Submit a task to see the agents reason in real time..."}
            </p>
          </div>
        )}

        <AnimatePresence initial={false}>
          {revealed.map((msg) => (
            <WarRoomMessage key={msg.message_id} msg={msg} />
          ))}
        </AnimatePresence>

        {/* Show thinking skeleton for active agent not yet revealed */}
        {(isLoading || (activeRole && revealed.length < messages.length)) && (
          <ThinkingSkeleton role={activeRole} />
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
