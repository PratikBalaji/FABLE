"use client";
import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { AgentMessage } from "@/lib/api";
import UserPromptBubble from "./UserPromptBubble";

// Role colour map — applied inline (no Tailwind class dependency)
const ROLE_COLORS: Record<string, string> = {
  analyst:          "#89b4fa",
  critic:           "#f38ba8",
  synthesizer:      "#a6e3a1",
  "adv:planner":    "#cba6f7",
  "adv:actor":      "#89b4fa",
  "adv:critic":     "#f38ba8",
  "adv:validator":  "#f9e2af",
  "adv:refiner":    "#94e2d5",
  "adv:judge":      "#a6e3a1",
};

const ROLE_LABELS: Record<string, string> = {
  analyst:          "Analyst",
  critic:           "Critic",
  synthesizer:      "Synthesizer",
  "adv:planner":    "Planner",
  "adv:actor":      "Actor",
  "adv:critic":     "Critic",
  "adv:validator":  "Validator",
  "adv:refiner":    "Refiner",
  "adv:judge":      "Judge",
};

function getRoleColor(role: string) {
  return ROLE_COLORS[role] ?? "#6b6b8a";
}
function getRoleLabel(role: string) {
  return ROLE_LABELS[role] ?? role;
}

function MessageCard({ msg, index }: { msg: AgentMessage; index: number }) {
  const color = getRoleColor(msg.role);
  const label = getRoleLabel(msg.role);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        type: "spring",
        stiffness: 320,
        damping: 30,
        delay: index * 0.04,
      }}
      className="p-4 mb-3 hover-lift"
      style={{
        background: "rgba(14,14,28,0.68)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        borderRadius: 20,
        boxShadow: `0 0 0 1px rgba(180,160,232,0.06), 0 4px 24px rgba(0,0,0,0.50), 0 0 32px ${color}08 inset`,
      }}
    >
      <div className="flex items-center gap-2.5 mb-3">
        {/* Role colour dot — replaces old border-l stripe */}
        <span
          className="w-2 h-2 rounded-full flex-none"
          style={{ background: color, boxShadow: `0 0 6px ${color}` }}
        />
        <span className="text-[11px] font-sans font-semibold" style={{ color }}>
          {label}
        </span>
        <span className="text-[10px] font-mono" style={{ color: "#35354d" }}>
          {new Date(msg.timestamp).toLocaleTimeString()}
        </span>
        {typeof msg.metadata?.model === "string" && (
          <span className="text-[10px] font-mono ml-auto" style={{ color: "#35354d" }}>
            {(msg.metadata.model as string).split("/").pop()}
          </span>
        )}
      </div>
      <p className="text-[12px] font-sans whitespace-pre-wrap leading-relaxed" style={{ color: "#cdd6f4" }}>
        {msg.content}
      </p>
    </motion.div>
  );
}

interface Props {
  messages: AgentMessage[];
  isLoading?: boolean;
  prompt?: string;
}

export default function AgentThread({ messages, isLoading, prompt }: Props) {
  return (
    <div className="h-full overflow-y-auto pr-1">
      {prompt && <UserPromptBubble prompt={prompt} />}
      <AnimatePresence mode="popLayout">
        {messages.length === 0 && !isLoading && (
          <motion.p
            key="empty"
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.45 }}
            exit={{ opacity: 0 }}
            className="text-[13px] font-sans text-center mt-20"
            style={{ color: "#6b6b8a" }}
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
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ type: "spring", stiffness: 320, damping: 30 }}
            className="p-4 mb-3 animate-pulse"
            style={{
              background: "rgba(14,14,28,0.60)",
              borderRadius: 20,
              boxShadow: "0 0 0 1px rgba(180,160,232,0.05)",
            }}
          >
            <div className="flex items-center gap-2 mb-3">
              <div className="w-2 h-2 rounded-full" style={{ background: "#6b6b8a" }} />
              <div className="h-2.5 rounded-full w-20" style={{ background: "#1a1a2e" }} />
            </div>
            <div className="space-y-2">
              <div className="h-2 rounded-full w-full" style={{ background: "#1a1a2e" }} />
              <div className="h-2 rounded-full w-4/5" style={{ background: "#1a1a2e" }} />
              <div className="h-2 rounded-full w-2/3" style={{ background: "#1a1a2e" }} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
