import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  listEntries,
  deleteEntry,
  clearMode,
  relativeTime,
  type HistoryEntry,
  type HistoryMode,
} from "@/lib/history";

interface Props {
  open: boolean;
  mode: HistoryMode;
  onClose: () => void;
  onSelect: (entry: HistoryEntry) => void;
  // bump this number to force a refresh after a new entry is saved
  refreshKey: number;
}

function entryChip(entry: HistoryEntry): { label: string; color: string } | null {
  const p = entry.payload;
  if (p.kind === "experiment") {
    const pct = Math.round((p.result.consensus_score ?? 0) * 100);
    return { label: `${pct}%`, color: pct >= 85 ? "#a6e3a1" : pct >= 70 ? "#f9e2af" : "#f38ba8" };
  }
  const v = p.verdict?.verdict;
  if (!v) return null;
  const pass = v === "PASS" || v === "ACCEPT";
  return { label: v, color: pass ? "#a6e3a1" : v === "WARN" ? "#f9e2af" : "#f38ba8" };
}

export default function HistorySidebar({ open, mode, onClose, onSelect, refreshKey }: Props) {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);

  useEffect(() => {
    if (open) setEntries(listEntries(mode));
  }, [open, mode, refreshKey]);

  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    deleteEntry(mode, id);
    setEntries(listEntries(mode));
  };

  const handleClear = () => {
    clearMode(mode);
    setEntries([]);
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-[60]"
            style={{ background: "rgba(4,4,10,0.55)", backdropFilter: "blur(2px)" }}
          />
          {/* Drawer */}
          <motion.aside
            initial={{ x: -340 }}
            animate={{ x: 0 }}
            exit={{ x: -340 }}
            transition={{ type: "spring", stiffness: 360, damping: 36 }}
            className="fixed top-0 left-0 bottom-0 z-[61] w-[320px] flex flex-col"
            style={{
              background: "rgba(8,8,16,0.92)",
              backdropFilter: "blur(40px) saturate(1.6)",
              WebkitBackdropFilter: "blur(40px) saturate(1.6)",
              boxShadow: "1px 0 0 rgba(180,160,232,0.08)",
            }}
          >
            {/* Header */}
            <div className="flex items-center gap-2 px-4 h-[52px] flex-none" style={{ boxShadow: "0 1px 0 rgba(180,160,232,0.07)" }}>
              <span className="text-[12px] font-sans font-semibold uppercase tracking-wider" style={{ color: "#cba6f7" }}>
                History
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full" style={{ background: "rgba(203,166,247,0.10)", color: "#9494aa" }}>
                {mode}
              </span>
              <button
                onClick={onClose}
                className="ml-auto text-[#6b6b8a] hover:text-[#cdd6f4] text-lg leading-none"
                aria-label="Close history"
              >
                ×
              </button>
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto px-3 py-3 flex flex-col gap-2">
              {entries.length === 0 && (
                <p className="text-[11px] font-mono text-center mt-10" style={{ color: "#45455c" }}>
                  No {mode} history yet.
                </p>
              )}
              {entries.map((entry) => {
                const chip = entryChip(entry);
                return (
                  <div
                    key={entry.id}
                    onClick={() => onSelect(entry)}
                    className="group cursor-pointer rounded-xl p-3 transition-colors"
                    style={{ background: "rgba(180,160,232,0.04)", boxShadow: "0 0 0 1px rgba(180,160,232,0.07)" }}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[9px] font-mono" style={{ color: "#45455c" }}>{relativeTime(entry.timestamp)}</span>
                      {chip && (
                        <span className="text-[9px] font-mono px-1.5 py-0.5 rounded-full" style={{ background: `${chip.color}15`, color: chip.color }}>
                          {chip.label}
                        </span>
                      )}
                      <button
                        onClick={(e) => handleDelete(e, entry.id)}
                        className="ml-auto opacity-0 group-hover:opacity-100 text-[#6b6b8a] hover:text-[#f38ba8] text-xs leading-none transition-opacity"
                        aria-label="Delete entry"
                      >
                        ✕
                      </button>
                    </div>
                    <p className="text-[11px] font-sans leading-snug line-clamp-2" style={{ color: "#cdd6f4" }}>
                      {entry.prompt}
                    </p>
                  </div>
                );
              })}
            </div>

            {/* Footer */}
            {entries.length > 0 && (
              <div className="flex-none px-4 py-3" style={{ boxShadow: "0 -1px 0 rgba(180,160,232,0.07)" }}>
                <button
                  onClick={handleClear}
                  className="text-[10px] font-mono text-[#6b6b8a] hover:text-[#f38ba8] transition-colors"
                >
                  Clear all {mode} history
                </button>
              </div>
            )}
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
