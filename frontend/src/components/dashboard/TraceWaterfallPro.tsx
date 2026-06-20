"use client";
import React, { useState } from "react";
import type { TraceSpan } from "../../lib/api";

/** Enhanced OTel trace waterfall with per-span hover detail. */
export function TraceWaterfallPro({ traces }: { traces: TraceSpan[] }) {
  const [hover, setHover] = useState<string | null>(null);

  if (!traces.length) {
    return (
      <div className="text-[12px] py-6 px-1" style={{ color: "#6b6b8a", lineHeight: 1.7 }}>
        No spans captured. Enable{" "}
        <code style={{ color: "#cba6f7" }}>OTEL_ENABLED=true</code> on the backend and run a
        query — span timings (model, role, tokens, cost) will stream into this waterfall.
      </div>
    );
  }

  const minStart = Math.min(...traces.map((t) => t.start_time));
  const maxEnd = Math.max(...traces.map((t) => t.end_time || t.start_time));
  const total = maxEnd - minStart || 1;

  return (
    <div className="overflow-y-auto pr-1" style={{ maxHeight: 320 }}>
      {traces.slice(0, 40).map((span) => {
        const left = ((span.start_time - minStart) / total) * 100;
        const width = Math.max(((span.end_time - span.start_time) / total) * 100, 0.6);
        const model = String(span.attributes["llm.model"] ?? "");
        const role = String(span.attributes["llm.role"] ?? "");
        const tokensIn = span.attributes["llm.tokens.input"];
        const tokensOut = span.attributes["llm.tokens.output"];
        const cost = span.attributes["llm.cost.usd"];
        const dur = span.duration_ms?.toFixed(0) ?? "?";
        const bar = model.includes("claude") ? "#cba6f7" : "#9db4f0";
        const active = hover === span.span_id;

        return (
          <div key={span.span_id} className="mb-1.5"
               onMouseEnter={() => setHover(span.span_id)}
               onMouseLeave={() => setHover(null)}>
            <div className="flex items-center gap-2">
              <span className="text-[10px] truncate flex-shrink-0" style={{ width: 170, color: active ? "#cdd6f4" : "#6b6b8a" }}>
                {span.name.replace("fable.", "")}{role ? ` · ${role}` : ""}
              </span>
              <div className="flex-1 h-2.5 rounded-full relative" style={{ background: "rgba(180,160,232,0.06)" }}>
                <div className="absolute h-full rounded-full transition-all"
                     style={{
                       left: `${left}%`, width: `${width}%`, minWidth: 3,
                       background: bar,
                       boxShadow: active ? `0 0 10px ${bar}88` : "none",
                       opacity: active ? 1 : 0.8,
                     }} />
              </div>
              <span className="text-[10px] tabular-nums flex-shrink-0" style={{ width: 48, textAlign: "right", color: "#6b6b8a" }}>
                {dur}ms
              </span>
            </div>
            {active && (
              <div className="ml-[178px] mt-1 text-[10px] font-mono flex gap-3" style={{ color: "#9494aa" }}>
                {model && <span>{model.split("/").pop()}</span>}
                {tokensIn != null && <span>↓{String(tokensIn)}</span>}
                {tokensOut != null && <span>↑{String(tokensOut)}</span>}
                {cost != null && <span style={{ color: "#f0c9a6" }}>${Number(cost).toFixed(5)}</span>}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
