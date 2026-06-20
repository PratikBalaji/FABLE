import React, { useState, useEffect, useCallback } from "react";
import dynamic from "next/dynamic";
import { motion, AnimatePresence } from "framer-motion";
import AgentThread from "@/components/panels/AgentThread";
import WarRoom from "@/components/panels/WarRoom";
import { PillSwitcher } from "@/components/ui/PillSwitcher";
import { SegmentedToggle } from "@/components/ui/SegmentedToggle";
import { StatusPill } from "@/components/ui/StatusPill";
import { ScorePills } from "@/components/ui/ScorePills";
import { Composer } from "@/components/composer/Composer";
import { Orbit, Swords, MessageSquare, BarChart3 } from "lucide-react";
import {
  runTask,
  runTaskStream,
  runAdversarialTask,
  runExperiment,
  getGraph,
  ingestFile,
  type AgentMessage,
  type RunResponse,
  type AdversarialRunResponse,
  type GraphState,
  type AdversarialMeta,
  type VerdictMeta,
  type RecycledMeta,
  type MonteCarloResponse,
} from "@/lib/api";
import ExperimentView from "@/components/panels/ExperimentView";
import HistorySidebar from "@/components/HistorySidebar";
import { saveEntry, type HistoryEntry } from "@/lib/history";

const PlanetaryGraph = dynamic(
  () => import("@/components/graph/PlanetaryGraph"),
  { ssr: false }
);

type Mode = "standard" | "adversarial" | "experiment";
type View = "graph" | "warroom" | "thread";

const MODE_OPTIONS  = [
  { value: "standard"    as Mode, label: "Standard" },
  { value: "adversarial" as Mode, label: "Adversarial" },
  { value: "experiment"  as Mode, label: "Experiment" },
];
// Experiment is a MODE, not a view — when mode==="experiment" the canvas shows
// ExperimentView directly and the view switcher is hidden.
// Icon-only view toggle for the minimal header (replaces the old centered pill row).
const VIEW_ICON_OPTIONS = [
  { value: "graph"   as View, label: "", icon: <Orbit size={14} /> },
  { value: "warroom" as View, label: "", icon: <Swords size={14} /> },
  { value: "thread"  as View, label: "", icon: <MessageSquare size={14} /> },
];

// ─── Main page ────────────────────────────────────────────────────────────────
export default function Home() {
  const [input,          setInput]          = useState("");
  const [messages,       setMessages]       = useState<AgentMessage[]>([]);
  const [graphState,     setGraphState]     = useState<GraphState | null>(null);
  const [scores,         setScores]         = useState<Record<string, number>>({});
  const [taskId,         setTaskId]         = useState<string | undefined>();
  const [modelUsed,      setModelUsed]      = useState<string>("");
  const [adversarialMeta,setAdversarialMeta]= useState<AdversarialMeta | null>(null);
  const [runSummary,     setRunSummary]     = useState<string>("");
  const [finalAnswer,    setFinalAnswer]    = useState<string>("");
  const [verdict,        setVerdict]        = useState<VerdictMeta | null>(null);
  const [isLoading,      setIsLoading]      = useState(false);
  const [error,          setError]          = useState<string | null>(null);
  const [mode,           setMode]           = useState<Mode>("standard");
  const [activeView,     setActiveView]     = useState<View>("graph");
  const [uploadedFiles,  setUploadedFiles]  = useState<File[]>([]);
  const [uploadStatus,   setUploadStatus]   = useState<string | null>(null);
  const [experimentResult, setExperimentResult] = useState<MonteCarloResponse | null>(null);
  const [recycledMeta,     setRecycledMeta]     = useState<RecycledMeta | null>(null);
  const [submittedPrompt,  setSubmittedPrompt]  = useState<string>("");
  const [historyOpen,      setHistoryOpen]      = useState(false);
  const [historyRefresh,   setHistoryRefresh]   = useState(0);

  useEffect(() => {
    getGraph().then(setGraphState).catch(() => {});
  }, []);

  // Re-fetch graph whenever user switches to the graph view
  useEffect(() => {
    if (activeView === "graph") {
      getGraph().then(setGraphState).catch(() => {});
    }
  }, [activeView]);

  // ─── File handling ─────────────────────────────────────────────────────────
  const handleFiles = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const newFiles = Array.from(files);
    setUploadedFiles((prev) => [...prev, ...newFiles]);
    for (const f of newFiles) {
      setUploadStatus(`Ingesting ${f.name}…`);
      try {
        const result = await ingestFile(f);
        setUploadStatus(`✓ ${f.name} — ${result.chunks_added} chunks indexed`);
      } catch {
        setUploadStatus(`✗ Failed to ingest ${f.name}`);
      }
    }
    setTimeout(() => setUploadStatus(null), 3000);
  }, []);

  const removeFile = (idx: number) =>
    setUploadedFiles((prev) => prev.filter((_, i) => i !== idx));

  // ─── Submit ────────────────────────────────────────────────────────────────
  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!input.trim() || isLoading) return;
      const promptText = input;
      setIsLoading(true);
      setError(null);
      setMessages([]);
      setScores({});
      setAdversarialMeta(null);
      setRunSummary("");
      setFinalAnswer("");
      setVerdict(null);
      setRecycledMeta(null);
      setExperimentResult(null);
      setSubmittedPrompt(promptText);

      try {
        if (mode === "experiment") {
          const result = await runExperiment({ input: promptText, n_variants: 4 });
          setExperimentResult(result);
          saveEntry("experiment", promptText, { kind: "experiment", result });
          setHistoryRefresh((n) => n + 1);
        } else if (mode === "adversarial") {
          const result: AdversarialRunResponse = await runAdversarialTask({ input: promptText });
          setMessages(result.messages);
          setTaskId(result.task_id);
          setScores(result.scores);
          setModelUsed(result.model_used);
          setGraphState(result.knowledge_graph);
          setAdversarialMeta(result.adversarial_meta);
          setRunSummary(result.run_summary ?? "");
          setFinalAnswer(result.final_answer ?? "");
          setVerdict(result.verdict ?? null);
          if (activeView === "graph") setActiveView("warroom");
          saveEntry("adversarial", promptText, {
            kind: "adversarial",
            messages: result.messages,
            scores: result.scores,
            modelUsed: result.model_used,
            graphState: result.knowledge_graph,
            runSummary: result.run_summary ?? "",
            finalAnswer: result.final_answer ?? "",
            verdict: result.verdict ?? null,
            adversarialMeta: result.adversarial_meta ?? null,
          });
          setHistoryRefresh((n) => n + 1);
        } else {
          // SSE streaming — messages appear as each agent completes
          const streamed: AgentMessage[] = [];
          let completePayload: {
            scores: Record<string, number>; modelUsed: string;
            graphState: GraphState | null; runSummary: string;
            finalAnswer: string; verdict: VerdictMeta | null; recycledMeta: RecycledMeta | null;
          } | null = null;
          for await (const event of runTaskStream({ input: promptText })) {
            if (event.type === "agent_message") {
              const { type: _t, ...msg } = event;
              streamed.push(msg as AgentMessage);
              setMessages((prev) => [...prev, msg as AgentMessage]);
              if (activeView === "graph") setActiveView("warroom");
            } else if (event.type === "complete") {
              setTaskId(event.task_id);
              setScores(event.scores);
              setModelUsed(event.model_used);
              setGraphState(event.knowledge_graph);
              setRunSummary(event.run_summary ?? "");
              setFinalAnswer(event.final_answer ?? "");
              setVerdict(event.verdict ?? null);
              const rm = (event as any).recycled_meta?.recycled ? (event as any).recycled_meta : null;
              if (rm) setRecycledMeta(rm);
              completePayload = {
                scores: event.scores, modelUsed: event.model_used,
                graphState: event.knowledge_graph, runSummary: event.run_summary ?? "",
                finalAnswer: event.final_answer ?? "", verdict: event.verdict ?? null, recycledMeta: rm,
              };
            } else if (event.type === "error") {
              throw new Error(event.detail);
            }
          }
          if (completePayload) {
            saveEntry("standard", promptText, {
              kind: "standard",
              messages: streamed,
              scores: completePayload.scores,
              modelUsed: completePayload.modelUsed,
              graphState: completePayload.graphState,
              runSummary: completePayload.runSummary,
              finalAnswer: completePayload.finalAnswer,
              verdict: completePayload.verdict,
              recycledMeta: completePayload.recycledMeta,
            });
            setHistoryRefresh((n) => n + 1);
          }
        }
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Request failed");
      } finally {
        setIsLoading(false);
      }
    },
    [input, isLoading, mode, activeView]
  );

  // Restore a past run from history (no network call)
  const handleSelectHistory = useCallback((entry: HistoryEntry) => {
    setError(null);
    setSubmittedPrompt(entry.prompt);
    const p = entry.payload;
    if (p.kind === "experiment") {
      setExperimentResult(p.result);
      setMode("experiment");
    } else {
      setExperimentResult(null);
      setMessages(p.messages);
      setScores(p.scores);
      setModelUsed(p.modelUsed);
      setGraphState(p.graphState);
      setRunSummary(p.runSummary);
      setFinalAnswer(p.finalAnswer);
      setVerdict(p.verdict);
      setAdversarialMeta(p.adversarialMeta ?? null);
      setRecycledMeta(p.recycledMeta ?? null);
      setMode(p.kind);
      setActiveView("warroom");
    }
    setHistoryOpen(false);
  }, []);

  const pipeline =
    mode === "adversarial"
      ? ["adv:planner","adv:actor","adv:critic","adv:validator","adv:refiner","adv:judge"]
      : ["analyst","critic","synthesizer"];

  const hasScores = Object.keys(scores).length > 0;
  const totalRuns = graphState?.stats?.totalRuns ?? 0;

  return (
    <div
      className="min-h-screen text-text font-sans overflow-hidden"
      style={{ background: "#080810" }}
    >
      {/* ─── Menubar (fixed, full-width glass pill) ──────────────────────────── */}
      <header
        className="fixed top-0 inset-x-0 z-50 flex items-center px-5 h-[52px]"
        style={{
          background: "rgba(8,8,16,0.82)",
          backdropFilter: "blur(40px) saturate(1.8)",
          WebkitBackdropFilter: "blur(40px) saturate(1.8)",
          boxShadow: "0 1px 0 rgba(180,160,232,0.07)",
        }}
      >
        {/* History toggle + Brand */}
        <div className="flex items-center gap-3 leading-none select-none">
          <button
            onClick={() => setHistoryOpen(true)}
            className="text-[#9494aa] hover:text-[#cba6f7] transition-colors text-base"
            title="Chat history"
            aria-label="Open history"
          >
            ☰
          </button>
          <span
            className="font-bold text-lg tracking-[0.16em] uppercase"
            style={{
              color: "#cba6f7",
              textShadow: "0 0 28px rgba(203,166,247,0.60), 0 0 8px rgba(203,166,247,0.28)",
            }}
          >
            FABLE
          </span>
        </div>

        {/* Mode switcher — centre */}
        <div className="flex-1 flex justify-center">
          <PillSwitcher
            options={MODE_OPTIONS}
            value={mode}
            onChange={(m) => {
              setMode(m);
              setMessages([]);
              setAdversarialMeta(null);
              setExperimentResult(null);
              setSubmittedPrompt("");
              // When switching away from experiment, restore graph view (not warroom);
              // only force-switch if the current view would be hidden (experiment has no sub-views).
              // no view switcher shown in experiment mode; otherwise stay on the
              // view the user was already on. Both cases are no-ops — activeView
              // state is preserved as-is for when the user leaves experiment mode.
            }}
            size="sm"
          />
        </div>

        {/* Right cluster — view icons · dashboard · adaptive status */}
        <div className="flex items-center gap-2.5">
          {mode !== "experiment" && (
            <SegmentedToggle
              size="sm"
              value={activeView}
              onChange={setActiveView}
              options={VIEW_ICON_OPTIONS}
            />
          )}
          <a
            href="/dashboard"
            className="flex items-center justify-center w-7 h-7 rounded-full transition-colors"
            style={{ color: "#9494aa" }}
            title="Benchmark Dashboard"
            aria-label="Open dashboard"
          >
            <BarChart3 size={15} />
          </a>
          <StatusPill
            isLoading={isLoading}
            verdict={adversarialMeta ? {
              label: adversarialMeta.judge_verdict,
              score: adversarialMeta.judge_score,
              accepted: adversarialMeta.judge_verdict === "ACCEPT",
            } : null}
            model={!isLoading ? modelUsed : undefined}
            totalRuns={totalRuns}
            taskId={taskId}
            recycled={recycledMeta?.recycled ? {
              similarity: recycledMeta.similarity,
              goldenRunId: recycledMeta.golden_run_id,
            } : null}
          />
        </div>
      </header>

      {/* ─── Main canvas ──────────────────────────────────────────────────────── */}
      <main
        className="h-screen overflow-hidden"
        style={{ paddingTop: 64, paddingBottom: 148 }}
      >
        <div className="h-full overflow-hidden">
          <AnimatePresence mode="wait">
            {mode === "experiment" ? (
              <motion.div
                key="experiment"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.22 }}
                className="h-full max-w-5xl mx-auto"
              >
                <ExperimentView
                  result={experimentResult}
                  isLoading={isLoading}
                  error={error}
                  prompt={submittedPrompt}
                />
              </motion.div>
            ) : activeView === "graph" ? (
              <motion.div
                key="graph"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.22 }}
                className="h-full"
              >
                <PlanetaryGraph graphState={graphState} />
              </motion.div>
            ) : activeView === "warroom" ? (
              <motion.div
                key="warroom"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.22 }}
                className="h-full"
              >
                <WarRoom
                  messages={messages}
                  isLoading={isLoading}
                  mode={mode}
                  scores={scores}
                  verdict={verdict}
                  runSummary={runSummary}
                  finalAnswer={finalAnswer}
                  adversarialMeta={adversarialMeta}
                  pipeline={pipeline}
                  prompt={submittedPrompt}
                />
              </motion.div>
            ) : (
              <motion.div
                key="thread"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.22 }}
                className="h-full px-6 py-4 max-w-3xl mx-auto"
              >
                <AgentThread messages={messages} isLoading={isLoading} prompt={submittedPrompt} />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>

      {/* ─── Floating composer (fixed bottom-centre) ──────────────────────────── */}
      <div
        className="fixed bottom-0 inset-x-0 z-40 flex flex-col items-center gap-3 pb-6 px-4"
        style={{
          background: "linear-gradient(to top, rgba(8,8,16,0.96) 40%, transparent)",
          paddingTop: 32,
          pointerEvents: "none",
        }}
      >
        {/* Score pills hover above composer */}
        <div style={{ pointerEvents: "auto" }}>
          <ScorePills scores={scores} visible={hasScores && !isLoading} />
        </div>

        {/* Composer input */}
        <div style={{ pointerEvents: "auto", width: "100%", maxWidth: 680 }}>
          <form onSubmit={handleSubmit}>
            <Composer
              value={input}
              onChange={setInput}
              onSubmit={handleSubmit}
              isLoading={isLoading}
              mode={mode}
              uploadedFiles={uploadedFiles}
              uploadStatus={uploadStatus}
              onFilesChange={handleFiles}
              onRemoveFile={removeFile}
              error={error}
            />
          </form>
        </div>
      </div>

      {/* ─── History sidebar (per-mode) ───────────────────────────────────────── */}
      <HistorySidebar
        open={historyOpen}
        mode={mode}
        onClose={() => setHistoryOpen(false)}
        onSelect={handleSelectHistory}
        refreshKey={historyRefresh}
      />
    </div>
  );
}
