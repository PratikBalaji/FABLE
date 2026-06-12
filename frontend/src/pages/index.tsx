import React, { useState, useEffect, useCallback } from "react";
import dynamic from "next/dynamic";
import AgentThread from "@/components/panels/AgentThread";
import WarRoom from "@/components/panels/WarRoom";
import { SegmentedToggle } from "@/components/ui/SegmentedToggle";
import { cn } from "@/components/ui/cn";
import {
  runTask,
  runAdversarialTask,
  getGraph,
  type AgentMessage,
  type RunResponse,
  type AdversarialRunResponse,
  type GraphState,
  type AdversarialMeta,
} from "@/lib/api";

const PlanetaryGraph = dynamic(
  () => import("@/components/graph/PlanetaryGraph"),
  { ssr: false }
);

type Mode = "standard" | "adversarial";
type View = "graph" | "warroom" | "thread";

const MODE_OPTIONS = [
  { value: "standard" as Mode, label: "Standard" },
  { value: "adversarial" as Mode, label: "Adversarial" },
];

const VIEW_OPTIONS = [
  { value: "graph" as View, label: "Universe" },
  { value: "warroom" as View, label: "War Room" },
  { value: "thread" as View, label: "Thread" },
];

// ─── Score bar ────────────────────────────────────────────────────────────────
function ScoreBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 80 ? "#a6e3a1" : pct >= 50 ? "#f9e2af" : "#f38ba8";

  return (
    <div className="flex items-center gap-2 text-xs font-mono">
      <span className="text-overlay w-20 truncate">{label}</span>
      <div className="flex-1 h-1 bg-surface0/60 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700 ease-out"
          style={{ width: `${pct}%`, background: color, boxShadow: `0 0 6px ${color}80` }}
        />
      </div>
      <span className="w-7 text-right" style={{ color }}>{pct}%</span>
    </div>
  );
}

// ─── Judge verdict chip ───────────────────────────────────────────────────────
function JudgeChip({ meta }: { meta: AdversarialMeta }) {
  const accepted = meta.judge_verdict === "ACCEPT";
  return (
    <span
      className={cn(
        "text-[10px] font-mono px-2 py-0.5 rounded-full border",
        accepted
          ? "bg-green/15 text-green border-green/30"
          : "bg-red/15 text-red border-red/30"
      )}
      title={meta.judge_rationale}
    >
      {accepted ? "✓ ACCEPT" : "✗ REJECT"} {Math.round(meta.judge_score * 100)}%
      {meta.rounds_completed > 0 && ` · ${meta.rounds_completed}r`}
    </span>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function Home() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [graphState, setGraphState] = useState<GraphState | null>(null);
  const [scores, setScores] = useState<Record<string, number>>({});
  const [taskId, setTaskId] = useState<string | undefined>();
  const [modelUsed, setModelUsed] = useState<string>("");
  const [adversarialMeta, setAdversarialMeta] = useState<AdversarialMeta | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("standard");
  const [activeView, setActiveView] = useState<View>("graph");

  useEffect(() => {
    getGraph().then(setGraphState).catch(() => {});
  }, []);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!input.trim() || isLoading) return;
      setIsLoading(true);
      setError(null);
      setMessages([]);
      setScores({});
      setAdversarialMeta(null);

      try {
        if (mode === "adversarial") {
          const result: AdversarialRunResponse = await runAdversarialTask({ input });
          setMessages(result.messages);
          setTaskId(result.task_id);
          setScores(result.scores);
          setModelUsed(result.model_used);
          setGraphState(result.knowledge_graph);
          setAdversarialMeta(result.adversarial_meta);
        } else {
          const result: RunResponse = await runTask({ input });
          setMessages(result.messages);
          setTaskId(result.task_id);
          setScores(result.scores);
          setModelUsed(result.model_used);
          setGraphState(result.knowledge_graph);
        }
        // Auto-switch to War Room after a run so the user sees agents
        if (activeView === "graph") setActiveView("warroom");
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Request failed");
      } finally {
        setIsLoading(false);
      }
    },
    [input, isLoading, mode, activeView]
  );

  // Enter submits, Shift+Enter adds newline
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit(e as unknown as React.FormEvent);
      }
    },
    [handleSubmit]
  );

  const pipeline =
    mode === "adversarial"
      ? ["adv:planner", "adv:actor", "adv:critic", "adv:validator", "adv:refiner", "adv:judge"]
      : ["analyst", "critic", "synthesizer"];

  return (
    <div className="min-h-screen text-text font-mono flex flex-col">
      {/* ─── Header ─────────────────────────────────────────────────────────── */}
      <header className="glass rounded-none border-b border-white/[0.06] px-5 py-2.5 flex items-center gap-4 z-20 relative">
        {/* Brand */}
        <div className="flex items-center gap-2">
          <span
            className="font-bold text-lg tracking-wider"
            style={{ color: "#cba6f7", textShadow: "0 0 20px rgba(203,166,247,0.5)" }}
          >
            F.A.B.L.E.
          </span>
          <span className="text-overlay text-[10px] hidden sm:inline font-sans">
            Federated Agent Bus &amp; Lifecycle Engine
          </span>
        </div>

        {/* Mode toggle — center */}
        <div className="flex-1 flex justify-center">
          <SegmentedToggle
            options={MODE_OPTIONS}
            value={mode}
            onChange={(m) => {
              setMode(m);
              setMessages([]);
              setAdversarialMeta(null);
            }}
          />
        </div>

        {/* Meta chips — right */}
        <div className="flex items-center gap-2 text-[10px] text-overlay font-mono">
          {adversarialMeta && <JudgeChip meta={adversarialMeta} />}
          {modelUsed && (
            <span className="glass-surface px-2 py-0.5 rounded-full">
              {modelUsed.split("/").pop()}
            </span>
          )}
          {taskId && (
            <span className="glass-surface px-2 py-0.5 rounded-full">
              #{taskId.slice(0, 8)}
            </span>
          )}
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* ─── Left sidebar ──────────────────────────────────────────────────── */}
        <aside className="w-72 min-w-56 flex flex-col p-3 gap-3 border-r border-white/[0.04] z-10">
          {/* Input panel */}
          <div className="glass flex flex-col gap-3 p-4 flex-1">
            <h2 className="text-subtext text-[10px] uppercase tracking-widest font-sans flex items-center gap-1.5">
              <span
                className="inline-block w-1.5 h-1.5 rounded-full"
                style={{ background: mode === "adversarial" ? "#f38ba8" : "#cba6f7", boxShadow: `0 0 6px currentColor` }}
              />
              Task Input
            </h2>

            <form onSubmit={handleSubmit} className="flex flex-col gap-3 flex-1">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  mode === "adversarial"
                    ? "Ask something challenging — 6 adversarial agents will deliberate...\n\nEnter to submit · Shift+Enter for newline"
                    : "Ask anything — code, finance, research, creative...\n\nEnter to submit · Shift+Enter for newline"
                }
                className={cn(
                  "flex-1 text-text text-xs rounded-lg px-3 py-2.5 resize-none",
                  "bg-surface0/30 border transition-all duration-200 min-h-40",
                  "placeholder:text-overlay/50 focus:outline-none",
                  "focus:border-accent/60 focus:bg-surface0/50 focus:shadow-glow",
                  isLoading ? "border-surface1/40 opacity-60" : "border-surface0/60"
                )}
                disabled={isLoading}
              />

              {error && (
                <div className="rounded-lg px-3 py-2 bg-red/10 border border-red/20 text-red text-[10px] font-mono leading-relaxed">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={isLoading || !input.trim()}
                className={cn(
                  "py-2.5 rounded-lg font-bold text-xs font-sans transition-all duration-200",
                  "disabled:opacity-40 disabled:cursor-not-allowed",
                  mode === "adversarial"
                    ? "bg-red/80 hover:bg-red text-white border border-red/30 hover:shadow-glow-red"
                    : "bg-accent hover:bg-accent/90 text-crust hover:shadow-glow",
                  isLoading && "animate-pulse"
                )}
              >
                {isLoading
                  ? `Running ${mode === "adversarial" ? "adversarial" : ""} agents...`
                  : mode === "adversarial"
                  ? "⚔  Run Adversarial"
                  : "▶  Run Collaboration"}
              </button>
            </form>

            {/* Pipeline indicator */}
            <div className="flex flex-wrap gap-1 pt-1 border-t border-white/[0.04]">
              {pipeline.map((role, i) => (
                <React.Fragment key={role}>
                  <span className="text-[9px] text-overlay font-mono bg-surface0/40 px-1.5 py-0.5 rounded">
                    {role.replace("adv:", "")}
                  </span>
                  {i < pipeline.length - 1 && (
                    <span className="text-[9px] text-overlay self-center">→</span>
                  )}
                </React.Fragment>
              ))}
            </div>
          </div>

          {/* Scores panel */}
          {Object.keys(scores).length > 0 && (
            <div className="glass p-4 space-y-2">
              <h3 className="text-subtext text-[10px] uppercase tracking-widest font-sans">Scores</h3>
              {Object.entries(scores).map(([k, v]) => (
                <ScoreBar key={k} label={k} value={v} />
              ))}
            </div>
          )}

          {/* Stats */}
          <div className="glass-surface px-4 py-3 text-[10px] text-overlay space-y-1">
            <p className="font-sans">Learned routing via OpenRouter</p>
            {graphState?.stats && (
              <p style={{ color: "#cba6f7" }}>
                {graphState.stats.totalRuns} runs in knowledge engine
              </p>
            )}
          </div>
        </aside>

        {/* ─── Main area ─────────────────────────────────────────────────────── */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* View toggle tab bar */}
          <div className="flex items-center gap-3 px-4 py-2 border-b border-white/[0.04] glass rounded-none z-10">
            <SegmentedToggle
              options={VIEW_OPTIONS}
              value={activeView}
              onChange={setActiveView}
              size="sm"
            />
            {isLoading && (
              <span className="text-[10px] text-overlay font-mono animate-pulse ml-2">
                ● agents running...
              </span>
            )}
          </div>

          {/* View content */}
          <div className="flex-1 overflow-hidden relative">
            {activeView === "graph" && (
              <PlanetaryGraph graphState={graphState} />
            )}
            {activeView === "warroom" && (
              <WarRoom messages={messages} isLoading={isLoading} mode={mode} />
            )}
            {activeView === "thread" && (
              <div className="p-4 h-full">
                <AgentThread messages={messages} isLoading={isLoading} />
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
