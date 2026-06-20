/**
 * F.A.B.L.E. Benchmark Dashboard (Phase 15 — glassmorphic redesign)
 *
 * Sidebar + bento grid. Apple-style glass surfaces, soft palette.
 * Filters (mode / category / verdict / score / status / batch) live-filter
 * the run list + every chart. Rich charts: score×category, latency scatter,
 * cost breakdown, consensus heatmap, OTel trace waterfall, feasibility.
 */
import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  getBenchmarkSummary, getBenchmarkRuns, getRecentTraces,
  type BenchmarkSummary, type BenchmarkRun, type TraceSpan,
} from "../lib/api";
import { DashSidebar } from "../components/dashboard/DashSidebar";
import { BentoGrid, BentoCard } from "../components/dashboard/DashboardShell";
import { FilterRail, DEFAULT_FILTERS, applyFilters, type FilterState } from "../components/dashboard/FilterRail";
import { KpiCard } from "../components/dashboard/KpiCard";
import { ScoreByCategoryChart } from "../components/dashboard/ScoreByCategoryChart";
import { LatencyDistribution } from "../components/dashboard/LatencyDistribution";
import { CostBreakdown } from "../components/dashboard/CostBreakdown";
import { ConsensusHeatmap } from "../components/dashboard/ConsensusHeatmap";
import { TraceWaterfallPro } from "../components/dashboard/TraceWaterfallPro";
import { FeasibilityCard } from "../components/dashboard/FeasibilityCard";
import { KaggleExportModal } from "../components/dashboard/KaggleExportModal";

export default function Dashboard() {
  const [summary, setSummary] = useState<BenchmarkSummary | null>(null);
  const [runs, setRuns] = useState<BenchmarkRun[]>([]);
  const [traces, setTraces] = useState<TraceSpan[]>([]);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS());
  const [activeNav, setActiveNav] = useState("overview");
  const [showKaggle, setShowKaggle] = useState(false);

  const fetchData = useCallback(async () => {
    const [s, r, t] = await Promise.allSettled([
      getBenchmarkSummary(), getBenchmarkRuns(), getRecentTraces(60),
    ]);
    if (s.status === "fulfilled") setSummary(s.value);
    if (r.status === "fulfilled") setRuns(r.value);
    if (t.status === "fulfilled") setTraces(t.value);
    if (r.status === "rejected" || s.status === "rejected") {
      setNotice("Backend offline — showing whatever loaded. Start the API on :8000 for live data.");
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const filtered = useMemo(() => applyFilters(runs, filters), [runs, filters]);

  // KPI aggregates from filtered runs
  const kpi = useMemo(() => {
    const done = filtered.filter((r) => r.status === "done" && r.score != null);
    const pct = (r: BenchmarkRun) => (r.score! <= 1 ? r.score! * 100 : r.score!);
    const std = done.filter((r) => r.mode === "standard");
    const adv = done.filter((r) => r.mode === "adversarial");
    const mean = (xs: BenchmarkRun[]) => xs.length ? Math.round(xs.reduce((a, r) => a + pct(r), 0) / xs.length) : 0;
    const meanLat = (xs: BenchmarkRun[]) => {
      const l = xs.filter((r) => r.latency_s != null);
      return l.length ? (l.reduce((a, r) => a + (r.latency_s as number), 0) / l.length).toFixed(1) : "—";
    };
    const totalCost = filtered.reduce((a, r) => a + (r.cost_usd ?? 0), 0);
    return {
      stdScore: mean(std), advScore: mean(adv),
      stdLat: meanLat(std), advLat: meanLat(adv),
      totalCost, doneCount: filtered.filter((r) => r.status === "done").length,
      totalCount: filtered.length,
    };
  }, [filtered]);

  const scrollTo = (id: string) => {
    setActiveNav(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ color: "#6b6b8a" }}>
        <span className="animate-pulse-glow rounded-full px-4 py-2 glass-ghost">Loading dashboard…</span>
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ color: "#cdd6f4" }}>
      <div className="flex" style={{ minHeight: "100vh" }}>
        {/* Sidebar */}
        <div className="flex-shrink-0 sticky top-0 h-screen" style={{ width: 256 }}>
          <DashSidebar active={activeNav} onNavigate={scrollTo} onExport={() => setShowKaggle(true)}>
            <FilterRail filters={filters} onChange={setFilters}
                        batches={["latest"]} activeBatch="latest" onBatchChange={() => {}} />
          </DashSidebar>
        </div>

        {/* Main */}
        <main className="flex-1 px-7 py-7" style={{ maxWidth: 1180 }}>
          {notice && (
            <div className="glass-ghost rounded-xl px-4 py-2.5 mb-5 text-[12px]" style={{ color: "#f0c9a6" }}>
              {notice}
            </div>
          )}

          {/* KPI row */}
          <div id="overview" className="grid gap-4 mb-4" style={{ gridTemplateColumns: "repeat(4, minmax(0,1fr))" }}>
            <KpiCard label="Std Score" value={`${kpi.stdScore}%`} accent="#9db4f0"
                     sublabel={`${kpi.stdLat}s avg`} />
            <KpiCard label="Adv Score" value={`${kpi.advScore}%`} accent="#cba6f7"
                     sublabel={`${kpi.advLat}s avg`} />
            <KpiCard label="Cost" value={`$${kpi.totalCost.toFixed(4)}`} accent="#f0c9a6"
                     sublabel="filtered runs" />
            <KpiCard label="Coverage" value={`${kpi.doneCount}/${kpi.totalCount}`} accent="#a6e3c4"
                     sublabel="done / shown" />
          </div>

          <BentoGrid>
            <BentoCard id="modes" title="Score by Category × Mode" span={2}
                       subtitle="Mean rubric score per prompt category">
              <ScoreByCategoryChart runs={filtered} />
            </BentoCard>

            <BentoCard title="Latency vs Score"
                       subtitle="Each point a run · colour = mode">
              <LatencyDistribution runs={filtered} />
            </BentoCard>

            <BentoCard id="cost" title="Token Cost"
                       subtitle="Per-mode + cumulative (USD)">
              <CostBreakdown runs={filtered} />
            </BentoCard>

            <BentoCard title="Monte Carlo Consensus" span={2}
                       subtitle="Wording robustness by category">
              <ConsensusHeatmap runs={filtered} />
            </BentoCard>

            <BentoCard id="traces" title="Trace Waterfall" span={2}
                       subtitle="OpenTelemetry spans — hover for model / tokens / cost">
              <TraceWaterfallPro traces={traces} />
            </BentoCard>

            <BentoCard id="dataset" title="Dataset Feasibility" span={2}
                       subtitle="Sample size, confidence, McNemar power">
              <FeasibilityCard runs={filtered} />
            </BentoCard>
          </BentoGrid>

          <div className="text-[10px] mt-6" style={{ color: "#35354d" }}>
            Source: benchmarks/benchmark_v1.yaml · {summary?.total ?? 60} total cases ·
            filters apply across all panels.
          </div>
        </main>
      </div>

      {showKaggle && <KaggleExportModal onClose={() => setShowKaggle(false)} />}
    </div>
  );
}
