// Per-mode chat history persisted in browser localStorage.
// Single-user, no backend/auth required. All access is try/catch-guarded so a
// corrupt or unavailable store can never crash the app.

import type { AgentMessage, GraphState, VerdictMeta, AdversarialMeta, MonteCarloResponse, RecycledMeta } from "./api";

export type HistoryMode = "standard" | "adversarial" | "experiment";

// Payload holds everything needed to re-render a past run with no network call.
export interface StandardPayload {
  kind: "standard" | "adversarial";
  messages: AgentMessage[];
  scores: Record<string, number>;
  modelUsed: string;
  graphState: GraphState | null;
  runSummary: string;
  finalAnswer: string;
  verdict: VerdictMeta | null;
  adversarialMeta?: AdversarialMeta | null;
  recycledMeta?: RecycledMeta | null;
}

export interface ExperimentPayload {
  kind: "experiment";
  result: MonteCarloResponse;
}

export type HistoryPayload = StandardPayload | ExperimentPayload;

export interface HistoryEntry {
  id: string;
  mode: HistoryMode;
  prompt: string;
  timestamp: number;
  payload: HistoryPayload;
}

const MAX_PER_MODE = 50;
const KEY_PREFIX = "fable:history:";

function key(mode: HistoryMode): string {
  return `${KEY_PREFIX}${mode}`;
}

function safeParse(raw: string | null): HistoryEntry[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function listEntries(mode: HistoryMode): HistoryEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const entries = safeParse(window.localStorage.getItem(key(mode)));
    // newest-first
    return entries.sort((a, b) => b.timestamp - a.timestamp);
  } catch {
    return [];
  }
}

export function getEntry(mode: HistoryMode, id: string): HistoryEntry | null {
  return listEntries(mode).find((e) => e.id === id) ?? null;
}

export function saveEntry(
  mode: HistoryMode,
  prompt: string,
  payload: HistoryPayload,
): HistoryEntry | null {
  if (typeof window === "undefined") return null;
  const entry: HistoryEntry = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    mode,
    prompt,
    timestamp: Date.now(),
    payload,
  };
  try {
    const entries = safeParse(window.localStorage.getItem(key(mode)));
    entries.push(entry);
    // FIFO cap — keep newest MAX_PER_MODE
    const trimmed = entries
      .sort((a, b) => b.timestamp - a.timestamp)
      .slice(0, MAX_PER_MODE);
    window.localStorage.setItem(key(mode), JSON.stringify(trimmed));
    return entry;
  } catch {
    // Quota exceeded or storage unavailable — non-fatal, history just won't persist
    return null;
  }
}

export function deleteEntry(mode: HistoryMode, id: string): void {
  if (typeof window === "undefined") return;
  try {
    const entries = safeParse(window.localStorage.getItem(key(mode))).filter((e) => e.id !== id);
    window.localStorage.setItem(key(mode), JSON.stringify(entries));
  } catch {
    /* non-fatal */
  }
}

export function clearMode(mode: HistoryMode): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(key(mode));
  } catch {
    /* non-fatal */
  }
}

export function relativeTime(ts: number): string {
  const diff = Date.now() - ts;
  const s = Math.floor(diff / 1000);
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}
