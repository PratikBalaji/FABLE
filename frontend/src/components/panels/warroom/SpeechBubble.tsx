"use client";
import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { AgentMessage } from "@/lib/api";

interface SpeechBubbleProps {
  msg: AgentMessage | null;
  color: string;
  /** Position (CSS top/left relative to the round-table container) */
  x: number;
  y: number;
}

/**
 * Animated speech bubble that pops above the speaking character.
 * Shows summary text by default; click expands full raw content.
 */
export function SpeechBubble({ msg, color, x, y }: SpeechBubbleProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <AnimatePresence>
      {msg && (
        <motion.div
          key={msg.message_id}
          initial={{ opacity: 0, scale: 0.75, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.8, y: 6 }}
          transition={{ type: "spring", stiffness: 380, damping: 26 }}
          className="absolute z-20 pointer-events-auto"
          style={{
            left: x,
            top: y,
            transform: "translate(-50%, -100%)",
            maxWidth: 200,
          }}
        >
          {/* Bubble body */}
          <div
            className="px-3 py-2 cursor-pointer"
            style={{
              background: "rgba(8,8,20,0.94)",
              backdropFilter: "blur(32px)",
              WebkitBackdropFilter: "blur(32px)",
              borderRadius: 20,
              boxShadow: `0 0 0 1px ${color}28, 0 8px 32px rgba(0,0,0,0.65), 0 0 16px ${color}10 inset`,
            }}
            onClick={() => setExpanded((v) => !v)}
          >
            <p
              className="text-[10px] font-sans text-text leading-relaxed whitespace-pre-wrap"
              style={{
                maxHeight: expanded ? 200 : 60,
                overflowY: expanded ? "auto" : "hidden",
                transition: "max-height 0.25s ease",
              }}
            >
              {(msg.summary && !expanded) ? msg.summary : msg.content}
            </p>
            {(msg.summary || msg.content.length > 120) && (
              <span className="text-[9px] font-mono mt-1 block" style={{ color: `${color}99` }}>
                {expanded ? "▲ collapse" : "▼ full output"}
              </span>
            )}
          </div>
          {/* Tail pointing down */}
          <div
            className="mx-auto w-0 h-0"
            style={{
              borderLeft: "6px solid transparent",
              borderRight: "6px solid transparent",
              borderTop: `7px solid ${color}55`,
              width: 0,
            }}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
