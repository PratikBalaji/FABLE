import axios, { AxiosError } from "axios";

// When NEXT_PUBLIC_API_URL is set (Vercel deploy), route through the same-origin
// Next.js rewrite proxy at /api/* → avoids CORS and mixed-content issues entirely.
// Locally falls back to direct localhost.
const BASE = process.env.NEXT_PUBLIC_API_URL ? "/api" : "http://localhost:8000";

const api = axios.create({
  baseURL: BASE,
  timeout: 180_000, // 180s — adversarial pipeline (planner + rounds + rubric) can run long
  withCredentials: true,  // send identity cookie on cross-origin requests (F-008 CORS fix)
  headers: {
    "X-FABLE-Request": "1",  // CSRF protection header (F-008)
  },
});

// Map raw network errors to user-readable messages
api.interceptors.response.use(
  (res) => res,
  (err: AxiosError) => {
    if (err.code === "ECONNABORTED" || err.message?.includes("timeout")) {
      return Promise.reject(
        new Error("Backend timed out — the adversarial pipeline can take up to ~3 min. Try again.")
      );
    }
    if (!err.response) {
      return Promise.reject(
        new Error("Cannot reach backend. Set NEXT_PUBLIC_API_URL in Vercel env and redeploy.")
      );
    }
    const detail = (err.response.data as Record<string, unknown>)?.detail;
    return Promise.reject(
      new Error(typeof detail === "string" ? detail : err.message)
    );
  }
);

export interface AgentMessage {
  role: string;
  content: string;
  summary?: string;
  metadata: Record<string, unknown>;
  timestamp: string;
  message_id: string;
}

export interface VerdictMeta {
  verdict: string;   // "PASS"|"WARN"|"FAIL" (standard) or "ACCEPT"|"REJECT" (adversarial)
  score: number;
  rationale: string;
}

export interface GraphNode {
  id: string;
  label: string;
  type: "cluster" | "concept" | "model" | "domain";
  weight: number;
  position: { x: number; y: number; z: number };
  runCount: number;
  metadata: Record<string, unknown>;
}

export interface GraphEdge {
  source: string;
  target: string;
  weight: number;
  type: string;
}

export interface GraphStats {
  totalRuns: number;
  totalNodes: number;
  totalEdges: number;
  clusters: number;
  concepts: number;
}

export interface GraphState {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: GraphStats;
}

export interface RecycledMeta {
  recycled: boolean;
  golden_run_id: string;
  similarity: number;
}

export interface RunResponse {
  task_id: string;
  domain: string;
  pipeline: string[];
  messages: AgentMessage[];
  scores: Record<string, number>;
  model_used: string;
  knowledge_graph: GraphState;
  run_summary: string;
  final_answer: string;
  verdict: VerdictMeta;
  recycled_meta: RecycledMeta;
}

export interface AdversarialMeta {
  rounds_completed: number;
  max_rounds: number;
  judge_verdict: string;
  judge_score: number;
  judge_rationale: string;
  unresolved_issues: string[];
}

export interface AdversarialRunResponse extends RunResponse {
  adversarial_meta: AdversarialMeta;
}

// P5a: domain is now optional + open-ended. Backend defaults to "general".
export async function runTask(params: {
  input: string;
  domain?: string;
  pipeline?: string[];
  session_id?: string;
}): Promise<RunResponse> {
  const { data } = await api.post<RunResponse>("/run", params);
  return data;
}

export type StreamEvent =
  | ({ type: "agent_message" } & AgentMessage)
  | ({ type: "complete" } & Omit<RunResponse, "messages">)
  | { type: "error"; detail: string };

/**
 * SSE streaming variant of runTask. Yields events as each agent completes.
 * Uses fetch + ReadableStream because EventSource only supports GET.
 */
export async function* runTaskStream(params: {
  input: string;
  domain?: string;
  pipeline?: string[];
  session_id?: string;
}): AsyncGenerator<StreamEvent> {
  const url = (process.env.NEXT_PUBLIC_API_URL ? "/api" : "http://localhost:8000") + "/run/stream";
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-FABLE-Request": "1",
    },
    credentials: "include",
    body: JSON.stringify(params),
  });

  if (!resp.ok || !resp.body) {
    throw new Error(`Stream request failed: ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const raw = line.slice(6).trim();
        if (raw && raw !== "[DONE]") {
          try {
            yield JSON.parse(raw) as StreamEvent;
          } catch {
            // malformed SSE line — skip
          }
        }
      }
    }
  }
}

export async function runAdversarialTask(params: {
  input: string;
  domain?: string;
  session_id?: string;
}): Promise<AdversarialRunResponse> {
  const { data } = await api.post<AdversarialRunResponse>("/adversarial-run", params);
  return data;
}

export async function getGraph(): Promise<GraphState> {
  const { data } = await api.get<GraphState>("/graph");
  return data;
}

export async function ingestText(text: string, source = "manual"): Promise<{ chunks_added: number }> {
  const { data } = await api.post("/ingest", { text, source });
  return data;
}

// ── Phase 13: Monte Carlo Experiment ─────────────────────────────────────────

export interface MonteCarloResponse {
  prompt: string;
  variants: string[];
  models: string[];
  responses: string[][];          // [variant_idx][model_idx]
  similarity_matrix: number[][];
  consensus_score: number;
  divergence_pairs: Array<{
    idx_a: number; idx_b: number; similarity: number;
    variant_a: string; model_a: string;
    variant_b: string; model_b: string;
  }>;
  per_model_consensus: Record<string, number>;
}

export async function runExperiment(params: {
  input: string;
  n_variants?: number;
  models?: string[];
}): Promise<MonteCarloResponse> {
  const { data } = await api.post<MonteCarloResponse>("/experiment/run", params);
  return data;
}

// ---------------------------------------------------------------------------
// Dashboard / Benchmark / Export APIs (Phase 15)
// ---------------------------------------------------------------------------

export interface BenchmarkSummary {
  total: number;
  done: number;
  pending: number;
  modes: {
    standard: { mean_score: number; mean_latency: number; pass_rate: number };
    adversarial: { mean_score: number; mean_latency: number; pass_rate: number };
    montecarlo: { mean_consensus: number };
  };
  cost: {
    total_usd: number;
    per_mode: Record<string, number>;
  };
}

export async function getBenchmarkSummary(): Promise<BenchmarkSummary> {
  const { data } = await api.get<BenchmarkSummary>("/benchmark/summary");
  return data;
}

export type RunMode = "standard" | "adversarial" | "montecarlo";
export type RunCategory = "code" | "reasoning" | "factual" | "docqa" | "writing";

export interface BenchmarkRun {
  run_id: string;
  mode: RunMode;
  category: RunCategory;
  prompt: string;
  verdict: string | null;
  score: number | null;
  latency_s: number | null;
  cost_usd: number | null;
  status: "done" | "pending";
}

export async function getBenchmarkRuns(): Promise<BenchmarkRun[]> {
  const { data } = await api.get<BenchmarkRun[]>("/benchmark/runs");
  return data;
}

export interface TraceSpan {
  trace_id: string;
  span_id: string;
  name: string;
  start_time: number;
  end_time: number;
  duration_ms: number;
  status: string;
  attributes: Record<string, unknown>;
}

export async function getRecentTraces(limit = 50): Promise<TraceSpan[]> {
  const { data } = await api.get<TraceSpan[]>(`/traces?limit=${limit}`);
  return data;
}

export interface KaggleExportRequest {
  username: string;
  key: string;
  dataset_slug?: string;
}

export interface KaggleExportResponse {
  dataset_url: string;
  kernel_url: string;
}

export async function exportToKaggle(creds: KaggleExportRequest): Promise<KaggleExportResponse> {
  const { data } = await api.post<KaggleExportResponse>("/export/kaggle", {
    credentials: { username: creds.username, key: creds.key },
    dataset_slug: creds.dataset_slug ?? "fable-benchmark-v1",
  });
  return data;
}

export async function ingestFile(file: File, source?: string): Promise<{ chunks_added: number; source: string }> {
  const form = new FormData();
  form.append("file", file);
  form.append("source", source ?? file.name);
  const { data } = await api.post<{ chunks_added: number; source: string }>("/ingest/file", form, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 60_000,
  });
  return data;
}
