"use client";
import React, { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { getByok, setByok, clearByok, testByokKey } from "../lib/api";

const PROVIDERS = [
  { value: "openrouter", label: "OpenRouter" },
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "google", label: "Google" },
];

export function ByokModal({ onClose }: { onClose: () => void }) {
  const existing = getByok();
  const [provider, setProvider] = useState(existing?.provider ?? "openrouter");
  const [key, setKey] = useState(existing?.key ?? "");
  const [baseUrl, setBaseUrl] = useState(existing?.baseUrl ?? "");
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; detail: string } | null>(null);

  const input = "w-full glass-ghost rounded-xl px-3 py-2 text-[13px] outline-none mb-3 focus-ring";

  const handleTest = useCallback(async () => {
    setTesting(true); setResult(null);
    try {
      const r = await testByokKey({ provider, api_key: key, base_url: baseUrl || undefined });
      setResult(r);
    } catch (e: unknown) {
      setResult({ ok: false, detail: e instanceof Error ? e.message : "test failed" });
    } finally { setTesting(false); }
  }, [provider, key, baseUrl]);

  const handleSave = useCallback(() => {
    setByok({ provider, key: key.trim(), baseUrl: baseUrl.trim() || undefined });
    onClose();
  }, [provider, key, baseUrl, onClose]);

  const handleClear = useCallback(() => { clearByok(); onClose(); }, [onClose]);

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
          className="glass p-7" style={{ width: 440, maxWidth: "92vw" }}
          onClick={(e) => e.stopPropagation()}
        >
          <h3 className="text-[16px] font-semibold mb-1" style={{ color: "#cba6f7" }}>
            Your API Key
          </h3>
          <p className="text-[12px] mb-5" style={{ color: "#6b6b8a", lineHeight: 1.6 }}>
            Run FABLE with your own provider quota. Stored <strong>only in this browser</strong>,
            sent per-request, never saved on the server. Clear it anytime.
          </p>

          <label className="text-[11px]" style={{ color: "#6b6b8a" }}>Provider</label>
          <select className={input} value={provider} style={{ color: "#cdd6f4" }}
                  onChange={(e) => setProvider(e.target.value)}>
            {PROVIDERS.map((p) => (
              <option key={p.value} value={p.value} style={{ background: "#0d0d1a" }}>{p.label}</option>
            ))}
          </select>

          <label className="text-[11px]" style={{ color: "#6b6b8a" }}>API Key</label>
          <input className={input} type="password" value={key} autoComplete="off"
                 style={{ color: "#cdd6f4" }}
                 onChange={(e) => setKey(e.target.value)} placeholder="sk-..." />

          <label className="text-[11px]" style={{ color: "#6b6b8a" }}>
            Custom base URL <span style={{ color: "#45455d" }}>(optional, OpenAI-compatible)</span>
          </label>
          <input className={input} value={baseUrl} style={{ color: "#cdd6f4" }}
                 onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://…/v1" />

          {result && (
            <div className="text-[12px] mb-3" style={{ color: result.ok ? "#a6e3c4" : "#e3a6c9" }}>
              {result.ok ? "✓ Key valid" : `✗ ${result.detail}`}
            </div>
          )}

          <div className="flex gap-2.5 mt-1">
            <button onClick={handleTest} disabled={testing || key.length < 8}
                    className="glass-ghost rounded-xl px-4 py-2.5 text-[13px]"
                    style={{ color: "#cdd6f4", opacity: key.length < 8 ? 0.5 : 1 }}>
              {testing ? "Testing…" : "Test"}
            </button>
            <button onClick={handleSave} disabled={key.length < 8}
                    className="flex-1 rounded-xl py-2.5 text-[13px] font-semibold"
                    style={{ background: key.length < 8 ? "rgba(203,166,247,0.3)" : "#cba6f7",
                             color: "#0d0d1a", opacity: key.length < 8 ? 0.5 : 1 }}>
              Save
            </button>
            {existing && (
              <button onClick={handleClear} className="glass-ghost rounded-xl px-4 text-[13px]"
                      style={{ color: "#e3a6c9" }}>
                Clear
              </button>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
