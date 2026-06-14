"use client";
import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { AgentMessage } from "@/lib/api";

interface AgentDetailCardProps {
  role: string;
  label: string;
  color: string;
  messages: AgentMessage[];
  onClose: () => void;
}

type View = "summary" | "raw";

/** Slide-in panel showing all messages from a clicked character, with raw/summary toggle. */
export function AgentDetailCard({ role, label, color, messages, onClose }: AgentDetailCardProps) {
  const [view, setView] = useState<View>("summary");

  return (
    <AnimatePresence>
      <motion.div
        key={role}
        initial={{ opacity: 0, x: 24 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: 24 }}
        transition={{ type: "spring", stiffness: 320, damping: 28 }}
        className="absolute top-0 right-0 h-full w-72 z-30 flex flex-col bg-crust/95 backdrop-blur-md"
        style={{
          borderRadius: "24px 0 0 24px",
          boxShadow: `0 0 0 1px ${color}20, -12px 0 48px rgba(0,0,0,0.65)`,
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: "1px solid rgba(180,160,232,0.06)" }}>
          <div className="flex items-center gap-2">
            <span
              className="w-2.5 h-2.5 rounded-full"
              style={{ background: color, boxShadow: `0 0 6px ${color}` }}
            />
            <span className="text-xs font-bold font-mono uppercase tracking-wider" style={{ color }}>
              {label}
            </span>
          </div>
          <button onClick={onClose} className="text-overlay1 hover:text-text text-xs transition-colors" aria-label="Close">✕</button>
        </div>

        {/* View toggle */}
        <div className="flex gap-1 px-4 py-2" style={{ borderBottom: "1px solid rgba(180,160,232,0.04)" }}>
          {(["summary", "raw"] as View[]).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className="text-[10px] font-mono uppercase tracking-widest px-3 py-1 rounded-full transition-all"
              style={{
                background: view === v ? `${color}20` : "transparent",
                color: view === v ? color : "#6c7086",
                border: `1px solid ${view === v ? `${color}50` : "transparent"}`,
              }}
            >
              {v}
            </button>
          ))}
          <span className="ml-auto text-[10px] font-mono text-overlay0">{messages.length} msg{messages.length !== 1 ? "s" : ""}</span>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
          {messages.length === 0 && (
            <p className="text-[10px] text-overlay0 font-mono text-center mt-8">No messages yet.</p>
          )}
          {messages.map((msg, i) => (
            <div key={msg.message_id} className="p-3" style={{ borderRadius: 16, background: `${color}06`, boxShadow: `0 0 0 1px ${color}12` }}>
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-[9px] font-mono text-overlay0">#{i + 1}</span>
                <span className="text-[9px] font-mono text-overlay0">{new Date(msg.timestamp).toLocaleTimeString()}</span>
              </div>
              <p className="text-[11px] font-sans text-text leading-relaxed whitespace-pre-wrap">
                {view === "summary" && msg.summary ? msg.summary : msg.content}
              </p>
              {view === "summary" && !msg.summary && (
                <p className="text-[9px] text-overlay0 italic mt-1">No summary available</p>
              )}
            </div>
          ))}
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
