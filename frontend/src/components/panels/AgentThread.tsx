"use client";
import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { AgentMessage } from "@/lib/api";
import { cn } from "@/components/ui/cn";

const ROLE_STYLES: Record<string, { border: string; label: string; badge: string; glow: string }> = {
  analyst:         { border: "border-l-blue",  label: "Analyst",   badge: "bg-blue/15 text-blue border border-blue/25",   glow: "rgba(137,180,250,0.12)" },
  critic:          { border: "border-l-red",   label: "Critic",    badge: "bg-red/15 text-red border border-red/25",       glow: "rgba(243,139,168,0.12)" },
  synthesizer:     { border: "border-l-green", label: "Synth",     badge: "bg-green/15 text-green border border-green/25", glow: "rgba(166,227,161,0.12)" },
  "adv:planner":   { border: "border-l-[#cba6f7]",  label: "Planner",   badge: "bg-[#cba6f7]/15 text-[#cba6f7] border border-[#cba6f7]/25", glow: "rgba(203,166,247,0.12)" },
  "adv:actor":     { border: "border-l-blue",  label: "Actor",     badge: "bg-blue/15 text-blue border border-blue/25",   glow: "rgba(137,180,250,0.12)" },
  "adv:critic":    { border: "border-l-red",   label: "Critic",    badge: "bg-red/15 text-red border border-red/25",       glow: "rgba(243,139,168,0.12)" },
  "adv:validator": { border: "border-l-yellow",label: "Validator", badge: "bg-yellow/15 text-yellow border border-yellow/25", glow: "rgba(249,226,175,0.12)" },
  "adv:refiner":   { border: "border-l-teal",  label: "Refiner",   badge: "bg-teal/15 text-teal border border-teal/25",   glow: "rgba(148,226,213,0.12)" },
  "adv:judge":     { border: "border-l-green", label: "Judge",     badge: "bg-green/15 text-green border border-green/25", glow: "rgba(166,227,161,0.12)" },
};

function MessageCard({ msg, index }: { msg: AgentMessage; index: number }) {
  const style = ROLE_STYLES[msg.role] ?? {
    border: "border-l-surface1",
    label: msg.role,
    badge: "bg-surface0 text-subtext border border-surface1",
    glow: "rgba(108,112,134,0.08)",
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: -12, y: 4 }}
      animate={{ opacity: 1, x: 0, y: 0 }}
      transition={{ duration: 0.28, delay: index * 0.05, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        "rounded-xl border-l-2 glass-surface p-4 mb-3 space-y-2",
        "hover:bg-surface0/20 transition-colors duration-200",
        style.border
      )}
      style={{ boxShadow: `inset 0 0 32px ${style.glow}` }}
    >
      <div className="flex items-center gap-2">
        <span className={cn("text-[10px] font-mono px-2 py-0.5 rounded-full", style.badge)}>
          {style.label.toUpperCase()}
        </span>
        <span className="text-[10px] text-overlay font-mono">
          {new Date(msg.timestamp).toLocaleTimeString()}
        </span>
        {typeof msg.metadata?.model === "string" && (
          <span className="text-[10px] text-overlay font-mono ml-auto opacity-60">
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

interface Props {
  messages: AgentMessage[];
  isLoading?: boolean;
}

export default function AgentThread({ messages, isLoading }: Props) {
  return (
    <div className="h-full overflow-y-auto pr-1">
      <AnimatePresence mode="popLayout">
        {messages.length === 0 && !isLoading && (
          <motion.p
            key="empty"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="text-overlay text-sm font-mono text-center mt-16"
          >
            Submit a task to start the agent collaboration…
          </motion.p>
        )}

        {messages.map((m, i) => (
          <MessageCard key={m.message_id} msg={m} index={i} />
        ))}

        {isLoading && (
          <motion.div
            key="skeleton"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="rounded-xl border-l-2 border-l-surface1 glass-surface p-4 animate-pulse"
          >
            <div className="h-3 bg-surface0/60 rounded w-20 mb-3" />
            <div className="space-y-1.5">
              <div className="h-2 bg-surface0/60 rounded w-full" />
              <div className="h-2 bg-surface0/60 rounded w-4/5" />
              <div className="h-2 bg-surface0/60 rounded w-2/3" />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
