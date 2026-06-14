import React from "react";
import { motion } from "framer-motion";

// The user's submitted prompt, rendered as a "You" bubble at the top of each view
// so the conversation reads as prompt → agent responses.
export default function UserPromptBubble({ prompt }: { prompt: string }) {
  if (!prompt) return null;
  const color = "#cba6f7";
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 320, damping: 30 }}
      className="p-4 mb-3"
      style={{
        background: "rgba(203,166,247,0.07)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        borderRadius: 20,
        boxShadow: `0 0 0 1px ${color}22, 0 4px 24px rgba(0,0,0,0.40)`,
      }}
    >
      <div className="flex items-center gap-2.5 mb-2">
        <span className="w-2 h-2 rounded-full flex-none" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />
        <span className="text-[11px] font-sans font-semibold" style={{ color }}>You</span>
      </div>
      <p className="text-[12px] font-sans whitespace-pre-wrap leading-relaxed" style={{ color: "#cdd6f4" }}>
        {prompt}
      </p>
    </motion.div>
  );
}
