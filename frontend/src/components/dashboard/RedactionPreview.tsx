"use client";
import React, { useState, useCallback } from "react";
import { previewRedaction, type RedactPreview, type RedactEntity } from "../../lib/api";

const SAMPLE = "Contact Jane Doe at jane@acme.com or 555-123-4567. She works at Acme Corp in Boston.";

// Soft per-type colors (desaturated, glass-friendly)
const TYPE_COLOR: Record<string, string> = {
  PERSON: "#cba6f7", EMAIL_ADDRESS: "#9db4f0", PHONE_NUMBER: "#a6e3c4",
  LOCATION: "#f0c9a6", ORGANIZATION: "#e3a6c9", CREDIT_CARD: "#e3a6c9",
  US_SSN: "#e3a6c9", IP_ADDRESS: "#9db4f0", API_KEY: "#e3a6c9",
};
const colorFor = (t: string) => TYPE_COLOR[t] ?? "#9494aa";

/** Highlight the original text by wrapping detected spans. */
function Highlighted({ text, entities }: { text: string; entities: RedactEntity[] }) {
  const sorted = [...entities].sort((a, b) => a.start - b.start);
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  sorted.forEach((e, i) => {
    if (e.start > cursor) parts.push(<span key={`t${i}`}>{text.slice(cursor, e.start)}</span>);
    const c = colorFor(e.type);
    parts.push(
      <span key={`e${i}`} title={`${e.type} · ${(e.score * 100).toFixed(0)}%`}
            style={{ background: `${c}26`, color: "#e8e8f5", borderRadius: 4,
                     padding: "1px 3px", boxShadow: `0 0 0 1px ${c}55` }}>
        {text.slice(e.start, e.end)}
      </span>
    );
    cursor = e.end;
  });
  if (cursor < text.length) parts.push(<span key="tail">{text.slice(cursor)}</span>);
  return <div className="text-[12px] leading-relaxed" style={{ color: "#9494aa" }}>{parts}</div>;
}

export function RedactionPreview() {
  const [text, setText] = useState(SAMPLE);
  const [res, setRes] = useState<RedactPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = useCallback(async () => {
    setBusy(true); setErr(null);
    try { setRes(await previewRedaction(text)); }
    catch (e: unknown) { setErr(e instanceof Error ? e.message : "preview failed"); }
    finally { setBusy(false); }
  }, [text]);

  return (
    <div>
      <textarea
        value={text} onChange={(e) => setText(e.target.value)} rows={3}
        className="w-full glass-ghost rounded-xl px-3 py-2 text-[12px] outline-none focus-ring resize-none"
        style={{ color: "#cdd6f4" }} placeholder="Paste text with names, emails, phones…"
      />
      <div className="flex items-center gap-3 mt-2 mb-3">
        <button onClick={run} disabled={busy || !text.trim()}
                className="rounded-xl px-4 py-2 text-[12px] font-semibold"
                style={{ background: "#cba6f7", color: "#0d0d1a", opacity: busy ? 0.6 : 1 }}>
          {busy ? "Redacting…" : "Preview redaction"}
        </button>
        {res && (
          <span className="text-[11px]" style={{ color: "#6b6b8a" }}>
            mode: <span style={{ color: "#cba6f7" }}>{res.mode}</span> · {res.entities.length} entities
          </span>
        )}
        {err && <span className="text-[11px]" style={{ color: "#e3a6c9" }}>{err}</span>}
      </div>

      {res && (
        <div className="grid gap-3" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <div className="glass-ghost rounded-xl p-3">
            <div className="text-[10px] uppercase tracking-wider mb-2" style={{ color: "#6b6b8a" }}>Detected</div>
            <Highlighted text={res.original} entities={res.entities} />
          </div>
          <div className="glass-ghost rounded-xl p-3">
            <div className="text-[10px] uppercase tracking-wider mb-2" style={{ color: "#6b6b8a" }}>Redacted (sent to LLM)</div>
            <div className="text-[12px] leading-relaxed font-mono" style={{ color: "#a6e3c4" }}>{res.redacted}</div>
          </div>
        </div>
      )}

      {res && res.entities.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-3">
          {res.entities.map((e, i) => (
            <span key={i} className="text-[10px] px-2 py-0.5 rounded-full"
                  style={{ background: `${colorFor(e.type)}1f`, color: "#e8e8f5",
                           boxShadow: `0 0 0 1px ${colorFor(e.type)}55` }}>
              {e.type} · {(e.score * 100).toFixed(0)}%
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
