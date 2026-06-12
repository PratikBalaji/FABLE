import React, { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import AgentThread from "@/components/panels/AgentThread";
import { runTask, getGraph, type AgentMessage, type RunResponse, type GraphState } from "@/lib/api";

const PlanetaryGraph = dynamic(() => import("@/components/graph/PlanetaryGraph"), { ssr: false });

// P5a: domain selector retired. Prompt input is open-ended; backend defaults to "general".

export default function Home() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [graphState, setGraphState] = useState<GraphState | null>(null);
  const [scores, setScores] = useState<Record<string, number>>({});
  const [taskId, setTaskId] = useState<string | undefined>();
  const [modelUsed, setModelUsed] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"graph" | "thread">("graph");

  // Load existing graph on mount
  useEffect(() => {
    getGraph().then(setGraphState).catch(() => {});
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim()) return;
    setIsLoading(true);
    setError(null);
    setMessages([]);
    setScores({});
    try {
      const result: RunResponse = await runTask({ input });
      setMessages(result.messages);
      setTaskId(result.task_id);
      setScores(result.scores);
      setModelUsed(result.model_used);
      setGraphState(result.knowledge_graph);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-base text-text font-mono flex flex-col">
      {/* Header */}
      <header className="bg-crust border-b border-surface0 px-6 py-3 flex items-center gap-4">
        <span className="text-accent font-bold text-lg tracking-wider">F.A.B.L.E.</span>
        <span className="text-overlay text-xs hidden sm:inline">Federated Agent Bus & Lifecycle Engine</span>
        <div className="ml-auto flex items-center gap-4 text-xs text-overlay">
          {modelUsed && <span>model: {modelUsed.split("/").pop()}</span>}
          {taskId && <span>task: {taskId.slice(0, 8)}</span>}
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Left panel — input */}
        <aside className="w-80 min-w-64 bg-mantle border-r border-surface0 flex flex-col p-4 gap-4">
          <h2 className="text-subtext text-xs uppercase tracking-widest">Task Input</h2>
          <form onSubmit={handleSubmit} className="flex flex-col gap-3 flex-1">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask anything — code, finance, research, creative, factual..."
              className="flex-1 bg-surface0 border border-surface1 text-text rounded px-3 py-2 text-sm resize-none focus:outline-none focus:border-accent placeholder:text-overlay min-h-48"
            />
            {error && <p className="text-red text-xs">{error}</p>}
            <button
              type="submit"
              disabled={isLoading || !input.trim()}
              className="bg-accent text-base font-bold py-2 rounded hover:bg-accent/80 disabled:opacity-40 transition-colors text-sm"
            >
              {isLoading ? "Running agents..." : "Run Collaboration"}
            </button>
          </form>

          {/* Scores */}
          {Object.keys(scores).length > 0 && (
            <div className="border-t border-surface0 pt-3 space-y-1">
              <h3 className="text-subtext text-xs uppercase tracking-widest">Scores</h3>
              {Object.entries(scores).map(([k, v]) => (
                <div key={k} className="flex items-center gap-2 text-xs">
                  <span className="text-overlay w-24">{k}</span>
                  <div className="flex-1 h-1.5 bg-surface0 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-accent rounded-full transition-all"
                      style={{ width: `${v * 100}%` }}
                    />
                  </div>
                  <span className="text-text w-8 text-right">{(v * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}

          {/* Stats footer */}
          <div className="border-t border-surface0 pt-3 text-xs text-overlay space-y-1">
            <p>Pipeline: analyst → critic → synthesizer</p>
            <p>Learned routing via OpenRouter</p>
            {graphState?.stats && (
              <p className="text-accent">{graphState.stats.totalRuns} runs in knowledge engine</p>
            )}
          </div>
        </aside>

        {/* Main area */}
        <main className="flex-1 flex flex-col overflow-hidden relative">
          {/* Tab bar */}
          <div className="bg-crust border-b border-surface0 flex gap-0 z-10">
            {(["graph", "thread"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-5 py-2.5 text-xs uppercase tracking-wider transition-colors ${
                  activeTab === tab
                    ? "border-b-2 border-accent text-accent"
                    : "text-overlay hover:text-subtext"
                }`}
              >
                {tab === "graph" ? "Knowledge Universe" : "Agent Thread"}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-hidden relative">
            {activeTab === "graph" ? (
              <PlanetaryGraph graphState={graphState} />
            ) : (
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
