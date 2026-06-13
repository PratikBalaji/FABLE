# FABLE — Framework for Adversarial Benchmarking and Logic Evaluation

Multi-agent adversarial benchmarking platform coordinating frontier LLMs across collaborative and adversarial deliberation workflows, with PII-safe RAG, per-user semantic memory, glassmorphic UI, and Kaggle notebook export.

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
  docker/       # Compose + Dockerfiles (incl. K8s coordinator/agent-group)
  k8s/          # Kubernetes manifests (kind local dev)
  cloudrun/     # GCP Cloud Run deployment
  aws/          # CDK / Terraform stubs

notebooks/      # Kaggle-ready .ipynb exports
```

## Phases

| Phase | Focus |
|-------|-------|
| 1 | Orchestration Core — adversarial agent bus, 6-role pipeline, collaboration loop |
| 2 | Multi-User Platform — Supabase Auth, per-user memory, AES-256-GCM credential encryption |
| 3 | Guardrails — two-layer safety (rules + Llama-Guard classifier), audit log |
| 4 | Privacy & Identity — pseudonymous-first identity, PII redact/reinject, entity map |
| 5 | Deploy ($0/mo) — Presidio→regex+LLM, sentence-transformers→OpenAI, Cloud Run |
| 6 | ELM — Embedded Language Model (Phi-3 ONNX) for dynamic adversarial role declaration |
| 7 | K8s — Kubernetes (kind) local agent scaling; 3 pod groups + coordinator |
| 8 | Security Hardening — 40-finding appsec audit; 10 critical/high patches applied |
| 9 | Document Upload — PDF/DOCX/MD extraction via pypdf + python-docx; glassmorphic UI |

**Adversarial rounds:** Default `max_rounds = 2` to minimize API cost. Judge terminates early (round 1) when score ≥ 0.80. Configurable up to 3+ via `ADVERSARIAL_MAX_ROUNDS` env var when task complexity and budget warrant; hard ceiling enforced server-side at 10.

**Acronym:** FABLE = **F**ramework for **A**dversarial **B**enchmarking and **L**ogic **E**valuation. *Note:* The codebase uses "Embedded Language Model" for the Phi-3 ONNX role-declaration component (P6/ELM). A separate R&D track explores Extreme Learning Machine as a fast meta-scorer — see RESEARCH_LOG Phase 10.

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
- Docker (for Cloud Run deploy)
- OpenAI API key (for embeddings — text-embedding-3-small, dim=384)
- OpenRouter API key (for LLM gateway — adversarial pipeline + classifier)
- Supabase project (free tier — Postgres + pgvector + Auth)

## Deploy — $0/mo path (P6)

F.A.B.L.E. ships on a zero fixed-cost stack across three free tiers:

| Component | Provider | Plan | Notes |
|-----------|----------|------|-------|
| Frontend | Vercel | Hobby | Next.js, edge-cached |
| Backend | Google Cloud Run | Free tier | 2M req/mo, 360k vCPU-sec, scales to zero, ~5-8s cold start |
| Database + Auth + Vector | Supabase | Free tier | 500MB DB, RLS, pgvector HNSW |
| Embeddings | OpenAI | Pay-as-you-go | text-embedding-3-small @ ~$0.003/mo light usage |
| LLM gateway | OpenRouter | Pay-as-you-go | Per-call billing on adversarial pipeline |

**Variable cost only**: OpenAI embeddings (~$0.02 per 1M tokens) + OpenRouter LLM calls (~$0.001/run).

### Backend (Cloud Run) one-time setup

```bash
# 1. Build + push image (or use --source for buildpack)
gcloud auth login
gcloud config set project <YOUR_GCP_PROJECT>
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

# 2. Store secrets (one-time)
echo -n "$OPENROUTER_API_KEY"        | gcloud secrets create fable-openrouter-key       --data-file=-
echo -n "$OPENAI_API_KEY"            | gcloud secrets create fable-openai-key           --data-file=-
echo -n "$SUPABASE_URL"              | gcloud secrets create fable-supabase-url         --data-file=-
echo -n "$SUPABASE_ANON_KEY"         | gcloud secrets create fable-supabase-anon        --data-file=-
echo -n "$SUPABASE_SERVICE_ROLE_KEY" | gcloud secrets create fable-supabase-service     --data-file=-
echo -n "$APP_ENCRYPTION_KEY"        | gcloud secrets create fable-app-encryption       --data-file=-
echo -n "$IDENTITY_COOKIE_SECRET"    | gcloud secrets create fable-identity-cookie      --data-file=-

# 3. Deploy
bash infra/cloudrun/deploy.sh
```

Generate the two app secrets locally before storing:
```bash
python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"   # APP_ENCRYPTION_KEY
python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"   # IDENTITY_COOKIE_SECRET
```

### Frontend (Vercel) one-time setup

Set in Vercel project env:
```
NEXT_PUBLIC_SUPABASE_URL=https://<ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon publishable key>
NEXT_PUBLIC_API_URL=https://<your-cloud-run-service>-uc.a.run.app
```

### Cross-origin notes

- Cookies: `COOKIE_SAMESITE=none` + `COOKIE_SECURE=true` on Cloud Run env (so the `fable_id` cookie crosses the Vercel ↔ Cloud Run origin boundary).
- CORS: backend reads `APP_URL`; set to your Vercel frontend URL on Cloud Run env.
- Local dev: leave `COOKIE_SAMESITE=lax` and `COOKIE_SECURE=false` for `http://localhost`.

### Schema

Apply `infra/supabase/schema.sql` via the Supabase SQL Editor. The file is idempotent — safe to re-run after each phase that adds new tables.

### Trimmed image

The Cloud Run image excludes Presidio, spaCy, `sentence-transformers`, and `torch` to fit the free tier comfortably (<300 MB). PII redaction uses regex + a small LLM call (P6a); embeddings call OpenAI directly (P6b).

## Security — Production Required Variables

Add these to Cloud Run `--set-env-vars` / `--set-secrets` (see `infra/cloudrun/deploy.sh`):

```bash
CORS_ORIGINS=https://your-vercel-app.vercel.app   # restrict CORS from wildcard
AGENT_INTERNAL_TOKEN=<base64 32 random bytes>      # coordinator→pod auth (K8s mode)
RATE_LIMIT_RUN=20/minute                           # per-IP rate limit on /run
RATE_LIMIT_ADV=5/minute                            # per-IP rate limit on /adversarial-run
```

See `SECURITY_AUDIT_STATE.md` for the full 40-finding audit report and remaining patch backlog.

## ELM — Dynamic Role Declaration (P6)

An optional local ONNX model (Phi-3-mini, ~1.7GB) that dynamically generates system prompts, token budgets, and model assignments for each adversarial agent role based on task context. Disabled by default.

```bash
# Install ELM dependencies
pip install -e ".[elm]"

# Download the model (~1.7GB)
python scripts/download_elm_model.py

# Enable
export ELM_ENABLED=true
export ELM_MODEL_PATH=./data/models/phi-3-mini/cpu_and_mobile/cpu-int4-rtn-block-32
```

When disabled (`ELM_ENABLED=false`, the default), the pipeline uses the same hardcoded role declarations as before — zero behavior change.

## Kubernetes — Local Agent Scaling (P7)

Run adversarial agents as containerized pods locally via [kind](https://kind.sigs.k8s.io/):

```
Coordinator (API + lifecycle) ──HTTP──→ Planning Pod (Planner + Judge)
                               ──HTTP──→ Execution Pod (Actor + Refiner)
                               ──HTTP──→ Review Pod (Critic + Validator)
```

Each pod group scales independently via HPA. Prerequisites: Docker, kind, kubectl.

```bash
# One-command setup
./infra/k8s/setup.sh

# Access
curl http://localhost:8000/health

# Tear down
./infra/k8s/teardown.sh
```

Production stays on Cloud Run (`K8S_MODE=false` default). See RESEARCH_LOG.md P8 for the GKE Autopilot production scaling path.
