"use client";
import React, { useState, useEffect, useCallback } from "react";
import { Copy, Check, ExternalLink } from "lucide-react";
import { getPiiConfig, setPiiMode, type PiiConfig } from "../../lib/api";

// Host port 3001 to avoid clashing with the Next.js dev server on 3000.
const DOCKER_CMD = "docker run -p 3001:3000 mcr.microsoft.com/presidio-analyzer:latest";

export function PiiModeCard() {
  const [cfg, setCfg] = useState<PiiConfig | null>(null);
  const [url, setUrl] = useState("http://localhost:3001");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const refresh = useCallback(async () => {
    try { setCfg(await getPiiConfig()); } catch { /* backend offline */ }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const toggle = useCallback(async (mode: "presidio" | "regex_llm") => {
    setBusy(true); setErr(null);
    try {
      await setPiiMode(mode, url);
      await refresh();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "switch failed");
    } finally { setBusy(false); }
  }, [url, refresh]);

  const copy = () => {
    navigator.clipboard?.writeText(DOCKER_CMD);
    setCopied(true); setTimeout(() => setCopied(false), 1500);
  };

  const mode = cfg?.mode ?? "regex_llm";
  const reachable = cfg?.presidio_reachable ?? false;

  const Opt = ({ id, label, desc }: { id: "regex_llm" | "presidio"; label: string; desc: string }) => (
    <button
      onClick={() => toggle(id)}
      disabled={busy}
      className="flex-1 text-left rounded-2xl p-3 transition-all"
      style={{
        background: mode === id ? "rgba(203,166,247,0.12)" : "rgba(12,12,28,0.45)",
        boxShadow: mode === id ? "0 0 0 1px rgba(203,166,247,0.4)" : "0 0 0 1px rgba(180,160,232,0.06)",
      }}
    >
      <div className="flex items-center gap-2 text-[13px] font-medium" style={{ color: "#e8e8f5" }}>
        <span style={{
          width: 9, height: 9, borderRadius: 99,
          background: mode === id ? "#a6e3c4" : "#45455d",
          boxShadow: mode === id ? "0 0 8px #a6e3c4" : "none",
        }} />
        {label}
      </div>
      <div className="text-[11px] mt-1" style={{ color: "#6b6b8a" }}>{desc}</div>
    </button>
  );

  return (
    <div>
      <div className="flex gap-3 mb-4">
        <Opt id="regex_llm" label="Regex + LLM" desc="Default. No setup. Runs everywhere (incl. hosted)." />
        <Opt id="presidio" label="Presidio" desc="spaCy NER via local Docker sidecar (~95% recall)." />
      </div>

      <div className="flex items-center gap-2 text-[11px] mb-3" style={{ color: "#6b6b8a" }}>
        Sidecar:
        <span style={{ color: reachable ? "#a6e3c4" : "#e3a6c9" }}>
          {reachable ? "✓ reachable" : "✗ not reachable"}
        </span>
        {cfg?.presidio_url && <span style={{ color: "#45455d" }}>· {cfg.presidio_url}</span>}
      </div>

      <input
        value={url} onChange={(e) => setUrl(e.target.value)}
        className="w-full glass-ghost rounded-xl px-3 py-2 text-[12px] outline-none mb-3 focus-ring"
        style={{ color: "#cdd6f4" }} placeholder="http://localhost:3000"
      />

      {err && <div className="text-[11px] mb-3" style={{ color: "#e3a6c9" }}>{err}</div>}

      <div className="glass-ghost rounded-xl p-3">
        <div className="text-[10px] uppercase tracking-wider mb-2" style={{ color: "#6b6b8a" }}>
          Run Presidio locally
        </div>
        <div className="flex items-center gap-2">
          <code className="flex-1 text-[11px] font-mono truncate" style={{ color: "#cba6f7" }}>
            {DOCKER_CMD}
          </code>
          <button onClick={copy} className="flex-shrink-0" style={{ color: "#9494aa" }} title="Copy">
            {copied ? <Check size={14} /> : <Copy size={14} />}
          </button>
        </div>
        <a href="https://github.com/microsoft/presidio" target="_blank" rel="noopener noreferrer"
           className="flex items-center gap-1 text-[11px] mt-2" style={{ color: "#9db4f0" }}>
          microsoft/presidio <ExternalLink size={11} />
        </a>
      </div>

      <p className="text-[10px] mt-3" style={{ color: "#45455d", lineHeight: 1.5 }}>
        Presidio requires a self-hosted backend that can reach the sidecar. On hosted
        Cloud Run the toggle stays on Regex + LLM. The switch is process-global (affects all
        sessions on this backend instance).
      </p>
    </div>
  );
}
