"use client";
import React, { useRef, useState, useLayoutEffect, useEffect } from "react";
import { motion } from "framer-motion";

export interface PillOption<T extends string> {
  value: T;
  label: string;
}

interface PillSwitcherProps<T extends string> {
  options: PillOption<T>[];
  value: T;
  onChange: (v: T) => void;
  size?: "sm" | "md" | "lg";
}

/**
 * iOS-style animated pill switcher.
 * The active indicator is a filled capsule that spring-slides between options.
 */
export function PillSwitcher<T extends string>({
  options,
  value,
  onChange,
  size = "md",
}: PillSwitcherProps<T>) {
  const containerRef = useRef<HTMLDivElement>(null);
  const btnRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const [indicator, setIndicator] = useState({ left: 0, width: 0 });

  const activeIdx = options.findIndex((o) => o.value === value);

  const updateIndicator = () => {
    const btn = btnRefs.current[activeIdx];
    const container = containerRef.current;
    if (!btn || !container) return;
    const br = btn.getBoundingClientRect();
    const cr = container.getBoundingClientRect();
    setIndicator({ left: br.left - cr.left, width: br.width });
  };

  useLayoutEffect(updateIndicator, [activeIdx]);

  // Re-measure on window resize
  useEffect(() => {
    window.addEventListener("resize", updateIndicator);
    return () => window.removeEventListener("resize", updateIndicator);
  });

  const pad =
    size === "sm" ? "px-3 py-1 text-[11px]" :
    size === "lg" ? "px-5 py-2 text-sm" :
                    "px-4 py-1.5 text-[12px]";

  return (
    <div
      ref={containerRef}
      role="tablist"
      className="relative inline-flex items-center p-1 glass-pill"
    >
      {/* Sliding active indicator */}
      {indicator.width > 0 && (
        <motion.span
          className="absolute inset-y-1 rounded-full pointer-events-none"
          style={{
            background: "rgba(203,166,247,0.14)",
            boxShadow: "0 0 0 1px rgba(203,166,247,0.20)",
          }}
          animate={{ left: indicator.left, width: indicator.width }}
          initial={false}
          transition={{ type: "spring", stiffness: 440, damping: 36 }}
          aria-hidden
        />
      )}
      {options.map((opt, i) => (
        <button
          key={opt.value}
          role="tab"
          aria-selected={value === opt.value}
          ref={(el) => { btnRefs.current[i] = el; }}
          onClick={() => onChange(opt.value)}
          className={`relative z-10 rounded-full font-sans font-medium transition-colors duration-200 whitespace-nowrap ${pad}`}
          style={{
            color: value === opt.value ? "#cba6f7" : "#6b6b8a",
            textShadow: value === opt.value ? "0 0 16px rgba(203,166,247,0.55)" : "none",
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
