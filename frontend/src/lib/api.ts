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
