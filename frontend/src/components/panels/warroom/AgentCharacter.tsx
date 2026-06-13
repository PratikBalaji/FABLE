"use client";
import React from "react";
import { motion } from "framer-motion";

interface AgentCharacterProps {
  color: string;
  label: string;
  isActive: boolean;
  isDone: boolean;
  onClick: () => void;
}

/**
 * Among-Us-style bean character — SVG body + visor, role-color-coded.
 * Active: bob animation + glow ring. Done: ✓ visor.
 */
export function AgentCharacter({ color, label, isActive, isDone, onClick }: AgentCharacterProps) {
  return (
    <motion.div
      className="flex flex-col items-center gap-1 cursor-pointer select-none"
      animate={isActive ? { y: [0, -5, 0] } : { y: 0 }}
      transition={isActive ? { repeat: Infinity, duration: 0.7, ease: "easeInOut" } : { duration: 0.3 }}
      onClick={onClick}
      whileHover={{ scale: 1.12 }}
      whileTap={{ scale: 0.95 }}
    >
      <div className="relative">
        {/* Glow ring when active */}
        {isActive && (
          <motion.div
            className="absolute inset-0 rounded-full pointer-events-none"
            style={{ boxShadow: `0 0 18px 6px ${color}55` }}
            animate={{ opacity: [0.5, 1, 0.5] }}
            transition={{ repeat: Infinity, duration: 1.2 }}
          />
        )}
        <svg width="44" height="52" viewBox="0 0 44 52" fill="none" xmlns="http://www.w3.org/2000/svg">
          {/* Body */}
          <ellipse cx="22" cy="34" rx="14" ry="16" fill={color} opacity={isDone ? 0.85 : isActive ? 1 : 0.55} />
          {/* Head */}
          <circle cx="22" cy="18" r="13" fill={color} opacity={isDone ? 0.85 : isActive ? 1 : 0.55} />
          {/* Backpack */}
          <rect x="34" y="28" width="6" height="10" rx="2" fill={color} opacity={isDone ? 0.7 : isActive ? 0.9 : 0.4} />
          {/* Visor */}
          {isDone ? (
            <text x="22" y="22" textAnchor="middle" fontSize="10" fill="#1e1e2e" fontWeight="bold">✓</text>
          ) : (
            <ellipse
              cx="22" cy="18" rx="8" ry="5"
              fill={isActive ? "rgba(255,255,255,0.28)" : "rgba(255,255,255,0.14)"}
              stroke="rgba(255,255,255,0.35)"
              strokeWidth="0.8"
            />
          )}
          {/* Thinking dots when active */}
          {isActive && (
            <>
              <circle cx="17" cy="42" r="1.5" fill="rgba(255,255,255,0.6)" />
              <circle cx="22" cy="44" r="1.5" fill="rgba(255,255,255,0.6)" />
              <circle cx="27" cy="42" r="1.5" fill="rgba(255,255,255,0.6)" />
            </>
          )}
        </svg>
      </div>
      <span
        className="text-[9px] font-mono uppercase tracking-widest"
        style={{ color: isActive ? color : "#6c7086" }}
      >
        {label}
      </span>
    </motion.div>
  );
}
