/**
 * Shared chart theme for the FABLE dashboard.
 * Uses the app's purple-tonal palette + desaturated accents so charts read
 * as part of the same glassmorphic product (no harsh Catppuccin colors).
 */
import type { RunMode, RunCategory } from "../../lib/api";

// Soft, desaturated palette — purple primary + muted distinguishers.
export const PALETTE = {
  ink: "#080810",
  text: "#cdd6f4",
  subtle: "#6b6b8a",
  ghost: "#9494aa",
  accent: "#cba6f7",
  grid: "rgba(180,160,232,0.08)",
  // Mode hues (muted, translucent-friendly)
  mode: {
    standard: "#9db4f0",    // soft periwinkle
    adversarial: "#cba6f7", // brand purple
    montecarlo: "#a6e3c4",  // soft mint
  } as Record<RunMode, string>,
  // Category hues (desaturated spectrum)
  category: {
    code: "#cba6f7",
    reasoning: "#9db4f0",
    factual: "#f0c9a6",
    docqa: "#a6e3c4",
    writing: "#e3a6c9",
  } as Record<RunCategory, string>,
};

export const modeColor = (m: RunMode): string => PALETTE.mode[m] ?? PALETTE.accent;
export const categoryColor = (c: RunCategory): string => PALETTE.category[c] ?? PALETTE.accent;

/** Glass tooltip style for recharts <Tooltip contentStyle=...>. */
export const glassTooltip: React.CSSProperties = {
  background: "rgba(10,10,22,0.88)",
  backdropFilter: "blur(20px)",
  border: "none",
  borderRadius: 14,
  boxShadow: "0 0 0 1px rgba(180,160,232,0.10), 0 8px 32px rgba(0,0,0,0.6)",
  color: "#cdd6f4",
  fontSize: 12,
  padding: "8px 12px",
};

export const axisTick = { fontSize: 11, fill: PALETTE.subtle } as const;

export const MODES: RunMode[] = ["standard", "adversarial", "montecarlo"];
export const CATEGORIES: RunCategory[] = ["code", "reasoning", "factual", "docqa", "writing"];
