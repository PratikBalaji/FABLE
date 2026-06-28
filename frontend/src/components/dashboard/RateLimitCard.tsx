"use client";
import React, { useEffect, useState, useCallback } from "react";
import { getRateLimits, type RateLimits } from "../../lib/api";

// Phase 19: read-only view of the project's configured rate limits + per-identity
// concurrency. Live remaining quota is surfaced by the 429 handler in lib/api.ts on
// the X-RateLimit-* / Retry-After response headers.
export function RateLimitCard() {
  const [cfg, setCfg] = useState<RateLimits | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try { setCfg(await getRateLimits()); setErr(null); }
    catch (e: unknown) { setErr(e instanceof Error ? e.message : "offline"); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const Row = ({ label, value, desc }: { label: string; value: string; desc: string }) => (
    <div className="rounded-2xl p-3" style={{
      background: "rgba(12,12,28,0.45)",
      boxShadow: "0 0 0 1px rgba(180,160,232,0.06)",
    }}>
      <div className="flex items-center justify-between">
        <span className="text-[13px] font-medium" style={{ color: "#e8e8f5" }}>{label}</span>
        <code className="text-[12px] font-mono" style={{ color: "#cba6f7" }}>{value}</code>
      </div>
      <div className="text-[11px] mt-1" style={{ color: "#6b6b8a" }}>{desc}</div>
    </div>
  );

  if (err) return <div className="text-[11px]" style={{ color: "#e3a6c9" }}>Limits unavailable — {err}</div>;
  if (!cfg) return <div className="text-[11px]" style={{ color: "#6b6b8a" }}>Loading limits…</div>;

  return (
    <div className="flex flex-col gap-2">
      <Row label="Project-wide" value={cfg.global} desc="Backstop limit on every endpoint (per IP)." />
      <Row label="Standard run" value={cfg.run} desc="POST /run and /run/stream (per IP)." />
      <Row label="Adversarial run" value={cfg.adversarial} desc="POST /adversarial-run (per IP)." />
      <Row label="Concurrent / identity"
           value={String(cfg.max_concurrent_per_identity)}
           desc="Max in-flight runs per user (in-process). 0 = unlimited." />
      <p className="text-[10px] mt-1" style={{ color: "#45455d", lineHeight: 1.5 }}>
        Exceeding a limit returns HTTP 429 with a Retry-After header; the UI shows a
        retry message. Limits are set via RATE_LIMIT_* env vars on the backend.
      </p>
    </div>
  );
}
