import React, { useState, useEffect, useCallback } from "react";
import dynamic from "next/dynamic";
import { motion, AnimatePresence } from "framer-motion";
import AgentThread from "@/components/panels/AgentThread";
import WarRoom from "@/components/panels/WarRoom";
import { PillSwitcher } from "@/components/ui/PillSwitcher";
import { ScorePills } from "@/components/ui/ScorePills";
import { Composer } from "@/components/composer/Composer";
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

const PlanetaryGraph = dynamic(
  () => import("@/components/graph/PlanetaryGraph"),
  { ssr: false }
);

type Mode = "standard" | "adversarial" | "experiment";
type View = "graph" | "warroom" | "thread" | "experiment";

const MODE_OPTIONS  = [
  { value: "standard"    as Mode, label: "Standard" },
  { value: "adversarial" as Mode, label: "Adversarial" },
  { value: "experiment"  as Mode, label: "Experiment" },
];
const VIEW_OPTIONS  = [
  { value: "graph"      as View, label: "Universe" },
  { value: "warroom"    as View, label: "War Room" },
  { value: "thread"     as View, label: "Thread" },
  { value: "experiment" as View, label: "Experiment" },
];

// ─── Judge verdict chip ───────────────────────────────────────────────────────
function JudgeChip({ meta }: { meta: AdversarialMeta }) {
  const accepted = meta.judge_verdict === "ACCEPT";
  const color = accepted ? "#a6e3a1" : "#f38ba8";
  return (
    <motion.span
      initial={{ opacity: 0, y: -4, scale: 0.9 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      transition={{ type: "spring", stiffness: 380, damping: 30 }}
      className="text-[10px] font-mono px-2.5 py-1 rounded-full font-medium"
      style={{
        background: `${color}12`,
        color,
        boxShadow: `0 0 0 1px ${color}30, 0 0 10px ${color}20`,
        textShadow: `0 0 10px ${color}80`,
      }}
      title={meta.judge_rationale}
    >
      {accepted ? "✓ ACCEPT" : "✗ REJECT"} {Math.round(meta.judge_score * 100)}%
      {meta.rounds_completed > 0 && ` · ${meta.rounds_completed}r`}
    </motion.span>
  );
}

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

  useEffect(() => {
    getGraph().then(setGraphState).catch(() => {});
  }, []);

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
      setIsLoading(true);
      setError(null);
      setMessages([]);
      setScores({});
      setAdversarialMeta(null);
      setRunSummary("");
      setFinalAnswer("");
      setVerdict(null);
      setRecycledMeta(null);

      try {
        if (mode === "experiment") {
          const result = await runExperiment({ input, n_variants: 4 });
          setExperimentResult(result);
          setActiveView("experiment");
        } else if (mode === "adversarial") {
          const result: AdversarialRunResponse = await runAdversarialTask({ input });
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
        } else {
          // SSE streaming — messages appear as each agent completes
          for await (const event of runTaskStream({ input })) {
            if (event.type === "agent_message") {
              const { type: _t, ...msg } = event;
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
              if ((event as any).recycled_meta?.recycled) setRecycledMeta((event as any).recycled_meta);
            } else if (event.type === "error") {
              throw new Error(event.detail);
            }
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
        {/* Brand */}
        <div className="flex flex-col leading-none select-none">
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
            }}
            size="sm"
          />
        </div>

        {/* Right meta chips */}
        <div className="flex items-center gap-2">
          <AnimatePresence>
            {adversarialMeta && <JudgeChip key="judge" meta={adversarialMeta} />}
            {recycledMeta?.recycled && (
              <motion.span
                key="recycled"
                initial={{ opacity: 0, y: -4, scale: 0.9 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                transition={{ type: "spring", stiffness: 380, damping: 30 }}
                className="text-[10px] font-mono px-2.5 py-1 rounded-full font-medium"
                style={{
                  background: "rgba(249,226,175,0.10)",
                  color: "#f9e2af",
                  boxShadow: "0 0 0 1px rgba(249,226,175,0.25), 0 0 10px rgba(249,226,175,0.12)",
                }}
                title={`Golden case ${recycledMeta.golden_run_id.slice(0, 8)}`}
              >
                ♻ {Math.round(recycledMeta.similarity * 100)}% match
              </motion.span>
            )}
          </AnimatePresence>
          {isLoading && (
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="text-[10px] font-mono"
              style={{ color: "#6b6b8a" }}
            >
              ● running…
            </motion.span>
          )}
          {modelUsed && !isLoading && (
            <span
              className="text-[10px] font-mono rounded-full px-2.5 py-1"
              style={{ background: "rgba(203,166,247,0.07)", color: "#9494aa" }}
            >
              {modelUsed.split("/").pop()}
            </span>
          )}
          {totalRuns > 0 && (
            <span
              className="text-[10px] font-mono rounded-full px-2.5 py-1 hidden sm:inline"
              style={{ background: "rgba(10,10,22,0.6)", color: "#6b6b8a" }}
            >
              {totalRuns} runs
            </span>
          )}
          {taskId && (
            <span
              className="text-[10px] font-mono rounded-full px-2 py-1 hidden md:inline"
              style={{ color: "#35354d" }}
            >
              #{taskId.slice(0, 6)}
            </span>
          )}
        </div>
      </header>

      {/* ─── View pill switcher (below menubar, centred) ──────────────────────── */}
      <div
        className="fixed z-40 flex justify-center"
        style={{ top: 60, insetInline: 0 }}
      >
        <PillSwitcher
          options={VIEW_OPTIONS}
          value={activeView}
          onChange={setActiveView}
          size="sm"
        />
      </div>

      {/* ─── Main canvas ──────────────────────────────────────────────────────── */}
      <main
        className="h-screen overflow-hidden"
        style={{ paddingTop: 108, paddingBottom: 148 }}
      >
        <div className="h-full overflow-hidden">
          <AnimatePresence mode="wait">
            {activeView === "graph" && (
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
            )}
            {activeView === "warroom" && (
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
                />
              </motion.div>
            )}
            {activeView === "thread" && (
              <motion.div
                key="thread"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.22 }}
                className="h-full px-6 py-4 max-w-3xl mx-auto"
              >
                <AgentThread messages={messages} isLoading={isLoading} />
              </motion.div>
            )}
            {activeView === "experiment" && (
              <motion.div
                key="experiment"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.22 }}
                className="h-full max-w-5xl mx-auto"
              >
                <ExperimentView result={experimentResult} isLoading={isLoading} />
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
    </div>
  );
}
