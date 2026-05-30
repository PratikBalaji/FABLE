import axios from "axios";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const api = axios.create({ baseURL: BASE });

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

export async function runTask(params: {
  input: string;
  domain: "code_review" | "finance";
  pipeline?: string[];
}): Promise<RunResponse> {
  const { data } = await api.post<RunResponse>("/run", params);
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
