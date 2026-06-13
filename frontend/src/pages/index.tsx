import React, { useState, useEffect, useCallback, useRef } from "react";
import dynamic from "next/dynamic";
import { motion, AnimatePresence } from "framer-motion";
import { Upload, X, FileText, File } from "lucide-react";
import AgentThread from "@/components/panels/AgentThread";
import WarRoom from "@/components/panels/WarRoom";
import { SegmentedToggle } from "@/components/ui/SegmentedToggle";
import { cn } from "@/components/ui/cn";
import {
  runTask,
  runAdversarialTask,
  getGraph,
  ingestFile,
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

// ─── Uploaded file chip ───────────────────────────────────────────────────────
function FileChip({ name, onRemove }: { name: string; onRemove: () => void }) {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  const icon =
    ext === "pdf" ? (
      <FileText size={10} className="text-red" />
    ) : ext === "docx" || ext === "doc" ? (
      <FileText size={10} className="text-blue" />
    ) : (
      <File size={10} className="text-subtext" />
    );

  return (
    <motion.span
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.8 }}
      className="inline-flex items-center gap-1 glass-surface px-2 py-1 rounded-full text-[10px] font-mono text-subtext max-w-[160px]"
    >
      {icon}
      <span className="truncate">{name}</span>
      <button onClick={onRemove} className="text-overlay hover:text-red transition-colors ml-0.5">
        <X size={10} />
      </button>
    </motion.span>
  );
}

// ─── Score bar ────────────────────────────────────────────────────────────────
function ScoreBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 80 ? "#a6e3a1" : pct >= 50 ? "#f9e2af" : "#f38ba8";
  return (
    <div className="flex items-center gap-2 text-xs font-mono">
      <span className="text-overlay w-20 truncate">{label}</span>
      <div className="flex-1 h-1 bg-surface0/60 rounded-full overflow-hidden">
        <motion.div
          className="h-full rounded-full"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.7, ease: "easeOut" }}
          style={{ background: color, boxShadow: `0 0 6px ${color}80` }}
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
    <motion.span
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
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
    </motion.span>
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
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dropRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getGraph().then(setGraphState).catch(() => {});
  }, []);

  // ─── File handling ─────────────────────────────────────────────────────────
  const handleFiles = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const newFiles = Array.from(files);
    setUploadedFiles((prev) => [...prev, ...newFiles]);

    // Upload each file immediately
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

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles]
  );

  const handleDragOver = (e: React.DragEvent) => e.preventDefault();

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
        if (activeView === "graph") setActiveView("warroom");
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Request failed");
      } finally {
        setIsLoading(false);
      }
    },
    [input, isLoading, mode, activeView]
  );

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

      {/* ─── Header ───────────────────────────────────────────────────────────── */}
      <header className="glass rounded-none border-b border-white/[0.06] px-5 py-3 flex items-center gap-4 z-20 relative">
        {/* Brand */}
        <div className="flex flex-col leading-none">
          <span
            className="font-bold text-xl tracking-[0.15em] uppercase"
            style={{ color: "#cba6f7", textShadow: "0 0 28px rgba(203,166,247,0.55), 0 0 8px rgba(203,166,247,0.25)" }}
          >
            FABLE
          </span>
          <span className="text-[9px] text-overlay/70 font-sans tracking-wide hidden sm:block mt-0.5">
            Framework for Adversarial Benchmarking and Logic Evaluation
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
          <AnimatePresence>
            {adversarialMeta && <JudgeChip key="judge" meta={adversarialMeta} />}
          </AnimatePresence>
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
        {/* ─── Left sidebar ────────────────────────────────────────────────────── */}
        <aside className="w-72 min-w-56 flex flex-col p-3 gap-3 border-r border-white/[0.04] z-10">

          {/* Input panel */}
          <div
            ref={dropRef}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            className="glass flex flex-col gap-3 p-4 flex-1 relative"
          >
            <h2 className="text-subtext text-[10px] uppercase tracking-widest font-sans flex items-center gap-1.5">
              <span
                className="inline-block w-1.5 h-1.5 rounded-full"
                style={{
                  background: mode === "adversarial" ? "#f38ba8" : "#cba6f7",
                  boxShadow: "0 0 6px currentColor",
                }}
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
                  "bg-surface0/30 border transition-all duration-200 min-h-36",
                  "placeholder:text-overlay/50 focus:outline-none",
                  "focus:border-accent/60 focus:bg-surface0/50 focus:shadow-glow",
                  isLoading ? "border-surface1/40 opacity-60" : "border-surface0/60"
                )}
                disabled={isLoading}
              />

              {/* ─── Upload area ─────────────────────────────────────────────── */}
              <div className="space-y-2">
                {/* Drop zone / button */}
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className={cn(
                    "w-full flex items-center justify-center gap-2 py-2 rounded-lg border border-dashed",
                    "text-[10px] font-sans text-overlay transition-all duration-200",
                    "border-surface1/60 hover:border-accent/40 hover:text-accent hover:bg-accent/5",
                    isLoading && "opacity-40 pointer-events-none"
                  )}
                >
                  <Upload size={11} />
                  Drop or click to attach document
                  <span className="text-overlay/50">pdf · docx · md · txt</span>
                </button>

                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".pdf,.docx,.doc,.md,.markdown,.txt,.csv,.json"
                  className="hidden"
                  onChange={(e) => handleFiles(e.target.files)}
                />

                {/* File chips */}
                <AnimatePresence>
                  {uploadedFiles.length > 0 && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      className="flex flex-wrap gap-1"
                    >
                      {uploadedFiles.map((f, i) => (
                        <FileChip key={i} name={f.name} onRemove={() => removeFile(i)} />
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Upload status */}
                <AnimatePresence>
                  {uploadStatus && (
                    <motion.p
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="text-[10px] font-mono text-subtext/70"
                    >
                      {uploadStatus}
                    </motion.p>
                  )}
                </AnimatePresence>
              </div>

              {error && (
                <motion.div
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="rounded-lg px-3 py-2 bg-red/10 border border-red/20 text-red text-[10px] font-mono leading-relaxed"
                >
                  {error}
                </motion.div>
              )}

              <motion.button
                type="submit"
                disabled={isLoading || !input.trim()}
                whileTap={{ scale: 0.97 }}
                whileHover={{ scale: isLoading || !input.trim() ? 1 : 1.02 }}
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
                  ? `Running ${mode === "adversarial" ? "adversarial" : ""} agents…`
                  : mode === "adversarial"
                  ? "⚔  Run Adversarial"
                  : "▶  Run Collaboration"}
              </motion.button>
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
          <AnimatePresence>
            {Object.keys(scores).length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 8 }}
                className="glass p-4 space-y-2"
              >
                <h3 className="text-subtext text-[10px] uppercase tracking-widest font-sans">Scores</h3>
                {Object.entries(scores).map(([k, v]) => (
                  <ScoreBar key={k} label={k} value={v} />
                ))}
              </motion.div>
            )}
          </AnimatePresence>

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
            <AnimatePresence>
              {isLoading && (
                <motion.span
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="text-[10px] text-overlay font-mono ml-2"
                >
                  ● agents running…
                </motion.span>
              )}
            </AnimatePresence>
          </div>

          {/* View content */}
          <div className="flex-1 overflow-hidden relative">
            {activeView === "graph" && <PlanetaryGraph graphState={graphState} />}
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
