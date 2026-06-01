# F.A.B.L.E. — Framework of Adversarial Benchmarking & Logic Engine 

Multi-agent orchestration platform coordinating Claude + auxiliary LLMs across domain-specific collaborative workflows, with RAG, evaluation, an Obsidian-style UI, and Kaggle notebook export.

## Architecture

```
backend/
  agents/       # Agent roles: Analyst, Critic, Synthesizer, Router
  rag/          # Ingestion, chunking, embedding, retrieval
  router/       # Multi-LLM routing (Claude + OpenAI/Groq)
  evaluation/   # Rubric scoring, multi-agent vs single-agent benchmarks
  domains/      # Domain plugins: code_review, finance
  api/          # FastAPI app, WebSocket streams
  core/         # Bus, lifecycle, feedback loop

frontend/
  src/
    components/
      graph/    # Knowledge-graph view (React Flow)
      panels/   # Multi-panel notes + agent thread views
      ui/       # Shared dark-theme components

infra/
  docker/       # Compose + Dockerfiles
  aws/          # CDK / Terraform stubs

notebooks/      # Kaggle-ready .ipynb exports
```

## Phases

| Phase | Focus |
|-------|-------|
| 1 | Orchestration Core — agent bus, collaboration loop, feedback logging |
| 2 | RAG Foundation — ingest → chunk → embed → retrieve → cite |
| 3 | Multi-LLM Support — model router, response normalization |
| 4 | Domain Implementations — Code Review + Finance |
| 5 | UI + Export — Obsidian-style UI, knowledge graph, Kaggle .ipynb |
| 6 | Evaluation + Polish — benchmarks, demo, docs |

## Quick Start

```bash
# Backend
cd backend && pip install -e ".[dev]"
uvicorn api.main:app --reload

# Frontend
cd frontend && npm install && npm run dev
```

## Requirements

- Python 3.11+
- Node 20+
- Docker
- AWS CLI (for deployment)
- Anthropic API key
- Secondary LLM API key (OpenAI or Groq)
