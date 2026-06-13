"""
Neural Knowledge Engine — dual-layer persistent knowledge system.

Layer 1: Embedding Graph
  Every run embeds input+output into vector space. Similar runs cluster
  into "knowledge planets". Connections = cosine similarity between clusters.

Layer 2: Weighted Concept Graph
  Explicit nodes (concepts/entities) and edges (relationships) extracted
  from every run. Weights increase with repeated co-occurrence across runs.

Together they form a growing neural substrate that gets smarter with use.
"""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from .embeddings import embed_text as _api_embed_text
from .elm_router import ELMRouter


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeNode:
    """A concept or entity in the knowledge graph."""
    node_id: str
    label: str
    node_type: str  # "concept", "entity", "domain", "model", "cluster"
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    position: dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0, "z": 0})
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    run_count: int = 0


@dataclass
class KnowledgeEdge:
    """A weighted connection between two knowledge nodes."""
    source: str
    target: str
    weight: float = 1.0
    edge_type: str = "related"  # "related", "derived_from", "critique_of", "model_excels_at"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class RunRecord:
    """A single run through the engine, stored for learning."""
    run_id: str
    input_text: str
    domain: str
    model_used: str
    output: str
    scores: dict[str, float]
    concepts: list[str]
    embedding: list[float]
    cluster_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# ---------------------------------------------------------------------------
# Knowledge Engine
# ---------------------------------------------------------------------------

class KnowledgeEngine:
    """Dual-layer neural knowledge system that learns from every run."""

    def __init__(self, data_dir: str = "./data/knowledge") -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.nodes: dict[str, KnowledgeNode] = {}
        self.edges: list[KnowledgeEdge] = []
        self.runs: list[RunRecord] = []
        self._embeddings_matrix: np.ndarray | None = None

        # Phase 11: ELM meta-scorer
        self._elm = ELMRouter()
        self._elm.load(self.data_dir / "elm_router.npz")

        self._load()

    # -- Persistence ---------------------------------------------------------

    def _graph_path(self) -> Path:
        return self.data_dir / "graph.json"

    def _runs_path(self) -> Path:
        return self.data_dir / "runs.jsonl"

    def _load(self) -> None:
        gp = self._graph_path()
        if gp.exists():
            data = json.loads(gp.read_text())
            for n in data.get("nodes", []):
                self.nodes[n["node_id"]] = KnowledgeNode(**n)
            self.edges = [KnowledgeEdge(**e) for e in data.get("edges", [])]

        rp = self._runs_path()
        if rp.exists():
            for line in rp.read_text().splitlines():
                if line.strip():
                    self.runs.append(RunRecord(**json.loads(line)))

        self._rebuild_embedding_matrix()

    def save(self) -> None:
        graph_data = {
            "nodes": [asdict(n) for n in self.nodes.values()],
            "edges": [asdict(e) for e in self.edges],
        }
        self._graph_path().write_text(json.dumps(graph_data, indent=2))
        # Phase 11: persist ELM weights alongside graph
        self._elm.save(self.data_dir / "elm_router.npz")

    def _append_run(self, run: RunRecord) -> None:
        with open(self._runs_path(), "a") as f:
            f.write(json.dumps(asdict(run)) + "\n")

    def _rebuild_embedding_matrix(self) -> None:
        if self.runs:
            self._embeddings_matrix = np.array([r.embedding for r in self.runs], dtype=np.float32)
        else:
            self._embeddings_matrix = None

    # -- Core operations -----------------------------------------------------

    def embed_text(self, text: str) -> list[float]:
        # P6b: OpenAI text-embedding-3-small via shared embeddings module.
        return _api_embed_text(text)

    def extract_concepts(self, text: str) -> list[str]:
        """Extract key concepts from text using simple NLP heuristics.
        In production, this would call an LLM for entity extraction."""
        import re
        words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        phrases = re.findall(r'\b(?:SQL|API|LLM|RAG|AWS|HTTP|CSS|HTML|FAISS|NLP)\b', text, re.IGNORECASE)
        keywords = set()
        for w in words:
            if len(w) > 2:
                keywords.add(w)
        for p in phrases:
            keywords.add(p.upper())
        return list(keywords)[:20]

    def find_cluster(self, embedding: list[float], threshold: float = 0.75) -> str | None:
        """Find the nearest knowledge cluster for an embedding."""
        cluster_nodes = [n for n in self.nodes.values() if n.node_type == "cluster" and n.embedding]
        if not cluster_nodes:
            return None
        query = np.array(embedding, dtype=np.float32)
        best_sim = -1.0
        best_id = None
        for node in cluster_nodes:
            node_emb = np.array(node.embedding, dtype=np.float32)
            sim = float(np.dot(query, node_emb))
            if sim > best_sim:
                best_sim = sim
                best_id = node.node_id
        return best_id if best_sim >= threshold else None

    def create_cluster(self, embedding: list[float], label: str, domain: str) -> str:
        """Create a new knowledge planet (cluster node)."""
        node_id = f"cluster_{uuid.uuid4().hex[:8]}"
        angle = len([n for n in self.nodes.values() if n.node_type == "cluster"]) * 0.618 * 6.28
        radius = 3.0 + np.random.uniform(0, 2)
        node = KnowledgeNode(
            node_id=node_id,
            label=label,
            node_type="cluster",
            embedding=embedding,
            position={
                "x": float(radius * np.cos(angle)),
                "y": float(np.random.uniform(-1, 1)),
                "z": float(radius * np.sin(angle)),
            },
            metadata={"domain": domain},
        )
        self.nodes[node_id] = node
        return node_id

    def ingest_run(
        self,
        input_text: str,
        output: str,
        domain: str,
        model_used: str,
        scores: dict[str, float],
    ) -> dict[str, Any]:
        """
        Process a completed run through both knowledge layers.
        Returns the updated graph state for visualization.
        """
        # Layer 1: Embedding graph
        combined_text = f"{input_text}\n\n{output}"
        embedding = self.embed_text(combined_text)

        # Find or create cluster
        cluster_id = self.find_cluster(embedding)
        if cluster_id is None:
            label = input_text[:50].strip().replace("\n", " ")
            cluster_id = self.create_cluster(embedding, label, domain)
        else:
            # Strengthen existing cluster
            cluster = self.nodes[cluster_id]
            cluster.run_count += 1
            cluster.weight = min(cluster.weight + 0.1, 10.0)
            # Update centroid via running average
            old_emb = np.array(cluster.embedding, dtype=np.float32)
            new_emb = np.array(embedding, dtype=np.float32)
            cluster.embedding = ((old_emb * (cluster.run_count - 1) + new_emb) / cluster.run_count).tolist()

        # Layer 2: Concept graph
        concepts = self.extract_concepts(combined_text)
        for concept in concepts:
            concept_id = f"concept_{concept.lower().replace(' ', '_')}"
            if concept_id not in self.nodes:
                angle = hash(concept_id) % 628 / 100.0
                self.nodes[concept_id] = KnowledgeNode(
                    node_id=concept_id,
                    label=concept,
                    node_type="concept",
                    position={
                        "x": float(1.5 * np.cos(angle)),
                        "y": float(np.random.uniform(-0.5, 0.5)),
                        "z": float(1.5 * np.sin(angle)),
                    },
                )
            else:
                self.nodes[concept_id].weight = min(self.nodes[concept_id].weight + 0.2, 10.0)
                self.nodes[concept_id].run_count += 1

            # Connect concept to cluster
            self._add_or_strengthen_edge(concept_id, cluster_id, "related")

        # Connect co-occurring concepts
        for i, c1 in enumerate(concepts):
            for c2 in concepts[i + 1:]:
                id1 = f"concept_{c1.lower().replace(' ', '_')}"
                id2 = f"concept_{c2.lower().replace(' ', '_')}"
                self._add_or_strengthen_edge(id1, id2, "co_occurs")

        # Track model performance
        model_node_id = f"model_{model_used.replace('/', '_')}"
        if model_node_id not in self.nodes:
            self.nodes[model_node_id] = KnowledgeNode(
                node_id=model_node_id,
                label=model_used.split("/")[-1],
                node_type="model",
                position={"x": 0, "y": float(3 + len(self.nodes) * 0.1), "z": 0},
            )
        model_node = self.nodes[model_node_id]
        model_node.run_count += 1
        avg_score = sum(scores.values()) / max(len(scores), 1)
        self._add_or_strengthen_edge(model_node_id, cluster_id, "model_excels_at", avg_score)

        # Store run
        run = RunRecord(
            run_id=str(uuid.uuid4()),
            input_text=input_text,
            domain=domain,
            model_used=model_used,
            output=output,
            scores=scores,
            concepts=concepts,
            embedding=embedding,
            cluster_id=cluster_id,
        )
        self.runs.append(run)
        self._append_run(run)
        self._rebuild_embedding_matrix()

        # Phase 11: feed this run into the ELM meta-scorer
        if scores:
            try:
                features = self._build_elm_features(embedding, input_text, domain)
                score_avg = sum(scores.values()) / len(scores)
                self._elm.add_sample(features, score_avg)
            except Exception:  # noqa: BLE001
                pass  # ELM failure must never break a run

        self.save()

        return self.get_graph_state()

    def _add_or_strengthen_edge(self, source: str, target: str, edge_type: str, weight_delta: float = 0.3) -> None:
        for edge in self.edges:
            if edge.source == source and edge.target == target and edge.edge_type == edge_type:
                edge.weight = min(edge.weight + weight_delta, 10.0)
                return
        self.edges.append(KnowledgeEdge(source=source, target=target, weight=1.0, edge_type=edge_type))

    # -- Query ---------------------------------------------------------------

    def get_relevant_context(self, query: str, top_k: int = 5) -> list[dict]:
        """Retrieve the most relevant past runs for RAG context injection."""
        if not self.runs or self._embeddings_matrix is None:
            return []
        query_emb = np.array(self.embed_text(query), dtype=np.float32)
        sims = self._embeddings_matrix @ query_emb
        top_indices = np.argsort(-sims)[:top_k]
        results = []
        for idx in top_indices:
            run = self.runs[idx]
            results.append({
                "input": run.input_text[:200],
                "output": run.output[:500],
                "score": float(sims[idx]),
                "domain": run.domain,
                "model": run.model_used,
            })
        return results

    def get_model_performance(self, domain: str | None = None) -> dict[str, dict[str, float]]:
        """Get average scores per model, optionally filtered by domain."""
        perf: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for run in self.runs:
            if domain and run.domain != domain:
                continue
            for k, v in run.scores.items():
                perf[run.model_used][k].append(v)
        return {
            model: {k: sum(v) / len(v) for k, v in scores.items()}
            for model, scores in perf.items()
        }

    def _build_elm_features(self, embedding: list[float], input_text: str, domain: str) -> np.ndarray:
        """Build 387-d feature vector for the ELM: 384-d embedding + 3 scalars."""
        emb = np.array(embedding, dtype=np.float32)
        scalars = np.array([
            min(len(input_text) / 10_000.0, 1.0),            # normalised prompt length
            1.0 if "adversarial" in domain.lower() else 0.0,  # adversarial flag
            min(len(self.runs) / 1_000.0, 1.0),               # experience signal
        ], dtype=np.float32)
        return np.concatenate([emb, scalars])

    def get_best_model_for(self, query: str) -> str | None:
        """Determine which model historically performs best for similar queries.

        Phase 11: consults the ELM meta-scorer first (after MIN_SAMPLES runs).
        Falls back to weighted nearest-neighbour heuristic when ELM not trained.
        """
        if not self.runs or self._embeddings_matrix is None:
            return None
        query_emb = np.array(self.embed_text(query), dtype=np.float32)

        # ── ELM path (after sufficient training data) ──────────────────────
        if self._elm.is_trained:
            # ELM predicts a scalar quality score for the current context.
            # We use it to weight the nearest-neighbour candidates.
            features = self._build_elm_features(
                query_emb.tolist(), query, "general"
            )
            elm_score = self._elm.predict(features)
            if elm_score is not None:
                # Blend: find top-10 similar runs, multiply similarity by ELM score
                sims = self._embeddings_matrix @ query_emb
                top_indices = np.argsort(-sims)[:10]
                model_scores: dict[str, list[float]] = defaultdict(list)
                for idx in top_indices:
                    run = self.runs[idx]
                    relevance = float(sims[idx])
                    avg_quality = sum(run.scores.values()) / max(len(run.scores), 1)
                    # ELM score modulates heuristic weight
                    model_scores[run.model_used].append(relevance * avg_quality * (0.5 + elm_score * 0.5))
                if model_scores:
                    best = max(model_scores, key=lambda m: sum(model_scores[m]) / len(model_scores[m]))
                    import structlog
                    structlog.get_logger().info(
                        "elm_predict_active",
                        elm_score=round(elm_score, 3),
                        best_model=best,
                        n_samples=self._elm.n_samples,
                    )
                    return best

        # ── Heuristic fallback ─────────────────────────────────────────────
        import structlog
        structlog.get_logger().info("elm_predict_heuristic", trained=self._elm.is_trained)
        sims = self._embeddings_matrix @ query_emb
        top_indices = np.argsort(-sims)[:10]
        heuristic_scores: dict[str, list[float]] = defaultdict(list)
        for idx in top_indices:
            run = self.runs[idx]
            relevance = float(sims[idx])
            avg_quality = sum(run.scores.values()) / max(len(run.scores), 1)
            heuristic_scores[run.model_used].append(relevance * avg_quality)
        if not heuristic_scores:
            return None
        return max(heuristic_scores, key=lambda m: sum(heuristic_scores[m]) / len(heuristic_scores[m]))

    # -- Visualization state -------------------------------------------------

    def get_graph_state(self) -> dict:
        """Return the full graph state for 3D visualization."""
        return {
            "nodes": [
                {
                    "id": n.node_id,
                    "label": n.label,
                    "type": n.node_type,
                    "weight": n.weight,
                    "position": n.position,
                    "runCount": n.run_count,
                    "metadata": n.metadata,
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "weight": e.weight,
                    "type": e.edge_type,
                }
                for e in self.edges
            ],
            "stats": {
                "totalRuns": len(self.runs),
                "totalNodes": len(self.nodes),
                "totalEdges": len(self.edges),
                "clusters": len([n for n in self.nodes.values() if n.node_type == "cluster"]),
                "concepts": len([n for n in self.nodes.values() if n.node_type == "concept"]),
            },
        }


knowledge_engine = KnowledgeEngine()
