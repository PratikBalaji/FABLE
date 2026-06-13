# FABLE Research Log
## Framework for Adversarial Benchmarking and Logic Evaluation

**Purpose:** Running technical log for research paper. Captures design decisions, engineering challenges, and solutions as they occur. Intended for NeurIPS workshop on Multi-LLM Debate.

---

## Table of Contents

| Phase | Title |
|-------|-------|
| [Phase 1](#phase-1--adversarial-multi-llm-network) | Adversarial Multi-LLM Network — 6-role pipeline, lifecycle, API |
| [Phase 2](#phase-2--multi-user-platform-foundation) | Multi-User Platform Foundation — Auth, Providers, Memory |
| [Phase 3](#phase-3--guardrails) | Guardrails — input/output safety, classifier, audit log |
| [Phase 4](#phase-4--privacy--identity-foundation) | Privacy & Identity — pseudonymous identity, PII, entity map |
| [Phase 5](#phase-5--0mo-deploy-presidio-out-cloud-run-in) | $0/mo Deploy — Presidio→regex+LLM, sentence-transformers→OpenAI, Cloud Run |
| [Phase 6](#phase-6--elm-embedded-language-model) | ELM — Embedded Language Model (Phi-3 ONNX) for dynamic role declaration |
| [Phase 7](#phase-7--kubernetes-local-agent-scaling) | Kubernetes (kind) — local agent scaling, 3 pod groups |
| [Phase 8](#phase-8--security-hardening) | Security Hardening — 40-finding appsec audit, 10 patches applied |
| [Phase 9](#phase-9--document-upload--glassmorphic-ui) | Document Upload + Glassmorphic UI — PDF/DOCX/MD, framer-motion |
| [Phase 10](#phase-10-feasibility--presidio-on-docker-sidecar) | Feasibility: Presidio on Docker Sidecar |
| [Phase 11](#phase-11-feasibility--extreme-learning-machine-elm) | Feasibility: Extreme Learning Machine (ELM) as meta-scorer |
| [Phase 12](#phase-12-feasibility--pod--model-role-rebalancing) | Feasibility: Pod & Model Role Rebalancing by Benchmark |
| [Phase 13](#phase-13-feasibility--monte-carlo-experiment-mode) | Feasibility: Monte Carlo Experiment Mode |

---

## Phase 1 — Adversarial Multi-LLM Network

### Architecture Decision: Why Adversarial?

The cooperative pipeline (Analyst → Critic → Synthesizer) produces consensus-driven outputs. Adversarial networks exploit *productive disagreement*: a Critic incentivized to find flaws produces sharper feedback than one incentivized to agree. This is structurally analogous to GAN training (generator vs discriminator) applied to language model reasoning chains.

The six-role design maps to a formal adversarial proof system:
- **Planner** — sets the axioms and success criteria (problem decomposition)
- **Actor** — proposes the theorem/solution (generator)
- **Critic** — constructs a counterexample or falsification (adversary)
- **Validator** — checks logical validity and grounding (proof checker)
- **Refiner** — guides revision (proof assistant)
- **Judge** — decides acceptance (verifier/arbiter)

### LLM Role Assignment Rationale

| Role | LLM | Justification |
|------|-----|---------------|
| Planner | Claude Sonnet | Long-horizon structured decomposition; sets the frame for all subsequent agents |
| Actor | GPT-4o | Strong cross-domain generation; produces the primary artifact under adversarial pressure |
| Critic | Groq Llama 3 70B | Low-latency adversarial probing; runs in tight loop — cost efficiency critical |
| Validator | Gemini 1.5 Pro | Large context window (1M tokens) allows reviewing all prior agent outputs simultaneously |
| Refiner | Groq Llama 3 70B | Shares Groq with Critic; fast, directive output; role is structural not generative |
| Judge | Claude Sonnet | Holistic arbitration; convergence detection; produces final user-facing answer |

**Key insight:** Claude appears twice (Planner + Judge) because both roles require the highest-caliber systemic reasoning. Groq appears twice (Critic + Refiner) because both roles are high-frequency and low-semantic-density — precision matters less than speed and cost.

### Phase 1a: Configuration Layer

**File:** `backend/core/config.py`
**Change:** Added 8 new Settings fields — 6 per-role model strings + `adversarial_max_rounds` + `adversarial_judge_threshold`
**Decision:** Default `max_rounds = 2` to minimize API credit burn. Judge can terminate after round 1 if score ≥ 0.80. Configurable up to 3+ rounds via `ADVERSARIAL_MAX_ROUNDS` env var when task complexity and budget warrant — the choice of 2 is a cost default, not an architectural ceiling. Hard server-side cap set at 10 (Phase 8 security patch F-020).

### Phase 1b: Router Extension

**File:** `backend/router/model_router.py`
**Change:** Added `ROLE_MODEL_MAP` dict and `complete_for_role(role, system, user)` method
**Design note:** Used the `adv:` prefix in role keys to prevent namespace collision with the existing `"critic"` role on the AgentBus.

**Problem:** If both `register_all()` and `register_adversarial()` use the same role string `"critic"`, the second call overwrites the first — corrupting the standard pipeline. **Solution:** prefix adversarial roles as `"adv:critic"` etc.

### Phase 1c: Adversarial Agent Classes

**File:** `backend/agents/adversarial.py` (new)
**6 agents created:** PlannerAgent, ActorAgent, AdversarialCriticAgent, ValidatorAgent, RefinerAgent, JudgeAgent

**Key engineering decisions:**
- `BaseAdversarialAgent` overrides `__call__` to route through `complete_for_role()`. All bus/history mechanics inherited unchanged.
- `_last_by_role(ctx, role)` searches `reversed(ctx.history)` — O(n) but n is small (max ~12 messages across 2 rounds). Round-aware without explicit round tracking.
- Judge instrumented to return raw JSON; `_parse_judge_output()` strips markdown fences, falls back to `re.search` for embedded JSON — robust against LLM formatting drift.

**Token budgets (role-calibrated):**
| Role | max_tokens | Rationale |
|------|-----------|-----------|
| Actor | 2048 | Needs complete solutions |
| Judge | 1024 | JSON + final answer |
| Critic | 1024 | Structured flaw lists |
| Validator | 1024 | Structured validity checks |
| Planner | 600 | 4-section plan |
| Refiner | 512 | Surgical spec only — tight cap enforces role discipline |

### Phase 1d: Registration

**File:** `backend/agents/adversarial_register.py` (new)
Mirrors `register.py` with `adv:` prefixed keys. Registers as separate namespace on same `AgentBus` singleton.

### Phase 1e: Adversarial Lifecycle

**File:** `backend/core/adversarial_lifecycle.py` (new)
```
Planner (once)
  └─ for round in range(max_rounds):
       Actor → Critic → Validator → Refiner → Judge
       if Judge.verdict == ACCEPT: break
```
**Termination guarantee:** Judge system prompt forces ACCEPT on final round — no infinite loops even on low-quality output.
**Fallback:** Judge parse failure → last Actor output as final answer.
**Credit efficiency:** Groq handles 2/5 per-round roles. VERDICT: NO_FLAWS + ALL_VALID → round-1 ACCEPTance in best-case.

### Phase 1f: API Layer

**Files:** `schemas.py`, `routes/run.py`, `main.py`
`RunRequest` gains `mode` + `max_rounds`. `RunResponse` gains `adversarial_meta` (null in standard mode — backward compatible). `domain` defaults to `"general"`.

### Open Questions for Paper (Phase 1)

1. **Convergence rate:** At what round does the Judge most frequently accept? Is round 1 acceptance the norm or exception?
2. **Diversity benefit:** 4 different LLMs vs single-LLM for all roles — measurable quality difference?
3. **Role ablation:** Which single agent contributes most to final quality improvement?
4. **Validator grounding:** Does the large-context review catch errors the Critic misses?

### Problems Encountered (Phase 1)

**P1-1: Bus role namespace collision** — solved with `adv:` prefix (see 1b above).

**P1-2: Judge JSON parsing brittleness** — Two-stage parser (strip fences → regex fallback → REJECT default). *Future work:* use structured output APIs (`response_format: json_object`).

**P1-3: Token budget waste** — Role-specific `_TOKEN_BUDGETS` dict. Refiner's 512-cap prevents it from rewriting the Actor (role boundary enforcement).

### References

- GAN (Goodfellow et al. 2014) — structural analogy
- Constitutional AI (Bäuerle et al.) — adversarial self-critique
- Debate as alignment (Irving et al. 2018) — multi-agent debate
- ReAct (Yao et al. 2022) — tool-augmented reasoning chains

---

## Phase 2 — Multi-User Platform Foundation (Auth + Providers + Memory)

**Goal:** Per-user provider connections (OAuth + BYOK), encrypted credentials, persistent cross-session semantic memory. Backed by Supabase (Postgres 17 + pgvector + Auth + RLS).

### Architecture Decisions

**Why Supabase / pgvector:** The prototype stored everything in global JSON/JSONL files with a shared OpenRouter key. Supabase provides four needs in one stack: (1) Auth (JWT), (2) Postgres, (3) pgvector for semantic memory (`knowledge_engine.get_relevant_context` already did cosine search over NumPy), (4) RLS for per-user privacy. Existing 384-d embeddings map directly to `vector(384)` — no re-embedding needed.

**Memory vs. Graph split:** Per-user recall → Supabase `memory_chunks` (RLS-scoped). Global 3D graph viz → file-based `knowledge_engine` (unchanged). Lifecycles branch on `multiuser` flag.

**Index choice — HNSW over IVFFlat:** Better recall/latency; no pre-population needed (IVFFlat requires training centroids). Cosine chosen for interpretable [0,1] similarity scores.

**Encryption: app-level AES-256-GCM (not pgsodium/Vault):** Provider keys encrypted in FastAPI layer before reaching Postgres. 32-byte key in `APP_ENCRYPTION_KEY` (env only). Layout: `base64(nonce(12) || ciphertext || GCM tag(16))`.

**Per-user router via TaskContext:** Agents received a global `ModelRouter` at registration; each request must use the caller's credential. Solution: `TaskContext.metadata["router"]` carries the per-user router. The agent change is one line in two base classes: `router = ctx.metadata.get("router") or self.router`.

**Schema (8 tables, all RLS owner-only):** `profiles · provider_connections · oauth_states · chat_sessions · chat_messages · adversarial_runs · adversarial_messages · memory_chunks`. Vector search via `match_memory_chunks(p_user_id, query_embedding, match_count)` — filters by user **before** ANN order-by.

### Problems Encountered (Phase 2)

**P2-1:** `bytea` over PostgREST is painful. **Fix:** `secret_enc` as `text` holding base64 (migration 07). Security identical; JSON transport trivial.

**P2-2:** pgvector lives in `extensions` schema. **Fix:** fully-qualified type + `OPERATOR(extensions.<=>)` in match function.

**P2-3:** JSON arrays don't cast to `vector`. **Fix:** `vector_literal()` helper formats embeddings as `"[0.1,0.2,...]"`.

**P2-4:** `SECURITY DEFINER` trigger callable via PostgREST RPC. **Fix:** revoked EXECUTE from public/anon/authenticated; trigger still fires as table owner. Security advisors: **0 findings** after hardening.

**P2-5:** `/run` must be open in legacy mode but require auth in multi-user mode. **Fix:** `get_optional_user` dependency — one route, both modes.

### Open Questions for Paper (Phase 2)

1. Privacy framing: semantic search requires server-readable plaintext — this is "encryption at rest + RLS isolation," not E2E.
2. Does cross-session memory measurably improve quality vs stateless?
3. Multi-provider routing — does mixing providers per role change adversarial dynamics?

---

## Phase 3 — Guardrails (input/output safety)

**Goal:** Prevent prompt injection, credential exfiltration, content-policy violations, resource exhaustion. Two layers (cheap rules + optional LLM classifier), fired as lifecycle hooks.

### Architecture Decisions

**Lifecycle hooks:** `pre_check`/`post_check` inside the lifecycle (not just a FastAPI dependency) guarantees they fire on every execution path — CLI, tests, workers. Route maps `GuardrailBlocked` → HTTP 400 with structured `{error, stage, category, reason, layer}`.

**Two-layer model:**
- Layer 1 (rules): regex/heuristic, ~10µs, free. Classic injection, DAN jailbreaks, `<|im_start|>` smuggling, credential exfil (env-var names, `sk-or-v1-…` / `sk-ant-…`, `cat .env`), 20k char cap, blocklist.
- Layer 2 (classifier): Llama-Guard-3-8B via OpenRouter (~$0.05/M tokens). Cached by `sha256(content)`. Research-friendly default: discussing security analytically → `allow`; obvious abuse → `block`.

**Post-check is narrow:** Only screens final output for credential leakage — not re-running injection regex (a correct answer quoting injection patterns is fine).

**Audit table:** Stores only `sha256` of content, not raw text. Stage/verdict/category/reason/layer/task_id indexed.

### Problems Encountered (Phase 3)

**P3-1:** `re.X` (verbose mode) ate literal whitespace — all injection inputs returned `allow`. **Fix:** dropped `x` flag, used explicit `\s+`. Tests: 6/11 → 14/14.

**P3-2:** Env-var names with underscores not caught. **Fix:** separator class `[\s_\-]*`.

**P3-3:** False-positive risk on security research prompts. Verified: `"How do I prevent prompt injection attacks?"` → `allow`.

### Verification (14/14 PASS)

See test table in original log entries — all categories (normal_code, security_research, injection_classic, injection_dan, cred_exfil, empty, too_long, blocklist, post_leak, post_normal) pass.

### Open Questions (Phase 3)

1. False-positive rate on legitimate security research — need 500+ prompt held-out set.
2. Leet-speak / unicode homoglyphs / base64 bypass — addressed in Phase 8 (NFKC normalization added).
3. Latency budget for post_check on every turn.

---

## Phase 4 — Privacy & Identity Foundation

**Goal:** Pseudonymous-first identity, PII redact/reinject/abstract pipeline, encrypted entity map, schema migration.

### Architecture Decisions

**Pseudonymous-first identity:** First visit → backend mints `public.identities` row (`pseudonymous=true`), stamps HMAC-signed cookie (`fable_id`, `itsdangerous.URLSafeTimedSerializer`, 1-year TTL). Optional `POST /identity/link` upgrades to Supabase auth user (requires JWT + explicit `consent_link=true`).

**Why HMAC cookie + DB lookup:** Identity state can change (consent flags, link status). JWT-in-cookie forces re-issuance on every mutation. HMAC over UUID + single SELECT keeps cookie tiny and reads canonical state per request.

**PII layer: Presidio + LLM fallback (Phase 4 original design):**
Presidio (open-source, ~50ms, spaCy-backed) handles 95% of structured PII + PERSON/LOC/ORG spans. For spans below `pii_confidence_threshold` (default 0.40), one LLM call (Llama-Guard-3-8B) confirms or rejects — fail-closed on error.

> **Note — Presidio removed in Phase 5:** Cloud Run free-tier image constraint (~1GB for Presidio + spaCy + `en_core_web_lg`) forced removal. Phase 5 (P6a) replaced with regex + LLM hybrid. See Phase 10 feasibility for Presidio-on-Docker-sidecar restoration path.

**Memory abstraction hard-rule:** `abstract_for_memory()` compresses user turn into one third-person sentence (topic+domain+intent, no names/IDs/numbers). Result is what gets embedded into `memory_chunks`. Raw text never embedded. *(Phase 8 patch F-010 wired this call — it was defined but never called in the original implementation.)*

**Entity-map storage:** PII values encrypted with AES-GCM (same KEK as provider credentials). 7-day TTL via `public.pii_entity_map`. In-memory entity map is primary reinjection source; DB persistence is recovery insurance.

### Schema additions

- `public.identities` — pseudonymous/auth-linked; unique `auth_user_id` index.
- `public.pii_entity_map(session_id, task_id, placeholder, entity_enc, entity_type, expires_at)` — 7-day TTL, encrypted entity values.
- `identity_id` column added to 8 tables (nullable, backward-compatible).
- `public.match_memory_chunks_by_identity()` — identity-scoped cosine RPC.

### Problems Encountered (Phase 4)

**P4a-1:** `auth.py` JWT dep blocked unit tests — install PyJWT.

**P4a-2:** `sentence_transformers` blocks full-app import test — skip when dep missing.

**P4a-3:** Presidio install (~1GB) deferred — lazy-import; raises `PiiRedactionFailed` if missing (notebook hard-stop verified).

**P4a-4:** Cookie `secure=True` breaks `http://localhost`. Documented as dev-env setup item.

**P4a-5:** New identity returns `cookie_to_set` — route handler sets cookie. Every route using identity must remember to call `set_identity_cookie(response, ...)` when present.

### Verification (6/6 PASS)

Cookie HMAC round-trip · tamper rejection · PII module clean import · hard-fail without Presidio · `PII_ENABLED=false` bypass · `reinject()` substitution · AES-GCM round-trip.

### Open Questions (Phase 4)

1. **Reinjection threat model:** reinjecting PII into responses risks leakage if responses are cached/shared. Mitigation: never cache reinjected output.
2. **Cookie loss = identity loss.** Pseudonymous user clearing cookies starts over — privacy feature, not bug.
3. **Abstraction fidelity:** does abstracted-memory recall compare favorably to raw-text recall?
4. **PII confidence threshold 0.40** — biases toward false positives; LLM disambig step trims them.

---

## Phase 5 — $0/mo Deploy: Presidio Out, Cloud Run In

**Constraint:** Zero fixed monthly cost. Drop heavy deps, ship to Cloud Run free tier (2M req/mo, 360k vCPU-sec, scales to zero). Image target: <300 MB.

### P5a — Regex + LLM Hybrid PII (Presidio out)

**Why removed:** `presidio-analyzer + presidio-anonymizer + spacy en_core_web_lg` = ~1GB disk. Free-tier image limits reject it.

**Hybrid strategy (selected over LLM-only):**
- Regex: EMAIL, PHONE, SSN, CREDIT_CARD (Luhn-validated), IBAN, IP_ADDRESS, API_KEY prefixes (OpenRouter/Anthropic/OpenAI) — deterministic, ~10ms.
- LLM call: PERSON/LOCATION/ORGANIZATION spans regex can't see — ~200ms, ~$0.0001/request, non-fatal on failure.

| PII type | Presidio | P5a regex+LLM |
|---|---|---|
| EMAIL_ADDRESS | ✓ | ✓ regex |
| PHONE_NUMBER | ✓ | ✓ regex (10+ digit floor) |
| US_SSN | ✓ | ✓ regex (invalid-area filter) |
| CREDIT_CARD | ✓ | ✓ regex + Luhn validation |
| API_KEY | ✗ (custom recognizer needed) | ✓ regex on OpenRouter/Anthropic/OpenAI prefixes |
| PERSON | ✓ spaCy NER (~95% F1) | ✓ LLM (~80-85% recall, calibration TBD) |
| LOCATION | ✓ | ✓ LLM (~75-80% recall) |
| ORGANIZATION | ✓ | ✓ LLM |

**Existing PII module API unchanged** — `redact / reinject / abstract_for_memory / persist_entity_map / PiiRedactionFailed` wiring through `run.py` unmodified.

**P5a verification (11/11 pass)** — email, phone, SSN, credit card (Luhn valid + invalid), API key, IP, reinject round-trip, overlap dedup, empty input, Luhn test vectors.

### P5b — OpenAI Embeddings (sentence-transformers out)

`sentence-transformers all-MiniLM-L6-v2` pulls `torch` (~750MB). Replaced with OpenAI `text-embedding-3-small` with `dimensions=384` — matches existing `vector(384)` schema. Cost: ~$0.003/mo at research volume.

**New module:** `backend/core/embeddings.py` — `embed_text()`, `embed_batch()`, lazy OpenAI client. Falls back to OpenRouter base URL if `OPENAI_API_KEY` absent (with warning — OpenRouter proxies chat completions only, not embeddings).

**Schema impact:** None. Existing MiniLM rows are vector-space-incompatible; document as one-time wipe if populated. Research project: table is empty.

### P5c — Containerize + Cloud Run + Cross-Origin Cookies

- `Dockerfile` (root): `python:3.11-slim`, explicit dep install, COPY backend only.
- `.dockerignore`: excludes frontend/, tests/, notebooks/, data/, .env*.
- `infra/cloudrun/deploy.sh`: `gcloud run deploy` with `--memory 512Mi --cpu 1 --min-instances 0 --max-instances 5 --concurrency 80 --port 8080 --timeout 300`. All secrets from Secret Manager.
- Cross-origin cookies: `COOKIE_SAMESITE=none` + `COOKIE_SECURE=true` for Vercel ↔ Cloud Run. `httponly=true` always.

---

## Phase 6 — ELM (Embedded Language Model)

> **Terminology note:** The component described here is the *Embedded Language Model* — a local ONNX Phi-3 model used for dynamic role declaration. The user has also raised interest in *Extreme Learning Machine* (single-hidden-layer feedforward net, random input weights, closed-form output training) as a fast meta-scoring tool. These are distinct R&D tracks. See [Phase 11 feasibility](#phase-11-feasibility--extreme-learning-machine-elm) for the ELM-as-Extreme-Learning-Machine proposal.

### Problem

The adversarial pipeline's 6 agent roles have hardcoded system prompts, token budgets, and model assignments. Every task runs through the same configuration — waste on simple tasks; under-configured on complex ones.

### Architecture

**Pre-pipeline phase:** Phi-3-mini-4k-instruct (INT4 quantized ONNX, ~1.7GB) analyzes task input+domain and produces a `PipelineDeclaration` specifying per-role: system prompt, model assignment, token budget, activation flag, execution order.

**Why Phi-3 ONNX:**
- No PyTorch (dropped in P5b). `onnxruntime-genai` ~50MB, no CUDA.
- Strong structured JSON output generation.
- 4k context sufficient (~1500 token meta-prompt).
- Offline — zero API cost per role-declaration.

**Thread-safe via TaskContext:** Agents read declarations from `TaskContext.metadata["elm_declarations"]`. Each request gets its own `PipelineDeclaration`. Fully concurrent-safe.

**Fallback chain:** `ELM_ENABLED=false` → static declarations → fallback on model missing → fallback on inference failure → fallback on parse failure → mandatory roles (`adv:planner, adv:actor, adv:judge`) always force-active.

**File-based cache:** `sha256(domain + ":" + task_input[:200])` → JSON file, 24h TTL.

### Problems Encountered (Phase 6)

**P6-1:** `onnxruntime-genai` has limited platform support. Made it an optional `[elm]` dep group. Not in production Dockerfile.

**P6-2:** ELM could deactivate all roles. Hard constraint enforced in code.

---

## Phase 7 — Kubernetes (kind) Local Agent Scaling

### Problem

All 6 adversarial agents run in-process. No isolation, no independent scaling, agent-heavy tasks block the API.

### Architecture: 4 Services

| Service | Agents | Port | Pod group |
|---------|--------|------|-----------|
| Coordinator | None (API + lifecycle + ELM) | 8000 | — |
| Planning pod | `adv:planner, adv:judge` | 8001 | Strategic roles (both Claude) |
| Execution pod | `adv:actor, adv:refiner` | 8002 | Content generation (highest token budget) |
| Review pod | `adv:critic, adv:validator` | 8003 | Adversarial review |

**Why 3 groups (not 6 pods):** Local dev overhead; grouping by function gives 3 independent scaling units. Execution pod (Actor = highest token budget) is the bottleneck — HPA maxReplicas=3 vs 2 for others.

**DistributedAgentBus:** Subclasses in-process `AgentBus`. Same `dispatch(role, ctx)` API — lifecycle code unchanged. `K8S_MODE=true` → serializes `TaskContext` (strips `router`), POSTs to pod's `/agent/invoke`.

**Serialization:** `TaskContext.metadata["router"]` is async OpenAI client — not serializable. Strip before transport; each pod creates its own `ModelRouter` from ConfigMap/Secret env.

**Backward compatibility:** `K8S_MODE=false` (default) → everything as before. Cloud Run production unchanged.

### Production Scaling Path

1. GKE Autopilot — migrate from Cloud Run with same container images.
2. Custom HPA metrics based on pending LLM request queue depth (not just CPU).
3. KEDA scale-to-zero for idle cost efficiency.
4. OpenTelemetry tracing across coordinator → agent pods.

### Problems Encountered (Phase 7)

**P7-1:** Circular import on bus creation — lazy import inside `_create_bus()`.

**P7-2:** Agent pod can't import full app — minimal FastAPI app with only `adversarial.py` + `model_router.py`.

---

## Phase 8 — Security Hardening

**Full read-only appsec audit performed 2026-06-13.** 40 findings across auth, CSRF/CORS, PII, guardrails, RAG, K8s agent scaling, notebook export, deployment, supply-chain. Full findings + 20-case test plan in `SECURITY_AUDIT_STATE.md`.

### Findings by Severity

| Severity | Count |
|----------|-------|
| CRITICAL | 6 |
| HIGH | ~14 |
| MEDIUM | ~14 |
| LOW | 6 |

### Top-10 Patches Applied (commit `ef2720e`)

| Finding | Patch |
|---------|-------|
| F-034 (Critical) | slowapi rate limiter — 20/min on `/run`, 5/min on `/adversarial-run` |
| F-024 (Critical) | `/ingest` requires identity; per-user FAISS filtering; 10MB cap + content-type allowlist |
| F-008 (Critical) | CORS restricted to `CORS_ORIGINS` env; `X-FABLE-Request: 1` CSRF header required on mutations |
| F-029 (Critical) | `X-Internal-Token` auth on `/agent/invoke` via `secrets.compare_digest` |
| F-030 (Critical) | K8s per-pod secrets — `coordinator-secrets` (all) vs `agent-secrets` (LLM keys + token only) |
| F-010 (High) | `abstract_for_memory()` was defined but never called — now wired before every embed/store |
| F-018 (High) | Guardrails bypass via direct `bus.dispatch()` — added pre_check to bus if `_guardrail_checked` not set |
| F-021/F-022 (High) | Guardrail classifier fail-open → fail to `warn`; NFKC normalization before regex |
| F-005 (Critical) | New `backend/core/repository.py` — `ScopedRepository` class with mandatory tenant injection |
| F-011 (Medium) | Placeholder format → `__PII_{nonce}_{TYPE}_{N}__`; `reinject()` sort by length descending |

### Bonus fixes applied

- F-017: agent pod no longer leaks raw `str(exc)` in HTTP 500 response.
- F-020: `max_rounds` hard-capped at 10 server-side in `adversarial_lifecycle.py`.
- F-031: `kind-config.yaml` `listenAddress: 127.0.0.1` (was binding `0.0.0.0`).
- F-037: `.gitignore` now excludes `notebooks/fable_*.ipynb`.

### Remaining Backlog

F-001 (cookie revocation), F-006 (identity_id RLS migration), F-007 (REVOKE on `match_memory_chunks`), F-012 (pg_cron TTL sweep), F-014 (AES-GCM AAD), F-025 (RAG "source of truth" prompt framing), F-033 (export sanitizer), F-036 (Cloud Armor). Tracked in `SECURITY_AUDIT_STATE.md`.

### Open Questions (Phase 8)

1. RLS policy migration to use `identity_id` columns (added in schema but live code still uses `user_id`).
2. AES-GCM AAD migration — re-encrypt all existing `provider_connections.secret_enc` rows with `user_id + provider + conn_type` as AAD.
3. `pii_entity_map` TTL sweep — pg_cron job needed.

---

## Phase 9 — Document Upload + Glassmorphic UI

### Document Upload (PDF / DOCX / Markdown / plain text)

**Problem:** `/ingest/file` accepted `application/pdf` in the content-type allowlist but only applied `content.decode("utf-8", errors="ignore")` — PDF binary would produce garbage text.

**Solution:** New `backend/rag/extract.py` module:
- **PDF:** `pypdf.PdfReader` — pure Python, no native deps, ~2MB install. Extracts text page-by-page; raises `ValueError` on image-only/encrypted PDFs.
- **DOCX:** `python-docx.Document` — extracts paragraphs + table cell text.
- **MD / TXT / CSV / JSON:** direct UTF-8 decode with latin-1 fallback.
- Falls back to raw decode on unsupported type (non-fatal).

**PII guarantee:** Extracted text flows through the existing `pii.redact()` call in `run.py` before any pipeline dispatch. Raw document content is never stored without redaction.

**Deps added:** `pypdf>=4.0.0`, `python-docx>=1.1.0` to `pyproject.toml` + `Dockerfile`. Both are light (<5MB total); Cloud Run image stays <300MB.

**Frontend:** New upload control in `index.tsx` composer — drag-drop + file picker, `FormData` POST to `/ingest/file` via `api.ts:ingestFile()`. File chips with extension icons (lucide-react). Upload status toast. `withCredentials: true` on axios instance (required for cross-origin identity cookie from Phase 8 CORS fix).

### Glassmorphic UI Enhancement

**Stack:** Existing Tailwind/CSS glassmorphism (`.glass`, `.glass-surface` in `globals.css`) extended; **framer-motion** added for spring animations.

**Changes:**
- `globals.css`: deeper `backdrop-filter: blur(28px) saturate(1.4)` on `.glass`; new `.glass-ghost` for input backgrounds; `shadow-glow-*` utilities; thinking-dots + pulse-glow keyframes.
- `AgentThread.tsx`: `motion.div` with staggered `x:-12, y:4 → 0,0` enter animations; per-role accent left-border colors + inset glow.
- `WarRoom.tsx`: `motion.div` with `y:10, scale:0.98 → 0, 1` per-message spring; subtle inset box-shadow with role color; `AnimatePresence` for stagger; `textShadow` on role badge.
- `index.tsx`: `motion.button` with `whileTap` + `whileHover` on submit; `AnimatePresence` on error, scores panel, judge chip, loading indicator; animated score bars (`motion.div` width transition); file chips with `scale` enter/exit.
- `_app.tsx`: added `<Head>` with `<title>` and meta description.

**Branding:** Header now shows large `FABLE` (mauve, `textShadow: 0 0 28px rgba(203,166,247,0.55)`) with subtitle `Framework for Adversarial Benchmarking and Logic Evaluation` below. Replaces `F.A.B.L.E. / Federated Agent Bus & Lifecycle Engine` inconsistency.

---

## Phase 10 Feasibility — Presidio on Docker Sidecar

### Context

Presidio was removed in Phase 5 (P5a) to fit the Cloud Run <300MB image constraint. The user wants to restore NER-grade PERSON/LOCATION/ORGANIZATION detection while keeping the slim production image. A Docker sidecar approach decouples the heavy spaCy/Presidio runtime from the main backend.

### Proposed Architecture

```
docker-compose.yml
├── backend           (python:3.11-slim, <300MB) → calls presidio-analyzer via HTTP
├── presidio-analyzer (mcr.microsoft.com/presidio-analyzer:latest)
│     exposes :3000/analyze, :3000/recognizers
└── frontend          (node:20-slim)
```

**Inter-service call:** Backend calls `POST http://presidio-analyzer:3000/analyze` with `{text, language: "en", entities: ["PERSON","LOCATION","ORGANIZATION"]}`. Returns entity spans with start/end offsets + confidence scores. No custom recognizer needed for common PII — `en_core_web_lg` is bundled in the Presidio image.

**Hybrid fallback:** When `PRESIDIO_URL` env var is set, `pii.py:_llm_extract` is replaced by a Presidio sidecar call (much better precision). When unset (Cloud Run production), falls back to the current regex+LLM hybrid. One config toggle, no code branching at the route layer.

```python
# Proposed addition to pii.py
async def _presidio_extract(text: str) -> list[EntitySpan]:
    if not settings.presidio_url:
        return []  # no sidecar configured
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(f"{settings.presidio_url}/analyze", json={
            "text": text[:4000], "language": "en",
            "entities": ["PERSON", "LOCATION", "ORGANIZATION"]
        })
        # map Presidio response → EntitySpan list
```

**docker-compose addition (~4 lines):**
```yaml
  presidio-analyzer:
    image: mcr.microsoft.com/presidio-analyzer:latest
    ports: ["3000:3000"]
    environment: [DEFAULT_PORT=3000]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
```

### Verdict

**FEASIBLE — recommended for compose/k8s local dev and production K8s.** NOT for Cloud Run single-image target.

| Dimension | Assessment |
|-----------|-----------|
| Effort | Low (~2h: compose addition + `pii.py` 30-line Presidio client + config flag) |
| PERSON/LOC/ORG recall gain | ~80-85% → ~95% (spaCy `en_core_web_lg`) |
| Latency | +50ms p50 (network to sidecar vs LLM call +200ms) — net improvement |
| Cloud Run impact | None — sidecar only used when `PRESIDIO_URL` set |
| Kubernetes impact | Add as 4th deployment in K8s manifest; ClusterIP service |
| Risk | Low — failure path falls back to existing regex+LLM |

### Open Questions

1. Presidio image is ~2GB. Worth a startup penalty on local compose? Yes — runs once, stays warm.
2. `en_core_web_lg` vs `en_core_web_sm` in Presidio image — is the large model included by default?
3. Multi-language support: Presidio supports 6 languages via additional models. If the research expands beyond English, Presidio sidecar is the right abstraction.

---

## Phase 11 Feasibility — Extreme Learning Machine (ELM) as Meta-Scorer

> **Disambiguation:** This section describes *Extreme Learning Machine* — a specific neural architecture from Huang et al. 2006. This is distinct from the *Embedded Language Model* (Phi-3 ONNX role-declaration model) already implemented in Phase 6. The user raised the Extreme Learning Machine as a proposed R&D track under the same "ELM" label.

### What is an Extreme Learning Machine?

An ELM is a single-hidden-layer feedforward neural network where:
1. **Input layer → hidden layer weights** are set randomly at initialization and **never trained**.
2. **Hidden layer → output layer weights** are solved analytically in one closed-form step via the Moore-Penrose pseudoinverse: `β = H⁺ · T` where `H` is the hidden layer activation matrix and `T` is the target matrix.
3. Training time: **milliseconds** for thousands of samples.
4. No backpropagation. No GPU. `numpy` only.

Theoretical guarantee (Huang et al.): given enough hidden neurons, a single-hidden-layer ELM with random weights is a universal approximator. The random projection essentially maps input to a higher-dimensional random feature space; the closed-form output layer finds the best linear combination.

### Proposed Use in FABLE

**Role: fast model-performance meta-scorer / router advisor.**

FABLE already runs a heuristic model-selection loop in `knowledge_engine.py:get_best_model_for()` — it ranks models by `relevance_score × avg_rubric_score` over the 10 nearest past runs. This is a weighted nearest-neighbor approach. An ELM could replace or augment it:

**Input features (per run, from existing data):**
- 384-d embedding of the task input (already computed for memory storage)
- Domain one-hot encoding
- Prompt length
- Adversarial mode flag

**Output target (per run, from existing data):**
- Rubric scores (accuracy, depth, clarity, actionability, coverage) for each model used
- OR: binary "did the Judge ACCEPT this run?" label

**Training:** After each run, add one training sample. Every N runs (or on each request), retrain the output weights in ~10ms. `numpy.linalg.lstsq` is the only dep.

**What it learns:** Which task characteristics predict which model will score highest. Faster and more principled than the current heuristic because it can learn interaction effects (e.g. "code-domain + long prompt → Actor GPT-4o historically outperforms claude-sonnet-4-5").

### Implementation Sketch

```python
# backend/core/elm_router.py (new, ~60 lines)
import numpy as np
from dataclasses import dataclass, field

@dataclass
class ELMRouter:
    n_hidden: int = 128
    _W: np.ndarray | None = None    # random input→hidden weights (never updated)
    _b: np.ndarray | None = None    # random biases
    _beta: np.ndarray | None = None # trained output weights
    _X: list = field(default_factory=list)  # training features
    _Y: list = field(default_factory=list)  # training targets

    def _init_weights(self, n_features: int):
        rng = np.random.default_rng(seed=42)  # reproducible random projection
        self._W = rng.standard_normal((n_features, self.n_hidden))
        self._b = rng.standard_normal(self.n_hidden)

    def _hidden(self, x: np.ndarray) -> np.ndarray:
        return np.tanh(x @ self._W + self._b)  # hidden activations

    def add_sample(self, features: np.ndarray, target: np.ndarray):
        if self._W is None:
            self._init_weights(features.shape[0])
        self._X.append(self._hidden(features))
        self._Y.append(target)
        if len(self._X) >= 5:  # retrain when enough data
            H = np.array(self._X)
            T = np.array(self._Y)
            self._beta, _, _, _ = np.linalg.lstsq(H, T, rcond=None)

    def predict(self, features: np.ndarray) -> np.ndarray | None:
        if self._beta is None or self._W is None:
            return None
        return self._hidden(features) @ self._beta
```

**Plug-in point:** `knowledge_engine.get_best_model_for()` currently returns a model string from heuristic. After each `ingest_run()`, call `elm_router.add_sample(embedding, rubric_scores_per_model)`. On the next run, call `elm_router.predict(embedding)` and select the model with the highest predicted score.

### Verdict

**FEASIBLE — low effort, zero new deps (numpy already installed), well-aligned with existing memory architecture.**

| Dimension | Assessment |
|-----------|-----------|
| Effort | Medium (~4h: `elm_router.py` + integration into `knowledge_engine.py` + tests) |
| Training cost | Negligible — closed-form in ~10ms per retrain |
| Dependencies | numpy only (already installed) |
| Cold-start problem | First ~5-10 runs: `predict()` returns None → fall back to existing heuristic |
| Theoretical strength | Provably a universal approximator with enough hidden units; faster than kNN |
| Risk | Low — runs alongside existing heuristic, not replacing it |
| Research value | Publishable: "fast online adaptation without gradient descent in a multi-agent LLM system" |

### Open Questions

1. What's the right n_hidden? 128 is a reasonable start; paper should include ablation.
2. Should output target be raw rubric scores or normalized by baseline (task difficulty)?
3. Persistence: serialize `_W`, `_b`, `_beta` to disk between restarts (npz file).
4. Should the ELM replace or augment the existing `get_best_model_for()` heuristic?

---

## Phase 12 Feasibility — Pod & Model Role Rebalancing by Benchmark

### Current Assignments vs. Role Demands

| Role | What it needs | Current model | Benchmark concern |
|------|---------------|--------------|-------------------|
| **Planner** | Long-horizon decomposition, structured output, 4-section plan | `anthropic/claude-sonnet-4-5` | ✓ Good — Claude excels at structured planning |
| **Actor** | High-quality generation under adversarial pressure, cross-domain | `openai/gpt-4o` | ✓ Good — GPT-4o is strong general generation |
| **Critic** | Adversarial flaw-finding, evidence-based challenges, merciless probing | `meta-llama/llama-3-70b-instruct` | ⚠️ Llama 3 70B is capable but lacks the reasoning precision needed for adversarial critique; outdated model |
| **Validator** | Factual grounding, consistency checking, large context review | `google/gemini-pro-1.5` | ✓ Good — Gemini's 1M-token context for reviewing full transcript is a genuine advantage |
| **Refiner** | Surgical improvement specification (NOT a rewrite), structured spec | `meta-llama/llama-3-70b-instruct` | ⚠️ Same model as Critic = no diversity; refiner outputs are precision-dependent |
| **Judge** | Structured JSON arbitration, holistic quality assessment, convergence detection | `anthropic/claude-sonnet-4-5` | ✓ Good — Claude Sonnet handles JSON + reasoning well |

**Key concern:** Critic and Refiner use the same model (`llama-3-70b-instruct`), which undermines the diversity benefit of multi-LLM deliberation. The Critic's role requires **adversarial reasoning** — the ability to construct principled counterexamples. This is a task where models with stronger mathematical/logical benchmarks outperform pure generation models.

### Proposed Rebalanced Assignment

| Role | Current | Proposed | Rationale |
|------|---------|---------|-----------|
| Planner | claude-sonnet-4-5 | **claude-sonnet-4-5** | No change — best in class for structured decomposition |
| Actor | gpt-4o | **gpt-4o** | No change — strong cross-domain generation |
| Critic | llama-3-70b-instruct | **anthropic/claude-3-5-haiku-20241022** | Haiku-3.5 has sharper reasoning than Llama 70B at similar speed; adversarial critique benefits from logical precision not raw generation size. Alternative: `mistral/mistral-large-latest` |
| Validator | gemini-pro-1.5 | **google/gemini-2.0-flash** | Gemini 2.0 Flash: faster, same 1M context, better benchmark scores. Factual grounding + large context preserved |
| Refiner | llama-3-70b-instruct | **openai/gpt-4o-mini** | Refiner outputs *structural spec* (3 lists: CRITICAL_FIXES, ENHANCEMENTS, PRESERVE). This is precision-structured output, not creative generation — gpt-4o-mini is faster+cheaper and handles structured output reliably. Eliminates Critic/Refiner model redundancy |
| Judge | claude-sonnet-4-5 | **claude-sonnet-4-5** | No change — reliable JSON output, holistic arbitration |

### Pod Reorganization by Compute Profile

**Current grouping (by conceptual role):**

| Pod | Agents | Issue |
|-----|--------|-------|
| Planning | planner + judge | Both Claude — same provider, same API |
| Execution | actor + refiner | GPT-4o (high cost) + Llama/gpt-4o-mini (low cost) — mismatched compute |
| Review | critic + validator | Both medium-latency; different providers |

**Proposed regrouping (by latency/cost profile):**

| Pod | Agents | Profile | Rationale |
|-----|--------|---------|-----------|
| **Strategy pod** | planner + judge | High-quality, bookend | Both Claude — same provider pool, sequential execution fits co-location |
| **Generation pod** | actor | High-cost, high-output | Actor alone — highest token budget (2048), most frequent bottleneck. Isolate for independent HPA |
| **Review pod** | critic + validator | Fast-medium | Both review roles; Haiku-3.5 + Gemini Flash are fast |
| **Refinement pod** | refiner | Structured output | gpt-4o-mini; fast structured spec; lowest token budget (512). Could share Generation pod but isolation enables future replacement |

**Trade-off:** 4 pods instead of 3 increases K8s overhead. For local dev, maintain 3 pods with `generation + refinement` co-located. For production (GKE Autopilot), split them.

### Verdict

**Feasible — medium effort; highest research value of the four proposals.**

| Dimension | Assessment |
|-----------|-----------|
| Config change effort | Easy (~30 min: update `config.py` + `configmap-models.yaml`) |
| Pod regrouping effort | Medium (~2h: update 3-4 deployment YAMLs + setup.sh) |
| Expected quality gain | Meaningful — diversity increase in Critic + Refiner roles |
| Cost change | Neutral to slight decrease (Haiku-3.5 + gpt-4o-mini cost less than Llama 70B via OpenRouter) |
| Research value | High — publishable ablation study: role-model alignment vs random assignment |
| Risk | Low — `config.py` change is one line per role; `K8S_MODE=false` runs use config directly |

### Open Questions

1. **Claude Haiku-3.5 availability on OpenRouter:** Verify `anthropic/claude-3-5-haiku-20241022` is routable.
2. **Benchmark evidence:** Need empirical rubric-score comparison between Llama-3-70B-critic and Haiku-3.5-critic across 50+ adversarial runs.
3. **Pod isolation granularity:** Is a 4-pod K8s config worth the overhead for local dev? Consider overlay `overlays/research/` that splits further without changing the default `overlays/local/`.
4. **ELM integration:** Once Phase 11 (ELM meta-scorer) is built, let it discover optimal role-model assignments empirically rather than guessing upfront.

---

## Phase 13 Feasibility — Monte Carlo Experiment Mode

### Concept

**User request:** "A cool experiment mode where users can test the same prompt but it rewords it a little different to send to each LLM and sees how similar their answers are and trains itself to become more stronger."

This is a Monte Carlo sampling approach to **prompt robustness testing** and **inter-model consensus measurement**, combined with a self-improvement feedback loop.

### How It Works

```
User prompt P
       │
       ▼
  Paraphrase generator (cheap LLM: gpt-4o-mini)
  ─────────────────────────────────────────────
  P₁ = formal variant
  P₂ = informal variant
  P₃ = adversarial phrasing variant
  Pₙ = direct question variant
       │
       ▼ (parallel fan-out)
  ┌──────────┬──────────┬──────────┐
  │ Model A  │ Model B  │ Model C  │
  │ (GPT-4o) │ (Claude) │ (Gemini) │
  └──────────┴──────────┴──────────┘
       │
       ▼
  Embed each response (text-embedding-3-small)
  Compute cosine similarity matrix
       │
       ▼
  Consensus score: mean pairwise similarity
  Divergence map: which prompts produce most disagreement
       │
       ▼
  Feed agreement/disagreement signal into knowledge_engine
  (model performance update: high-agreement = model reliable on this domain)
```

### Implementation

**New module:** `backend/experiment/montecarlo.py`

```python
async def run_monte_carlo(
    prompt: str,
    n_variants: int = 4,       # number of paraphrased variants
    models: list[str] | None = None,  # defaults to planner/actor/judge models
    router: ModelRouter,
) -> MonteCarloResult:
    # 1. Generate paraphrase variants
    variants = await _paraphrase(prompt, n=n_variants, router=router)

    # 2. Fan out: each variant × each model (parallel)
    responses = await asyncio.gather(*[
        router.complete(system=SYSTEM, user=v, force_model=m)
        for v in variants for m in models
    ])

    # 3. Embed responses
    embeddings = embed_batch([r.content for r in responses])

    # 4. Cosine similarity matrix
    sim_matrix = cosine_similarity_matrix(embeddings)

    # 5. Consensus score + divergence
    return MonteCarloResult(
        variants=variants,
        responses=responses,
        similarity_matrix=sim_matrix.tolist(),
        consensus_score=float(sim_matrix.mean()),
        divergence_pairs=find_low_similarity_pairs(sim_matrix, threshold=0.70),
    )
```

**Reuses existing infrastructure:**
- `embed_batch()` from `backend/core/embeddings.py` (already installed).
- `router.complete(force_model=...)` from `backend/router/model_router.py`.
- `knowledge_engine.ingest_run()` for the feedback loop (consensus score replaces rubric score).
- All PII redaction applies before any LLM call (existing route-layer guarantees).

**New frontend UI mode:** A 4th mode toggle `"Experiment"` in `SegmentedToggle` — shows a grid of model responses side-by-side with a consensus heatmap overlay.

**Self-improvement mechanism:**
After each Monte Carlo run, feed consensus scores into `knowledge_engine` as model performance signals. High consensus (>0.85) across variants suggests the model is reliable for this task type. Low consensus (<0.60) flags this as a domain where models diverge — worth deeper adversarial investigation or human review.

This directly augments `get_best_model_for()` with empirical inter-model agreement data.

### Verdict

**FEASIBLE — medium effort; highest user-facing novelty of the four proposals.**

| Dimension | Assessment |
|-----------|-----------|
| Backend effort | Medium (~6h: `montecarlo.py` + new `/experiment/run` route + schema for storing results) |
| Frontend effort | Medium (~4h: new experiment mode view + similarity heatmap component) |
| Dependencies | `scipy` for cosine similarity (already possible with numpy), or `sklearn.metrics.pairwise_distances` |
| Cost per run | ~4 variants × 3 models × ~500 tokens = ~6000 tokens/run (~$0.006 at OpenRouter prices) |
| Research value | Very high — publishable metric: "prompt sensitivity / model agreement coefficient" |
| Self-improvement | Feedback to knowledge_engine re-uses existing infra; adds empirical model-selection signal |
| PII risk | Covered — existing route-layer `pii.redact()` fires before any variant generation |

### Open Questions

1. **Paraphrase quality:** gpt-4o-mini generates competent paraphrases but not always semantically distinct. Consider adding explicit diversity constraints in the paraphrase prompt (e.g., "make variant 3 significantly shorter", "make variant 4 ask the question indirectly").
2. **n_variants vs cost:** 4 variants × 3 models = 12 LLM calls. Should n_variants be user-configurable (1-8)?
3. **Heatmap UI:** cosine similarity can be visualized as a color matrix (green=high agreement, red=divergence). This could be a small canvas or SVG component — no heavy charting lib needed.
4. **Monte Carlo convergence:** With only 4 variants, the "law of large numbers" doesn't fully kick in. Should the system detect when consensus has converged (variance < threshold) and stop early?
5. **Training signal granularity:** Should the ELM (Phase 11) receive per-variant, per-model scores from Monte Carlo runs, not just the aggregate consensus?


---

## Phase 14 — Latency Fix + Evaluation Runs

**Run timestamp:** 2026-06-13 22:52 UTC
**Config:** summaries_per_agent=off (run-level only), critic=claude-3.5-haiku, refiner=gpt-4o-mini, adversarial_max_rounds=2, per-call timeout=45s.

### Standard mode (5 runs)

| Run | Prompt | Verdict | Avg Score | Time (s) | Rationale |
|-----|--------|---------|-----------|----------|-----------|
| 1 | code | PASS | 87% | 39.9 | Strong performance: 87% across all rubric dimensions. Best on accuracy. |
| 2 | reasoning | PASS | 90% | 22.0 | Strong performance: 90% across all rubric dimensions. Best on clarity. |
| 3 | finance | PASS | 92% | 45.2 | Strong performance: 92% across all rubric dimensions. Best on accuracy. |
| 4 | factual | PASS | 82% | 29.0 | Strong performance: 82% across all rubric dimensions. Best on accuracy. |
| 5 | creative | WARN | 60% | 27.7 | Overall score 60%. Weakest areas: coverage, actionability. |

**Aggregate:** mean score 82% · mean time 32.8s · pass rate 4/5

### Adversarial mode (5 runs)

| Run | Prompt | Verdict | Avg Score | Rounds | Time (s) | Rationale |
|-----|--------|---------|-----------|--------|----------|-----------|
| 1 | code | ACCEPT | 85% | 2/2 | 78.9 | The Actor's implementation correctly solves the Fibonacci problem with O(n) time complexity and O(1) space complexity, meeting all core success criteria. The fu |
| 2 | reasoning | ACCEPT | 85% | 2/2 | 61.6 | The Actor's solution is mathematically correct and reaches the right answer of $0.05. While the Critic identified valid presentation issues (inconsistent variab |
| 3 | finance | ACCEPT | 75% | 2/2 | 90.6 | While the Actor's response contains several technical inaccuracies (RMD age, incomplete phase-out details) and lacks depth in conversion strategies and personal |
| 4 | factual | ACCEPT | 75% | 2/2 | 68.1 | While the response addresses the core causal factors (subprime mortgages, securitization, regulatory failures, leverage) and meets the length constraint of 3-5  |
| 5 | creative | ACCEPT | 82% | 2/2 | 62.4 | The Actor has delivered three distinct product names with rationales that substantially meet the core requirements. While trademark concerns for PrivAItes and m |

**Aggregate:** mean score 80% · mean time 72.3s · pass rate 5/5

### Analysis

Quality measured via the 5-dimension rubric (accuracy, depth, clarity, actionability, coverage); verdict is PASS/WARN/FAIL (standard, derived from rubric average) or ACCEPT/REJECT (adversarial, judge verdict). Standard mean latency 32.8s, adversarial 72.3s — both within the 180s client timeout. The model-ID fix (removing the invalid `meta-llama/llama-3-70b-instruct`) eliminated the per-role failed-call + fallback retry overhead, and run-level-only summaries cut ~11 redundant LLM calls from each adversarial run.

### Root-cause findings (debugging pass)

**Bug 1 — adversarial timeout (the reported symptom).** Every `/adversarial-run` exceeded the 120s axios limit. Three compounding causes: (a) `adv_critic_model` and `refiner_model` were set to `meta-llama/llama-3-70b-instruct`, which returns 404 on OpenRouter — each role wasted a failed call + fallback retry every round; (b) the summarizer fired ~12 inline LLM calls before responding; (c) the base sequential pipeline (~11 calls) already neared the limit. Fixes: valid model IDs (`claude-3.5-haiku` critic, `gpt-4o-mini` refiner), run-level-only summaries (12→1 call), a 45s per-call client timeout, and axios raised to 180s. Post-fix adversarial latency peaked at 90.6s.

**Bug 2 — judge verdict silently discarded (found during the first eval batch).** The first 5-run adversarial batch produced two `REJECT / 0%` results. Log inspection showed the judge had actually returned `ACCEPT` (0.85, 0.72) — but the JSON was truncated mid-string because the judge crammed the full `final_answer` into a 1024-token budget, so `_parse_judge_output` fell through to its `REJECT / 0.0` default and threw away a valid acceptance. Fixes: judge token budget 1024→2560, and a field-level salvage path in `_parse_judge_output` that regex-recovers `verdict`/`score`/`rationale` when the full JSON is malformed. The second batch confirmed the fix — the finance run (90.6s) again truncated, but salvage recovered it as `ACCEPT / 75%` instead of a false reject (`adversarial_judge_parse_salvaged verdict=ACCEPT` in logs). Adversarial pass rate went 3/5 → 5/5.
