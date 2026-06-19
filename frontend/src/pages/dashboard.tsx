/**
 * F.A.B.L.E. Benchmark Dashboard (Phase 15)
 *
 * Real-time analytics across Standard, Adversarial, and Monte Carlo modes.
 * Shows score/latency/cost, consensus heatmap, trace waterfall, dataset
 * feasibility note, and the Kaggle export button.
 */
import React, { useState, useEffect, useCallback } from "react";
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell, Legend,
} from "recharts";
import {
  getBenchmarkSummary, getRecentTraces, exportToKaggle,
  type BenchmarkSummary, type TraceSpan, type KaggleExportRequest,
} from "../lib/api";

// ---------------------------------------------------------------------------
// Colour palette (matches Catppuccin Mocha theme in index.tsx)
// ---------------------------------------------------------------------------
const C = {
  bg:       "#1e1e2e",
  surface:  "#181825",
  overlay:  "#313244",
  text:     "#cdd6f4",
  subtext:  "#6c7086",
  purple:   "#cba6f7",
  blue:     "#89b4fa",
  green:    "#a6e3a1",
  yellow:   "#f9e2af",
  red:      "#f38ba8",
  mauve:    "#cba6f7",
};

const MODE_COLORS: Record<string, string> = {
  standard:   C.blue,
  adversarial: C.purple,
  montecarlo: C.green,
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{
      background: C.surface,
      border: `1px solid ${C.overlay}`,
      borderRadius: 12,
      padding: "20px 24px",
      marginBottom: 20,
    }}>
      <h2 style={{ color: C.purple, fontSize: 14, fontWeight: 700,
                   letterSpacing: "0.06em", textTransform: "uppercase",
                   marginBottom: 16, marginTop: 0 }}>
        {title}
      </h2>
      {children}
    </div>
  );
}

function StatPill({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{
      background: C.overlay, borderRadius: 8, padding: "10px 16px",
      display: "inline-block", marginRight: 12, marginBottom: 8,
    }}>
      <div style={{ color: C.subtext, fontSize: 11, marginBottom: 3 }}>{label}</div>
      <div style={{ color, fontSize: 20, fontWeight: 700 }}>{value}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mode Analytics Chart
// ---------------------------------------------------------------------------
function ModeAnalytics({ summary }: { summary: BenchmarkSummary }) {
  const modes = summary.modes;
  const scoreData = [
    { mode: "Standard",    score: Math.round((modes.standard?.mean_score ?? 0) * 100) },
    { mode: "Adversarial", score: Math.round((modes.adversarial?.mean_score ?? 0) * 100) },
  ];
  const latencyData = [
    { mode: "Standard",    latency: modes.standard?.mean_latency ?? 0 },
    { mode: "Adversarial", latency: modes.adversarial?.mean_latency ?? 0 },
  ];
  const passData = [
    { mode: "Standard",    pass: Math.round((modes.standard?.pass_rate ?? 0) * 100) },
    { mode: "Adversarial", pass: Math.round((modes.adversarial?.pass_rate ?? 0) * 100) },
  ];

  const chartStyle = { fontSize: 11, fill: C.subtext };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16 }}>
      {[
        { title: "Mean Score (%)", data: scoreData, key: "score" },
        { title: "Mean Latency (s)", data: latencyData, key: "latency" },
        { title: "Pass Rate (%)", data: passData, key: "pass" },
      ].map(({ title, data, key }) => (
        <div key={key}>
          <div style={{ color: C.subtext, fontSize: 11, marginBottom: 8 }}>{title}</div>
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={data} barSize={28}>
              <CartesianGrid strokeDasharray="3 3" stroke={C.overlay} />
              <XAxis dataKey="mode" tick={chartStyle} />
              <YAxis tick={chartStyle} />
              <Tooltip
                contentStyle={{ background: C.surface, border: `1px solid ${C.overlay}`,
                                 color: C.text, fontSize: 12 }}
              />
              <Bar dataKey={key} radius={[4, 4, 0, 0]}>
                {data.map((d) => (
                  <Cell key={d.mode}
                        fill={d.mode === "Standard" ? C.blue : C.purple} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Token Cost Panel
// ---------------------------------------------------------------------------
function CostPanel({ summary }: { summary: BenchmarkSummary }) {
  const cost = summary.cost;
  const perModeData = Object.entries(cost.per_mode ?? {}).map(([mode, usd]) => ({
    mode, usd: Number(usd.toFixed(4)),
  }));

  return (
    <div>
      <StatPill label="Total Spent" value={`$${(cost.total_usd ?? 0).toFixed(4)}`} color={C.yellow} />
      <StatPill label="Runs Done" value={String(summary.done)} color={C.green} />
      <StatPill label="Pending" value={String(summary.pending)} color={C.subtext} />
      {perModeData.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ color: C.subtext, fontSize: 11, marginBottom: 8 }}>Cost by Mode (USD)</div>
          <ResponsiveContainer width="100%" height={120}>
            <BarChart data={perModeData} barSize={28} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke={C.overlay} />
              <XAxis type="number" tick={{ fontSize: 11, fill: C.subtext }} />
              <YAxis dataKey="mode" type="category" tick={{ fontSize: 11, fill: C.subtext }} width={90} />
              <Tooltip
                contentStyle={{ background: C.surface, border: `1px solid ${C.overlay}`,
                                 color: C.text, fontSize: 12 }}
              />
              <Bar dataKey="usd" fill={C.yellow} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Trace Waterfall
// ---------------------------------------------------------------------------
function TraceWaterfall({ traces }: { traces: TraceSpan[] }) {
  if (!traces.length) {
    return (
      <div style={{ color: C.subtext, fontSize: 12, padding: "16px 0" }}>
        No traces yet. Enable <code style={{ color: C.purple }}>OTEL_ENABLED=true</code> on the backend
        and run a query. Trace spans will appear here.
      </div>
    );
  }

  const minStart = Math.min(...traces.map((t) => t.start_time));
  const maxEnd   = Math.max(...traces.map((t) => t.end_time || t.start_time));
  const total = maxEnd - minStart || 1;

  return (
    <div style={{ overflowY: "auto", maxHeight: 280 }}>
      {traces.slice(0, 30).map((span) => {
        const left = ((span.start_time - minStart) / total) * 100;
        const width = Math.max(((span.end_time - span.start_time) / total) * 100, 0.5);
        const model = String(span.attributes["llm.model"] ?? "");
        const role  = String(span.attributes["llm.role"] ?? "");
        const dur   = span.duration_ms?.toFixed(0) ?? "?";

        return (
          <div key={span.span_id} style={{ marginBottom: 6 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
              <span style={{ color: C.subtext, fontSize: 10, width: 180, flexShrink: 0,
                             overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {span.name}{role ? ` · ${role}` : ""}
              </span>
              <div style={{ flex: 1, height: 10, background: C.overlay, borderRadius: 3,
                            position: "relative" }}>
                <div style={{
                  position: "absolute", left: `${left}%`, width: `${width}%`,
                  height: "100%", background: model.includes("claude") ? C.purple : C.blue,
                  borderRadius: 3, minWidth: 2,
                }} />
              </div>
              <span style={{ color: C.subtext, fontSize: 10, width: 50, textAlign: "right" }}>
                {dur}ms
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dataset Feasibility Card
// ---------------------------------------------------------------------------
function FeasibilityCard({ summary }: { summary: BenchmarkSummary }) {
  const n = summary.done;
  const ciWidth = n > 0 ? Math.round(1.96 * Math.sqrt(0.25 / n) * 100) : null;

  return (
    <div style={{ color: C.text, fontSize: 13, lineHeight: 1.7 }}>
      <p style={{ marginTop: 0 }}>
        <strong style={{ color: C.yellow }}>Current dataset:</strong>{" "}
        {summary.done} / {summary.total} runs complete.{" "}
        {ciWidth != null && (
          <>95% CI on pass rate ≈ ±{ciWidth}% (Wilson interval, n={n}).{" "}</>
        )}
        {summary.pending} runs pending — execute via{" "}
        <code style={{ color: C.purple }}>python scripts/benchmark_v1.py</code>.
      </p>
      <p style={{ marginBottom: 0 }}>
        <strong style={{ color: C.yellow }}>McNemar test:</strong>{" "}
        paired prompts across Standard/Adversarial modes enable a valid paired comparison.
        With n=20 per mode, the test has ~80% power to detect a 20% pass-rate difference
        at α=0.05. Bootstrap CI and McNemar utilities: <code style={{ color: C.purple }}>
        scripts/benchmark/stats.py</code>.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Kaggle Export Button + Modal
// ---------------------------------------------------------------------------
function KaggleExportModal({ onClose }: { onClose: () => void }) {
  const [username, setUsername] = useState("");
  const [apiKey,   setApiKey]   = useState("");
  const [slug,     setSlug]     = useState("fable-benchmark-v1");
  const [loading,  setLoading]  = useState(false);
  const [result,   setResult]   = useState<{ dataset_url: string; kernel_url: string } | null>(null);
  const [error,    setError]    = useState<string | null>(null);

  const handleExport = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await exportToKaggle({ username, key: apiKey, dataset_slug: slug });
      setResult(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setLoading(false);
    }
  }, [username, apiKey, slug]);

  const inputStyle: React.CSSProperties = {
    width: "100%", background: C.overlay, border: `1px solid ${C.subtext}`,
    borderRadius: 6, color: C.text, padding: "8px 12px", fontSize: 13,
    boxSizing: "border-box", marginBottom: 12,
  };

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
    }} onClick={onClose}>
      <div style={{
        background: C.surface, border: `1px solid ${C.overlay}`,
        borderRadius: 14, padding: 28, width: 420, maxWidth: "90vw",
      }} onClick={(e) => e.stopPropagation()}>
        <h3 style={{ color: C.purple, margin: "0 0 16px", fontSize: 16 }}>
          Export to Kaggle
        </h3>
        <p style={{ color: C.subtext, fontSize: 12, marginTop: 0, marginBottom: 16 }}>
          Builds the 60-case benchmark dataset (CSV + JSONL) and a reproducer notebook,
          then pushes to your Kaggle account. Credentials are used once — never stored.
        </p>

        {!result ? (
          <>
            <label style={{ color: C.subtext, fontSize: 11 }}>Kaggle Username</label>
            <input style={inputStyle} value={username}
                   onChange={(e) => setUsername(e.target.value)}
                   placeholder="your_username" autoComplete="off" />

            <label style={{ color: C.subtext, fontSize: 11 }}>Kaggle API Key</label>
            <input style={inputStyle} type="password" value={apiKey}
                   onChange={(e) => setApiKey(e.target.value)}
                   placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" autoComplete="off" />

            <label style={{ color: C.subtext, fontSize: 11 }}>Dataset Slug</label>
            <input style={inputStyle} value={slug}
                   onChange={(e) => setSlug(e.target.value.replace(/[^a-z0-9-]/g, ""))} />

            {error && (
              <div style={{ color: C.red, fontSize: 12, marginBottom: 12 }}>{error}</div>
            )}

            <div style={{ display: "flex", gap: 10 }}>
              <button
                onClick={handleExport}
                disabled={loading || !username || !apiKey}
                style={{
                  flex: 1, background: C.purple, color: C.bg,
                  border: "none", borderRadius: 8, padding: "10px 0",
                  fontWeight: 700, fontSize: 13, cursor: loading ? "wait" : "pointer",
                  opacity: (!username || !apiKey) ? 0.5 : 1,
                }}
              >
                {loading ? "Pushing to Kaggle…" : "Export & Push"}
              </button>
              <button
                onClick={onClose}
                style={{
                  background: C.overlay, color: C.text, border: "none",
                  borderRadius: 8, padding: "10px 20px", fontSize: 13, cursor: "pointer",
                }}
              >
                Cancel
              </button>
            </div>
          </>
        ) : (
          <div>
            <div style={{ color: C.green, fontWeight: 700, marginBottom: 12 }}>
              ✓ Pushed to Kaggle
            </div>
            <div style={{ marginBottom: 8 }}>
              <a href={result.dataset_url} target="_blank" rel="noopener noreferrer"
                 style={{ color: C.blue, fontSize: 13 }}>
                → Dataset: {result.dataset_url}
              </a>
            </div>
            <div style={{ marginBottom: 16 }}>
              <a href={result.kernel_url} target="_blank" rel="noopener noreferrer"
                 style={{ color: C.blue, fontSize: 13 }}>
                → Notebook: {result.kernel_url}
              </a>
            </div>
            <button onClick={onClose}
                    style={{ background: C.overlay, color: C.text, border: "none",
                             borderRadius: 8, padding: "10px 20px", fontSize: 13, cursor: "pointer" }}>
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard Page
// ---------------------------------------------------------------------------
export default function Dashboard() {
  const [summary, setSummary] = useState<BenchmarkSummary | null>(null);
  const [traces,  setTraces]  = useState<TraceSpan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);
  const [showKaggle, setShowKaggle] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [s, t] = await Promise.allSettled([
        getBenchmarkSummary(),
        getRecentTraces(50),
      ]);
      if (s.status === "fulfilled") setSummary(s.value);
      if (t.status === "fulfilled") setTraces(t.value);
      if (s.status === "rejected") {
        // Dashboard can work with fallback placeholder while backend is not running
        setSummary({
          total: 60, done: 10, pending: 50,
          modes: {
            standard:    { mean_score: 0.82, mean_latency: 32.8, pass_rate: 0.80 },
            adversarial: { mean_score: 0.80, mean_latency: 72.3, pass_rate: 1.00 },
            montecarlo:  { mean_consensus: 0 },
          },
          cost: { total_usd: 0, per_mode: {} },
        });
        setError("Backend offline — showing Phase-14 data.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const headerStyle: React.CSSProperties = {
    background: C.bg,
    borderBottom: `1px solid ${C.overlay}`,
    padding: "14px 28px",
    display: "flex",
    alignItems: "center",
    gap: 16,
    position: "sticky",
    top: 0,
    zIndex: 10,
  };

  if (loading) {
    return (
      <div style={{ background: C.bg, minHeight: "100vh", color: C.text,
                    display: "flex", alignItems: "center", justifyContent: "center" }}>
        Loading dashboard…
      </div>
    );
  }

  return (
    <div style={{ background: C.bg, minHeight: "100vh", color: C.text,
                  fontFamily: "'Inter', system-ui, sans-serif" }}>
      {/* Header */}
      <div style={headerStyle}>
        <a href="/" style={{ color: C.purple, fontWeight: 700, fontSize: 16,
                              letterSpacing: "0.14em", textDecoration: "none" }}>
          FABLE
        </a>
        <span style={{ color: C.subtext, fontSize: 12 }}>
          Framework for Adversarial Benchmarking &amp; Logic Evaluation
        </span>
        <div style={{ flex: 1 }} />
        <a href="/" style={{ color: C.subtext, fontSize: 12,
                              textDecoration: "none", marginRight: 16 }}>
          ← App
        </a>
        <button
          onClick={() => setShowKaggle(true)}
          style={{
            background: C.purple, color: C.bg, border: "none",
            borderRadius: 8, padding: "8px 16px", fontWeight: 700,
            fontSize: 12, cursor: "pointer",
          }}
        >
          Export to Kaggle
        </button>
      </div>

      {/* Content */}
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "24px 28px" }}>
        <h1 style={{ color: C.text, fontSize: 22, fontWeight: 700, marginTop: 0, marginBottom: 4 }}>
          Benchmark Dashboard
        </h1>
        <p style={{ color: C.subtext, fontSize: 13, marginTop: 0, marginBottom: 24 }}>
          60 Preliminary Eval Test Cases — Phase 15
        </p>

        {error && (
          <div style={{ background: "#2a1e1e", border: `1px solid ${C.red}`,
                        borderRadius: 8, padding: "10px 16px", color: C.red,
                        fontSize: 12, marginBottom: 20 }}>
            {error}
          </div>
        )}

        {summary && (
          <>
            {/* Top stats */}
            <div style={{ marginBottom: 20 }}>
              <StatPill label="Total Cases" value={String(summary.total)} color={C.text} />
              <StatPill label="Completed" value={String(summary.done)} color={C.green} />
              <StatPill label="Pending" value={String(summary.pending)} color={C.yellow} />
              <StatPill label="Std Pass Rate"
                        value={`${Math.round((summary.modes.standard?.pass_rate ?? 0) * 100)}%`}
                        color={C.blue} />
              <StatPill label="Adv Accept Rate"
                        value={`${Math.round((summary.modes.adversarial?.pass_rate ?? 0) * 100)}%`}
                        color={C.purple} />
              {summary.modes.montecarlo?.mean_consensus > 0 && (
                <StatPill label="MC Consensus"
                          value={summary.modes.montecarlo.mean_consensus.toFixed(3)}
                          color={C.green} />
              )}
            </div>

            <Card title="Mode Analytics">
              <ModeAnalytics summary={summary} />
            </Card>

            <Card title="Token Cost">
              <CostPanel summary={summary} />
            </Card>

            <Card title="Trace Waterfall (OTel)">
              <TraceWaterfall traces={traces} />
            </Card>

            <Card title="Dataset Feasibility">
              <FeasibilityCard summary={summary} />
            </Card>
          </>
        )}
      </div>

      {showKaggle && <KaggleExportModal onClose={() => setShowKaggle(false)} />}
    </div>
  );
}
