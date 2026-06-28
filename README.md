# FABLE — Framework for Adversarial Benchmarking & Logic Evaluation

> Multi-agent LLM benchmarking platform: adversarial deliberation, PII-safe RAG,
> semantic memory, Monte Carlo robustness, OpenTelemetry tracing, and a 60-case
> reproducible eval suite — all on a $0/mo serverless stack.

---

## Key Stats

| Metric | Value |
|--------|-------|
| Agent roles (adversarial) | 6 (Planner → Actor → Critic → Validator → Refiner → Judge) |
| Agent roles (standard) | 3 (Analyst → Critic → Synthesizer) |
| Standard mean score (Phase-14) | **82%** (4/5 pass) |
| Adversarial mean score (Phase-14) | **80%** (5/5 accept) |
| Standard mean latency | 32.8 s |
| Adversarial mean latency | 72.3 s |
| Security audit | 40 findings — 35 patched, 5 accepted risk |
| Total eval cases (v1 suite) | **60** (10 done, 50 pending) |
| Est. full suite cost | $0.10–$0.30 |

---

## Architecture

```
backend/
  agents/       # Analyst, Critic, Synthesizer, Planner, Actor, Validator, Refiner, Judge
  rag/          # Ingestion, chunking, embedding, retrieval, CRAG agentic re-ranking
  router/       # Multi-LLM routing (Claude + OpenAI/Groq via OpenRouter)
  evaluation/   # Rubric scorer, benchmark, notebook + Kaggle dataset export
  domains/      # Domain plugins: code_review, finance
  api/          # FastAPI app, WebSocket streams, benchmark/traces dashboard endpoints
  core/         # Bus, lifecycle, PII, auth, cost pricing, OTel telemetry

frontend/
  src/
    pages/
      index.tsx     # Main app (Standard / Adversarial / Experiment modes)
      dashboard.tsx # Benchmark analytics dashboard (recharts)
    components/
      graph/    # 3D planetary knowledge-graph (three.js)
      panels/   # ExperimentView, War Room, Scoreboard
      ui/       # Shared glassmorphic components

benchmarks/
  benchmark_v1.yaml        # 60 Preliminary Eval Test Cases (canonical dataset)
  BENCHMARK_RESULTS.md     # Live results table (10 done / 50 pending)

scripts/
  benchmark_v1.py          # Full 60-case runner
  eval_runs.py             # Phase-14 legacy 5-prompt harness
  benchmark/               # GSM8K loader, grader, stats, report

paper/
  fable_neurips2026.tex    # NeurIPS-format research paper (incl. 60-case appendix)

infra/
  docker/       # Compose + Dockerfiles
  k8s/          # Kubernetes manifests (kind local dev)
  cloudrun/     # GCP Cloud Run deployment
  aws/          # CDK / Terraform stubs

notebooks/      # Kaggle-ready .ipynb (fable_demo.ipynb committed; generated files gitignored)
```

---

## Project Sequence (Phases)

| Phase | Focus |
|-------|-------|
| 1  | Orchestration Core — adversarial agent bus, 6-role pipeline, collaboration loop |
| 2  | Multi-User Platform — Supabase Auth, per-user memory, AES-256-GCM credential encryption |
| 3  | Guardrails — two-layer safety (rules + Llama-Guard classifier), audit log |
| 4  | Privacy & Identity — pseudonymous-first identity, PII redact/reinject, entity map |
| 5  | Deploy ($0/mo) — Presidio→regex+LLM, sentence-transformers→OpenAI, Cloud Run |
| 6  | ELM — Embedded Language Model (Phi-3 ONNX) for dynamic adversarial role declaration |
| 7  | K8s — Kubernetes (kind) local agent scaling; 3 pod groups + coordinator |
| 8  | Security Hardening — 40-finding appsec audit; 35 patches, 5 accepted risk |
| 9  | Document Upload — PDF/DOCX/MD extraction via pypdf + python-docx; glassmorphic UI |
| 10 | ELM Meta-Scorer — confirmed; kNN + ELM hybrid learned router |
| 11 | Agentic RAG (CRAG-lite) — retrieve → grade → rewrite+retry → graded context |
| 12 | Monte Carlo — paraphrase-variant robustness, cosine consensus, divergence pairs |
| 13 | GSM8K Benchmark — 500-problem math benchmark harness, bootstrap CI, McNemar |
| 14 | Latency + Eval — Phase-14 eval harness; 5 std + 5 adv runs; latency + judge fixes |
| 15 | Benchmark v1 + Dashboard — 60-case suite, recharts dashboard, OTel tracing, cost tracking, Kaggle export |
| 16 | Orchestrator Comparison — pluggable asyncio / LangChain / LangGraph backends, self-consistency ensemble, LangSmith tracing, rate-limit dashboard controls |

> **Note:** this README's phase numbers track the README's own changelog and do **not**
> map 1:1 to `RESEARCH_LOG.md` (which numbers the same orchestrator work as Phase 19 and
> the benchmark as Phase 20). The log is the canonical research record.

**Adversarial rounds:** Default `max_rounds = 2`. Judge terminates early (round 1) when score ≥ 0.80. Configurable via `ADVERSARIAL_MAX_ROUNDS`; hard ceiling 10 server-side.

**Acronym:** FABLE = **F**ramework for **A**dversarial **B**enchmarking and **L**ogic **E**valuation.

---

## Benchmark (60 Preliminary Eval Test Cases)

The canonical eval suite lives in [`benchmarks/benchmark_v1.yaml`](benchmarks/benchmark_v1.yaml).

| Section | Cases | Description |
|---------|-------|-------------|
| Standard | 20 | 20 shared prompts → `/run` |
| Adversarial | 20 | Same 20 prompts → `/adversarial-run` (identical wording for fair comparison) |
| Monte Carlo | 10 | Best 2 word-sensitive prompts per category → `/experiment/run` (4 paraphrase variants) |
| Finished (Phase-14) | 10 | 5 std + 5 adv, backfilled from Phase-14 eval run |
| **Total** | **60** | |

**Categories (4 each):** code · reasoning/math · factual/explanation · RAG/CRAG/DocQA · writing/creative

**Monte Carlo selection:** most word-sensitive prompt per category chosen for paraphrase divergence. MC IDs: `MC-C2, MC-C3, MC-R2, MC-R3, MC-F3, MC-F4, MC-D1, MC-D3, MC-W2, MC-W3`.

### Reproduce the benchmark

```bash
# Prerequisites: backend running on :8000, API keys set in .env
python scripts/benchmark_v1.py

# Dry-run (validates yaml, writes placeholder markdown, no API calls):
python scripts/benchmark_v1.py --dry-run
```

Results: `benchmarks/BENCHMARK_RESULTS.md` (markdown) + `data/benchmarks/results/benchmark_v1_<ts>.json` (raw).

**Cost estimate:** $0.10–$0.30 total for all 50 pending runs (see `backend/core/cost.py`).

Full results table: [benchmarks/BENCHMARK_RESULTS.md](benchmarks/BENCHMARK_RESULTS.md)

---

## Quick Start

```bash
# Backend
cd backend && pip install -e ".[dev]"
uvicorn api.main:app --reload

# Frontend
cd frontend && npm install && npm run dev
```

**Dashboard:** [http://localhost:3000/dashboard](http://localhost:3000/dashboard)

---

## Requirements

- Python 3.11+
- Node 20+
- Docker (for Cloud Run deploy)
- OpenAI API key (embeddings — `text-embedding-3-small`, dim=384)
- OpenRouter API key (LLM gateway — all pipelines)
- Supabase project (free tier — Postgres + pgvector + Auth)

---

## Dashboard & Analytics (Phase 15)

Navigate to `/dashboard` for live benchmark monitoring:

- **Mode Analytics** — mean score, mean latency, pass/accept rate per mode (recharts bar)
- **Token Cost** — per-model USD breakdown + cumulative cost (sourced from `backend/core/cost.py`)
- **Trace Waterfall** — OTel span timeline per run (enable with `OTEL_ENABLED=true`)
- **Dataset Feasibility** — 95% CI width, McNemar power note, pending count
- **Export to Kaggle** — one-click push of the 60-case dataset (CSV + JSONL + reproducer notebook) to your Kaggle account

---

## Observability (OTel)

OpenTelemetry tracing is gated by `OTEL_ENABLED` (default: `false` — zero overhead, $0 stack).

```bash
# Enable tracing
export OTEL_ENABLED=true
export OTEL_TRACES_FILE=./data/traces/fable_traces.jsonl  # optional

# Spans instrument: ModelRouter.complete*, agent base, run_monte_carlo, /run, /adversarial-run, /experiment/run
# Attributes per span: llm.model, llm.role, llm.tokens.input, llm.tokens.output, llm.cost.usd
```

Span JSONL is OTLP-ready — point any Jaeger/OTLP collector at the file without restart. The dashboard waterfall reads the same file locally.

---

## Orchestrators — asyncio · LangChain · LangGraph (Phase 16)

The agent pipelines run on a swappable orchestrator, selected by `ORCHESTRATOR`
(default `asyncio`). All three share the **same agent handlers, prompts, and OpenRouter
routing** — only the orchestration layer changes, so the benchmark isolates the
orchestrator for a clean LangChain-vs-LangGraph comparison.

```bash
# Optional framework deps (slim Cloud Run image is unaffected — lazy-imported):
pip install -e "backend[orchestrators]"     # langgraph, langchain-core, langchain, langchain-openai

ORCHESTRATOR=asyncio    # native AgentBus (default / baseline)
ORCHESTRATOR=langgraph  # adversarial loop via LangGraph StateGraph (operator.add fan-in reducer)
ORCHESTRATOR=langchain  # standard pipeline via LangChain LCEL RunnableSequence
```

If the framework deps are absent, the alternate paths fall back to `asyncio` (no crash).

**Self-consistency ensemble:** run N independent debates concurrently and keep the
highest `judge_score` (run-level map-reduce; the per-round reviewer chain stays
sequential because Validator/Refiner depend on Critic):

```bash
ADVERSARIAL_ENSEMBLE_SIZE=5   # default 1 = single debate, original behavior
```

**LangSmith tracing (optional):** LangChain/LangGraph auto-emit traces when enabled.

```bash
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=<your key>
export LANGCHAIN_PROJECT=fable
```

No key → tracing off, hot path untouched (Cloud Run safe).

---

## Rate Limiting (Phase 16)

Per-IP limits (slowapi) + per-identity in-process concurrency, now with response
headers and a project-wide backstop. Live config is exposed at `GET /config/limits` and
shown on the dashboard **Rate Limits** card; a 429 surfaces a retry message in the UI.

```bash
RATE_LIMIT_GLOBAL=100/minute            # project-wide default on every route (per IP)
RATE_LIMIT_RUN=20/minute                # /run, /run/stream
RATE_LIMIT_ADV=5/minute                 # /adversarial-run
MAX_CONCURRENT_PER_IDENTITY=2           # in-flight runs per user (0 = unlimited)
```

Responses on rate-limited routes carry `X-RateLimit-Limit/Remaining/Reset`; exceeding a
limit returns HTTP 429 with `Retry-After`.

---

## Token Cost Tracking (Phase 15)

`backend/core/cost.py` provides per-model pricing + aggregation.

```python
from backend.core.cost import price, aggregate_costs

usd = price("anthropic/claude-sonnet-4-5", {"input": 1200, "output": 340})
# -> $0.00426

agg = aggregate_costs(agent_message_records)
# -> AggregatedCosts(total_usd=..., per_model={...}, per_run=[...])
```

Prices (USD / 1M tokens): Claude Sonnet 4.5 $3/$15, Claude 3.5 Haiku $0.80/$4, GPT-4o-mini $0.15/$0.60, GPT-4o $2.50/$10.

---

## Kaggle Export

From the `/dashboard` → **Export to Kaggle** button (or `POST /export/kaggle`):

- Builds `benchmark_v1.csv` (60 rows: id, mode, category, prompt, score, verdict, latency, tokens, cost)
- Builds `benchmark_v1.jsonl` (raw run records)
- Generates `fable_benchmark_v1.ipynb` (reproducer notebook: loads dataset, calls FABLE, plots leaderboard)
- Pushes all three to your Kaggle account via the Kaggle API

**Credentials (BYOK):** supply your `kaggle.json` `{username, key}` at request time. Never stored or logged. Handled identically to the OpenRouter BYOK key.

---

## Deploy — $0/mo Path

| Component | Provider | Plan | Notes |
|-----------|----------|------|-------|
| Frontend | Vercel | Hobby | Next.js, edge-cached |
| Backend | Google Cloud Run | Free tier | 2M req/mo, 360k vCPU-sec, scales to zero |
| Database + Auth + Vector | Supabase | Free tier | 500MB DB, RLS, pgvector HNSW |
| Embeddings | OpenAI | Pay-as-you-go | text-embedding-3-small @ ~$0.003/mo light usage |
| LLM gateway | OpenRouter | Pay-as-you-go | Per-call billing; adversarial ~$0.030/run |

**Variable cost only.** OTel gated off by default; dashboard reads local files. No added infra cost.

### Backend (Cloud Run) one-time setup

```bash
gcloud auth login
gcloud config set project <YOUR_GCP_PROJECT>
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

# Store secrets (one-time)
echo -n "$OPENROUTER_API_KEY"        | gcloud secrets create fable-openrouter-key       --data-file=-
echo -n "$OPENAI_API_KEY"            | gcloud secrets create fable-openai-key           --data-file=-
echo -n "$SUPABASE_URL"              | gcloud secrets create fable-supabase-url         --data-file=-
echo -n "$SUPABASE_ANON_KEY"         | gcloud secrets create fable-supabase-anon        --data-file=-
echo -n "$SUPABASE_SERVICE_ROLE_KEY" | gcloud secrets create fable-supabase-service     --data-file=-
echo -n "$APP_ENCRYPTION_KEY"        | gcloud secrets create fable-app-encryption       --data-file=-
echo -n "$IDENTITY_COOKIE_SECRET"    | gcloud secrets create fable-identity-cookie      --data-file=-

bash infra/cloudrun/deploy.sh
```

Generate secrets locally:
```bash
python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"  # APP_ENCRYPTION_KEY
python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"  # IDENTITY_COOKIE_SECRET
```

### Frontend (Vercel) one-time setup

```
NEXT_PUBLIC_SUPABASE_URL=https://<ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon key>
NEXT_PUBLIC_API_URL=https://<cloud-run-service>-uc.a.run.app   # REQUIRED — without it the client falls back to localhost:8000 and all API calls fail in prod
BACKEND_URL=https://<cloud-run-service>-uc.a.run.app           # server-side only; drives the Next.js /api/* rewrite proxy
```

> ⚠️ `NEXT_PUBLIC_API_URL` is build-time inlined — set it in Vercel **before** the build runs, then redeploy. `BACKEND_URL` is read server-side at request time by `next.config.js` rewrites.

### Cross-origin notes

- Set `COOKIE_SAMESITE=none` + `COOKIE_SECURE=true` on Cloud Run for Vercel ↔ Cloud Run cross-origin cookies.
- Local dev: `COOKIE_SAMESITE=lax` + `COOKIE_SECURE=false` for `http://localhost`.

### Schema

Apply `infra/supabase/schema.sql` via the Supabase SQL Editor (idempotent, safe to re-run).

---

## Security

See [`SECURITY_AUDIT_STATE.md`](SECURITY_AUDIT_STATE.md) for the full 40-finding audit report.

**Production required variables:**

```bash
CORS_ORIGINS=https://your-vercel-app.vercel.app   # restrict CORS from default localhost
AGENT_INTERNAL_TOKEN=<base64 32 random bytes>      # coordinator→pod auth (K8s mode)
RATE_LIMIT_RUN=20/minute
RATE_LIMIT_ADV=5/minute
RATE_LIMIT_GLOBAL=100/minute                       # project-wide per-IP backstop
```

> ⚠️ Never set `ENV=local` or `COOKIE_SECURE=false` on a deployed host — auth enforcement is bypassed in local mode.

---

## ELM — Dynamic Role Declaration (P6)

Optional local ONNX model (Phi-3-mini, ~1.7GB) that generates system prompts, token budgets, and model assignments for each adversarial role dynamically.

```bash
pip install -e ".[elm]"
python scripts/download_elm_model.py
export ELM_ENABLED=true
export ELM_MODEL_PATH=./data/models/phi-3-mini/cpu_and_mobile/cpu-int4-rtn-block-32
```

Default (`ELM_ENABLED=false`): hardcoded role declarations — zero behaviour change.

---

## Kubernetes — Local Agent Scaling (P7)

```
Coordinator (API + lifecycle) ──HTTP──→ Planning Pod (Planner + Judge)
                               ──HTTP──→ Execution Pod (Actor + Refiner)
                               ──HTTP──→ Review Pod (Critic + Validator)
```

```bash
./infra/k8s/setup.sh    # one-command setup
curl http://localhost:8000/health
./infra/k8s/teardown.sh
```

Production stays on Cloud Run (`K8S_MODE=false`).

---

## Research Paper

[`paper/fable_neurips2026.tex`](paper/fable_neurips2026.tex) — NeurIPS 2026 format.

Includes: system architecture, Standard + Adversarial + Monte Carlo evaluation tables, root-cause findings (adversarial timeout + judge verdict salvage), token cost analysis, and an appendix with all 60 preliminary eval test cases.
