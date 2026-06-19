"use client";
import React from "react";
import type { RunMode, RunCategory } from "../../lib/api";
import { MODES, CATEGORIES, modeColor, categoryColor } from "./theme";

export interface FilterState {
  modes: Set<RunMode>;
  categories: Set<RunCategory>;
  verdicts: Set<string>;
  scoreMin: number;          // 0..100
  scoreMax: number;          // 0..100
  status: "all" | "done" | "pending";
}

export const DEFAULT_FILTERS = (): FilterState => ({
  modes: new Set(MODES),
  categories: new Set(CATEGORIES),
  verdicts: new Set(),       // empty = all verdicts
  scoreMin: 0,
  scoreMax: 100,
  status: "all",
});

const VERDICTS = ["PASS", "WARN", "FAIL", "ACCEPT", "REJECT"];

interface FilterRailProps {
  filters: FilterState;
  onChange: (f: FilterState) => void;
  batches: string[];
  activeBatch: string;
  onBatchChange: (b: string) => void;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-5">
      <div className="text-[10px] uppercase tracking-wider mb-2" style={{ color: "#6b6b8a" }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function toggleSet<T>(set: Set<T>, v: T): Set<T> {
  const next = new Set(set);
  if (next.has(v)) next.delete(v); else next.add(v);
  return next;
}

function Chip({ label, active, color, onClick }: {
  label: string; active: boolean; color: string; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="text-[11px] px-2.5 py-1 rounded-full transition-all duration-150 capitalize"
      style={{
        background: active ? `${color}1f` : "rgba(12,12,28,0.45)",
        color: active ? "#e8e8f5" : "#6b6b8a",
        boxShadow: active ? `0 0 0 1px ${color}55, 0 0 10px ${color}22` : "0 0 0 1px rgba(180,160,232,0.05)",
      }}
    >
      {label}
    </button>
  );
}

export function FilterRail({ filters, onChange, batches, activeBatch, onBatchChange }: FilterRailProps) {
  const set = (patch: Partial<FilterState>) => onChange({ ...filters, ...patch });

  return (
    <div>
      <Section title="Mode">
        <div className="flex flex-wrap gap-1.5">
          {MODES.map((m) => (
            <Chip key={m} label={m} active={filters.modes.has(m)} color={modeColor(m)}
                  onClick={() => set({ modes: toggleSet(filters.modes, m) })} />
          ))}
        </div>
      </Section>

      <Section title="Category">
        <div className="flex flex-wrap gap-1.5">
          {CATEGORIES.map((c) => (
            <Chip key={c} label={c} active={filters.categories.has(c)} color={categoryColor(c)}
                  onClick={() => set({ categories: toggleSet(filters.categories, c) })} />
          ))}
        </div>
      </Section>

      <Section title="Verdict">
        <div className="flex flex-wrap gap-1.5">
          {VERDICTS.map((v) => (
            <Chip key={v} label={v} active={filters.verdicts.has(v)} color="#cba6f7"
                  onClick={() => set({ verdicts: toggleSet(filters.verdicts, v) })} />
          ))}
        </div>
        <div className="text-[10px] mt-1.5" style={{ color: "#45455d" }}>
          {filters.verdicts.size === 0 ? "all verdicts" : `${filters.verdicts.size} selected`}
        </div>
      </Section>

      <Section title={`Score  ${filters.scoreMin}%–${filters.scoreMax}%`}>
        <div className="flex flex-col gap-2">
          <input type="range" min={0} max={100} value={filters.scoreMin}
                 onChange={(e) => set({ scoreMin: Math.min(+e.target.value, filters.scoreMax) })}
                 className="dash-range" />
          <input type="range" min={0} max={100} value={filters.scoreMax}
                 onChange={(e) => set({ scoreMax: Math.max(+e.target.value, filters.scoreMin) })}
                 className="dash-range" />
        </div>
      </Section>

      <Section title="Status">
        <div className="flex gap-1.5">
          {(["all", "done", "pending"] as const).map((s) => (
            <Chip key={s} label={s} active={filters.status === s} color="#9db4f0"
                  onClick={() => set({ status: s })} />
          ))}
        </div>
      </Section>

      {batches.length > 0 && (
        <Section title="Run Batch">
          <select
            value={activeBatch}
            onChange={(e) => onBatchChange(e.target.value)}
            className="w-full text-[11px] rounded-xl px-3 py-2 glass-ghost outline-none"
            style={{ color: "#cdd6f4" }}
          >
            {batches.map((b) => (
              <option key={b} value={b} style={{ background: "#0d0d1a" }}>{b}</option>
            ))}
          </select>
        </Section>
      )}
    </div>
  );
}

/** Apply the filter state to a list of runs. */
export function applyFilters<T extends {
  mode: RunMode; category: RunCategory; verdict: string | null;
  score: number | null; status: "done" | "pending";
}>(runs: T[], f: FilterState): T[] {
  return runs.filter((r) => {
    if (!f.modes.has(r.mode)) return false;
    if (!f.categories.has(r.category)) return false;
    if (f.status !== "all" && r.status !== f.status) return false;
    if (f.verdicts.size > 0) {
      const v = (r.verdict ?? "").toUpperCase();
      if (![...f.verdicts].some((sel) => v.includes(sel))) return false;
    }
    // Score filter only constrains completed runs (pending has no score)
    if (r.score != null) {
      const pct = r.score <= 1 ? r.score * 100 : r.score;
      if (pct < f.scoreMin || pct > f.scoreMax) return false;
    }
    return true;
  });
}
