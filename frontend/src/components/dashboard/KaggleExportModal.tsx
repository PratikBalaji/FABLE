"use client";
import React, { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { exportToKaggle } from "../../lib/api";

export function KaggleExportModal({ onClose }: { onClose: () => void }) {
  const [username, setUsername] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [slug, setSlug] = useState("fable-benchmark-v1");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ dataset_url: string; kernel_url: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleExport = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const res = await exportToKaggle({ username, key: apiKey, dataset_slug: slug });
      setResult(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setLoading(false);
    }
  }, [username, apiKey, slug]);

  const input = "w-full glass-ghost rounded-xl px-3 py-2 text-[13px] outline-none mb-3 focus-ring";

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 z-[100] flex items-center justify-center"
        style={{ background: "rgba(4,4,10,0.6)", backdropFilter: "blur(6px)" }}
        onClick={onClose}
      >
        <motion.div
          initial={{ scale: 0.96, y: 8 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, opacity: 0 }}
          transition={{ type: "spring", stiffness: 420, damping: 32 }}
          className="glass p-7" style={{ width: 420, maxWidth: "90vw" }}
          onClick={(e) => e.stopPropagation()}
        >
          <h3 className="text-[16px] font-semibold mb-1" style={{ color: "#cba6f7" }}>
            Export to Kaggle
          </h3>
          <p className="text-[12px] mb-5" style={{ color: "#6b6b8a", lineHeight: 1.6 }}>
            Builds the 60-case dataset (CSV + JSONL) + reproducer notebook and pushes to your
            Kaggle account. Credentials are used once — never stored.
          </p>

          {!result ? (
            <>
              <label className="text-[11px]" style={{ color: "#6b6b8a" }}>Kaggle Username</label>
              <input className={input} value={username} autoComplete="off"
                     style={{ color: "#cdd6f4" }}
                     onChange={(e) => setUsername(e.target.value)} placeholder="your_username" />
              <label className="text-[11px]" style={{ color: "#6b6b8a" }}>Kaggle API Key</label>
              <input className={input} type="password" value={apiKey} autoComplete="off"
                     style={{ color: "#cdd6f4" }}
                     onChange={(e) => setApiKey(e.target.value)} placeholder="••••••••••••••••" />
              <label className="text-[11px]" style={{ color: "#6b6b8a" }}>Dataset Slug</label>
              <input className={input} value={slug} style={{ color: "#cdd6f4" }}
                     onChange={(e) => setSlug(e.target.value.replace(/[^a-z0-9-]/g, ""))} />

              {error && <div className="text-[12px] mb-3" style={{ color: "#e3a6c9" }}>{error}</div>}

              <div className="flex gap-2.5 mt-1">
                <button onClick={handleExport} disabled={loading || !username || !apiKey}
                        className="flex-1 rounded-xl py-2.5 text-[13px] font-semibold transition-all"
                        style={{
                          background: (!username || !apiKey) ? "rgba(203,166,247,0.3)" : "#cba6f7",
                          color: "#0d0d1a", cursor: loading ? "wait" : "pointer",
                          opacity: (!username || !apiKey) ? 0.5 : 1,
                        }}>
                  {loading ? "Pushing to Kaggle…" : "Export & Push"}
                </button>
                <button onClick={onClose} className="glass-ghost rounded-xl px-5 text-[13px]"
                        style={{ color: "#cdd6f4" }}>
                  Cancel
                </button>
              </div>
            </>
          ) : (
            <div>
              <div className="text-[14px] font-semibold mb-3" style={{ color: "#a6e3c4" }}>✓ Pushed to Kaggle</div>
              <a href={result.dataset_url} target="_blank" rel="noopener noreferrer"
                 className="block text-[13px] mb-2" style={{ color: "#9db4f0" }}>→ Dataset</a>
              <a href={result.kernel_url} target="_blank" rel="noopener noreferrer"
                 className="block text-[13px] mb-4" style={{ color: "#9db4f0" }}>→ Reproducer Notebook</a>
              <button onClick={onClose} className="glass-ghost rounded-xl px-5 py-2.5 text-[13px]"
                      style={{ color: "#cdd6f4" }}>Close</button>
            </div>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
