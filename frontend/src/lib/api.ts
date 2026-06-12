import axios, { AxiosError } from "axios";

// When NEXT_PUBLIC_API_URL is set (Vercel deploy), route through the same-origin
// Next.js rewrite proxy at /api/* → avoids CORS and mixed-content issues entirely.
// Locally falls back to direct localhost.
const BASE = process.env.NEXT_PUBLIC_API_URL ? "/api" : "http://localhost:8000";

const api = axios.create({
  baseURL: BASE,
  timeout: 120_000, // 120s covers Cloud Run cold start + multi-LLM pipeline
});

// Map raw network errors to user-readable messages
api.interceptors.response.use(
  (res) => res,
  (err: AxiosError) => {
    if (err.code === "ECONNABORTED" || err.message?.includes("timeout")) {
      return Promise.reject(
        new Error("Backend timed out — try again (Cloud Run cold start can take ~10s)")
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
  metadata: Record<string, unknown>;
  timestamp: string;
  message_id: string;
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
