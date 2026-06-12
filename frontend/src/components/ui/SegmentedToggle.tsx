"use client";
import React from "react";
import { cn } from "./cn";

export interface ToggleOption<T extends string> {
  value: T;
  label: string;
  icon?: React.ReactNode;
}

interface SegmentedToggleProps<T extends string> {
  options: ToggleOption<T>[];
  value: T;
  onChange: (v: T) => void;
  className?: string;
  size?: "sm" | "md";
}

export function SegmentedToggle<T extends string>({
  options,
  value,
  onChange,
  className,
  size = "md",
}: SegmentedToggleProps<T>) {
  const pad = size === "sm" ? "px-3 py-1 text-xs" : "px-4 py-1.5 text-xs";

  return (
    <div
      className={cn(
        "flex items-center gap-0.5 p-0.5 rounded-full",
        "bg-surface0/40 backdrop-blur-md border border-white/[0.06]",
        className
      )}
    >
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={cn(
            "flex items-center gap-1.5 rounded-full font-mono font-medium transition-all duration-200",
            pad,
            value === opt.value
              ? "bg-accent text-crust shadow-glow"
              : "text-overlay hover:text-subtext"
          )}
        >
          {opt.icon && <span className="w-3.5 h-3.5">{opt.icon}</span>}
          {opt.label}
        </button>
      ))}
    </div>
  );
}
