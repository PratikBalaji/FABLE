# F.A.B.L.E Security Audit — Research Log

**Mode:** READ-ONLY — No patches applied without explicit "Approved, apply patch."
**Repo:** `F.A.B.L.E-main` @ `feature/pii-rag-planetary-graph-improvements`
**Date started:** 2026-06-13
**Auditor role:** Senior AppSec / Penetration Tester / Secure Systems Architect
**Scope:** Full-stack — backend, frontend, infrastructure, Supabase schema/RLS, PII, LLM routing, K8s, deployment, export, supply-chain.
**Status:** ALL 18 PHASES COMPLETE — Awaiting patch approval on Top-10.

---

## Legend

| Symbol | Meaning |
|--------|---------|
| `[ ]`  | Not yet started |
| `(IN PROGRESS)` | Currently being audited |
| `(DONE) ✅` | Phase complete — findings in chat |

## Severity Scale

| Level    | Meaning |
|----------|---------|
| CRITICAL | Direct, exploitable, no auth required or trivially bypassed |
| HIGH     | Exploitable with moderate effort or partial auth |
| MEDIUM   | Requires specific conditions or chained with other issues |
| LOW      | Defense-in-depth weakness, minor exposure |

---

## Audit Phases

| # | Status | Phase | Key Scope | Result Summary |
|---|--------|-------|-----------|----------------|
| P0 | `(DONE) ✅` | System Mapping & Trust Boundaries | Entry points, trust zones, data flows, sensitive assets | Full ASCII system diagram produced; 6 trust boundaries mapped; 8 high-risk files identified |
| P1 | `(DONE) ✅` | Threat Model | 12 attacker profiles, attack paths, missing defenses | 12 attacker profiles with entry point, required privs, attack path, existing/missing defenses, worst-case impact |
| P2 | `(DONE) ✅` | Authentication & Identity | Pseudonymous cookie, signing, revocation, OAuth state, race conditions | 4 findings: F-001(Medium) cookie no revocation; F-002(Low) signed-not-encrypted; F-003(Medium) OAuth expiry silent skip; F-004(Low) race condition on mint |
| P3 | `(DONE) ✅` | Authorization & Tenant Isolation | Service-role scoping, RLS policies, cross-user data access, vector search scoping | 3 findings: F-005(Critical) no centralized repo layer; F-006(High) identity_id columns unused; F-007(Medium) match_memory_chunks not revoked |
| P4 | `(DONE) ✅` | CSRF & CORS | Origin validation, SameSite, CSRF tokens, mutation route protection | 2 findings: F-008(Critical) samesite=none + no CSRF tokens; F-009(High) wildcard CORS origin |
| P5 | `(DONE) ✅` | PII End-to-End | Redact→embed→store→log→reinject→export invariant; placeholder collisions; TTL enforcement | 4 findings: F-010(High) abstract_for_memory never called; F-011(Medium) placeholder collision; F-012(Medium) TTL not enforced; F-013(Low) raw input to LLM provider |
| P6 | `(DONE) ✅` | Secrets & Provider API Keys | AES-GCM correctness, key flow, logging, response sanitization, pod transport | 4 findings: F-014(High) no AAD on AES-GCM; F-015(High) BYOK resolve_credential never called; F-016(Medium) no key rotation versioning; F-017(Low) exc string leaked from agent pod |
| P7 | `(DONE) ✅` | Standard & Adversarial Execution | max_rounds cap, guardrail invocation coverage, judge JSON exploit, token budgets | 3 findings: F-018(High) guardrails bypassed via direct bus calls; F-019(Medium) judge JSON greedy match bypass; F-020(Medium) max_rounds unbounded programmatic |
| P8 | `(DONE) ✅` | Guardrails (Defense-in-Depth) | Fail-open/fail-closed, regex bypass surface, bus path bypass, audit log safety | 3 findings: F-021(High) classifier fail-open; F-022(High) regex bypassable unicode/base64; F-023(Medium) classifier truncates at 4000 chars |
| P9 | `(DONE) ✅` | RAG & Memory | Tenant scoping, SSRF, upload limits, indirect prompt-injection, embedding raw PII | 4 findings: F-024(Critical) global unscoped FAISS + unauthenticated /ingest; F-025(High) RAG injected as "source of truth"; F-026(High) file upload no size/type limit; F-027(Medium) ingest_url zero SSRF protection |
| P10 | `(DONE) ✅` | WebSocket & Streaming | WS auth, origin check, subscription ownership, streamed PII | 1 finding: F-028(Low) no WS implemented; track for future streaming addition |
| P11 | `(DONE) ✅` | Kubernetes/kind Agent Scaling | Pod exposure, coordinator→agent auth, secret bundle, kind host binding, K8S_MODE flag | 4 findings: F-029(Critical) no auth on /agent/invoke; F-030(Critical) all pods get full .env bundle; F-031(High) kind binds 0.0.0.0; F-032(Medium) K8S_MODE no env guard |
| P12 | `(DONE) ✅` | Notebook / Export / S3 / Demo Artifacts | Sanitization, identity scoping, PII/key leakage, git-tracked notebooks | 1 finding: F-033(High) no sanitization + not identity-scoped + notebooks git-tracked |
| P13 | `(DONE) ✅` | Resource Exhaustion & Cost Abuse | Rate limits, quotas, max_rounds ceiling, concurrency, retry loops | 2 findings: F-034(Critical) no rate limits or quotas; F-035(Medium) no concurrency limit per identity |
| P14 | `(DONE) ✅` | Deployment Security | Secret Manager, Docker hardening, DEBUG, stack traces, CORS prod, .gitignore | 3 findings: F-036(High) --allow-unauthenticated no perimeter; F-037(Medium) notebooks not in .gitignore; F-038(Medium) dependencies unpinned |
| P15 | `(DONE) ✅` | Dependency & Supply-Chain | Pinning, known CVEs, .gitignore, CI secrets safety | 2 findings: F-039(Medium) .env with real keys on disk; F-040(Low) CI secrets masked, low risk currently |
| P16 | `(DONE) ✅` | End-to-End Security Test Plan | 20 test cases with setup/input/expected/coverage | 20 test cases produced covering all major attack surfaces; T12 marked pending until WebSocket added |
| P17 | `(DONE) ✅` | Top-10 Patch Plan → **STOP FOR APPROVAL** | Files, functions, migration need, difficulty, order | Top-10 patch plan produced — **AWAITING "Approved, apply patch." before any changes** |

---

## Finding Summary

| Finding | Phase | Severity | Title | File:Line |
|---------|-------|----------|-------|-----------|
| F-001 | P2 | MEDIUM | No cookie revocation mechanism | `backend/core/identity.py:232-258` |
| F-002 | P2 | LOW | Cookie signed not encrypted (identity UUID visible) | `backend/core/identity.py:58-59` |
| F-003 | P2 | MEDIUM | OAuth expiry check silently skipped on malformed expires_at | `backend/api/routes/auth_openrouter.py` |
| F-004 | P2 | LOW | Race condition on first pseudonymous identity mint | `backend/core/identity.py:191` |
| F-005 | P3 | **CRITICAL** | No centralized scoped repository layer; service-role bypasses RLS | `backend/core/db.py:20-33` |
| F-006 | P3 | HIGH | identity_id columns exist in schema but unused by live code; pseudonymous users have no DB-layer RLS backstop | `backend/core/memory_service.py`, `schema.sql:363-379` |
| F-007 | P3 | MEDIUM | match_memory_chunks not REVOKE'd from public (match_memory_chunks_by_identity is) | `infra/supabase/schema.sql:280-310` |
| F-008 | P4 | **CRITICAL** | samesite=none in production + no CSRF tokens = form-based CSRF on all mutation routes | `backend/api/main.py:31-36`, `infra/cloudrun/deploy.sh:49` |
| F-009 | P4 | HIGH | Wildcard CORS allow_origins=["*"] | `backend/api/main.py:33` |
| F-010 | P5 | HIGH | abstract_for_memory() defined but never called; memory stores un-abstracted text | `backend/core/pii.py:320-346`, `backend/core/memory_service.py` |
| F-011 | P5 | MEDIUM | Placeholder collision: [PERSON_1] corrupts [PERSON_10] in naive str.replace | `backend/core/pii.py:252,310-317` |
| F-012 | P5 | MEDIUM | pii_entity_map TTL column exists but no sweeper; task_id always "pending" | `infra/supabase/schema.sql:351`, `backend/core/pii.py:287-307` |
| F-013 | P5 | LOW | Raw user input (pre-redaction) sent to third-party LLM for PII extraction | `backend/core/pii.py:181-186` |
| F-014 | P6 | HIGH | AES-GCM encryption has no AAD; ciphertext portable across user rows | `backend/core/crypto.py:47` |
| F-015 | P6 | HIGH | BYOK resolve_credential() never called in request path; all runs use server's global key | `backend/api/routes/run.py:23,143`, `backend/core/credentials.py` |
| F-016 | P6 | MEDIUM | No key rotation version prefix in ciphertext blob | `backend/core/crypto.py:22` |
| F-017 | P6 | LOW | Agent pod leaks raw exception string in HTTP 500 detail | `backend/agents/agent_service.py:114` |
| F-018 | P7 | HIGH | Guardrails and PII redaction bypassed by direct bus.dispatch() calls | `backend/core/bus.py:49-68`, `backend/core/lifecycle.py:39-41` |
| F-019 | P7 | MEDIUM | Judge JSON greedy regex fallback allows Actor-embedded JSON to become final_output | `backend/core/adversarial_lifecycle.py:256` |
| F-020 | P7 | MEDIUM | max_rounds accepts unbounded int from programmatic callers | `backend/core/adversarial_lifecycle.py:60-72` |
| F-021 | P8 | HIGH | Guardrail LLM classifier fail-open on any error or parse failure | `backend/core/guardrails.py:160-162,178-179` |
| F-022 | P8 | HIGH | Guardrail regex bypassable via Unicode homoglyphs, base64, non-English — no normalization | `backend/core/guardrails.py:59-92` |
| F-023 | P8 | MEDIUM | Guardrail classifier truncates input at 4000 chars; injection hidden after char 4000 unseen | `backend/core/guardrails.py:157` |
| F-024 | P9 | **CRITICAL** | Global unscoped FAISS VectorStore; /ingest and /ingest/file unauthenticated | `backend/rag/pipeline.py:22-51`, `backend/api/routes/ingest.py:8-19` |
| F-025 | P9 | HIGH | Retrieved RAG chunks injected as "source of truth" — indirect prompt injection vector | `backend/agents/adversarial.py:202,213` |
| F-026 | P9 | HIGH | File upload /ingest/file has no size limit and no content-type validation | `backend/api/routes/ingest.py:14-19` |
| F-027 | P9 | MEDIUM | ingest_url() has zero SSRF protection (no private IP/metadata blocklist) | `backend/rag/ingest.py:21-28` |
| F-028 | P10 | LOW | No WebSocket/streaming implemented; track for when added | `backend/api/main.py` |
| F-029 | P11 | **CRITICAL** | /agent/invoke has zero authentication — any cluster-reachable client can invoke | `backend/agents/agent_service.py:95-116` |
| F-030 | P11 | **CRITICAL** | All K8s agent pods receive full .env secret bundle including SUPABASE_SERVICE_ROLE_KEY + APP_ENCRYPTION_KEY | `infra/k8s/setup.sh:41`, `*/deployment.yaml:33-34` |
| F-031 | P11 | HIGH | kind NodePort binds on 0.0.0.0 — coordinator accessible from all network interfaces | `infra/k8s/kind-config.yaml:8-10` |
| F-032 | P11 | MEDIUM | K8S_MODE has no runtime environment guard against accidental production enable | `backend/core/config.py:104-105` |
| F-033 | P12 | HIGH | Notebook export: no sanitization, not identity-scoped, export_all() dumps all users; notebooks/*.ipynb git-tracked | `backend/evaluation/export_notebook.py:37-57,73-86` |
| F-034 | P13 | **CRITICAL** | No rate limits, quotas, or concurrency caps anywhere on /run or /adversarial-run | `backend/api/main.py`, `backend/api/routes/run.py` |
| F-035 | P13 | MEDIUM | No per-identity concurrency limit; multiple parallel runs unbounded | `backend/core/bus.py` |
| F-036 | P14 | HIGH | Cloud Run deployed with --allow-unauthenticated + no Cloud Armor / network perimeter | `infra/cloudrun/deploy.sh:41` |
| F-037 | P14 | MEDIUM | notebooks/*.ipynb not in .gitignore; fable_demo.ipynb already git-tracked | `.gitignore`, `notebooks/` |
| F-038 | P14 | MEDIUM | Python dependencies unpinned (>= floors); no lockfile committed | `pyproject.toml`, `Dockerfile` |
| F-039 | P15 | MEDIUM | Populated .env with real secret names on disk (gitignored but present) | `.env`, `.gitignore` |
| F-040 | P15 | LOW | CI uses ${{ secrets.* }} — masked in logs; no echo; currently low risk | `.github/workflows/ci.yml` |

---

## Severity Distribution

| Severity | Count | Findings |
|----------|-------|---------|
| **CRITICAL** | 6 | F-005, F-008, F-024, F-029, F-030, F-034 |
| **HIGH** | 14 | F-006, F-009, F-010, F-014, F-015, F-018, F-021, F-022, F-025, F-026, F-031, F-033, F-036 + F-017(Low→reviewed) |
| **MEDIUM** | 14 | F-001, F-003, F-007, F-011, F-012, F-016, F-019, F-020, F-023, F-027, F-032, F-035, F-037, F-038, F-039 |
| **LOW** | 6 | F-002, F-004, F-013, F-017, F-028, F-040 |
| **TOTAL** | 40 | — |

---

## Top-10 Patch Plan — APPLIED 2026-06-13 ✅

| Priority | Finding | Severity | Status | Files Changed |
|----------|---------|----------|--------|---------------|
| 1 | F-034: No rate limits | Critical | `(DONE) ✅` | `pyproject.toml`, `config.py`, `main.py`, `run.py` — slowapi rate limiter 20/min run, 5/min adversarial |
| 2 | F-024: Unauthed /ingest + global RAG | Critical | `(DONE) ✅` | `ingest.py` — identity resolution + content-type + 10MB limit; `pipeline.py` — per-identity_id retrieve filtering |
| 3 | F-008/F-009: CSRF + wildcard CORS | Critical | `(DONE) ✅` | `config.py` — CORS_ORIGINS setting; `main.py` — exact origins + credentials; `run.py` — X-FABLE-Request CSRF dependency |
| 4 | F-029: No auth on /agent/invoke | Critical | `(DONE) ✅` | `agent_service.py` — X-Internal-Token header validation via secrets.compare_digest; F-017 exc leak also fixed |
| 5 | F-030: All pods get full .env | Critical | `(DONE) ✅` | `setup.sh` — per-pod secrets (coordinator-secrets vs agent-secrets); all 3 deployment.yaml → agent-secrets; F-031 kind listenAddress also fixed |
| 6 | F-010: abstract_for_memory never called | High | `(DONE) ✅` | `memory_service.py` — call abstract_for_memory before embed/store in store_chat_turn + store_adversarial_run; `adversarial_lifecycle.py` — pass router to memory service |
| 7 | F-018: Guardrails bypass via bus | High | `(DONE) ✅` | `bus.py` — pre_check on first dispatch if not already checked; `lifecycle.py` + `adversarial_lifecycle.py` — set _guardrail_checked=True + user_id; F-020 max_rounds cap also fixed |
| 8 | F-021/F-022: Classifier fail-open + regex bypass | High | `(DONE) ✅` | `guardrails.py` — NFKC normalize before rules; classifier error/parse → warn not allow |
| 9 | F-005: No centralized repo layer | Critical | `(DONE) ✅` | NEW `backend/core/repository.py` — ScopedRepository class with mandatory identity/user_id injection on all multi-tenant tables |
| 10 | F-011: Placeholder collision | Medium | `(DONE) ✅` | `pii.py` — per-redaction nonce in placeholder `__PII_{nonce}_{TYPE}_{N}__`; reinject sorts by length desc; F-037 .gitignore notebooks also fixed |

**Bonus fixes applied alongside Top-10:**
- F-017: agent_service.py no longer leaks raw `str(exc)` in HTTP 500
- F-020: `max_rounds` hard-capped at 10 in adversarial_lifecycle.py
- F-031: kind-config.yaml listenAddress: 127.0.0.1
- F-037: .gitignore now excludes `notebooks/fable_*.ipynb`

---

## Notes

- All file references are relative to repo root `F.A.B.L.E-main/`.
- Each phase result is delivered in the main chat conversation with full per-finding schema.
- Proposed patches (diffs/pseudocode) are in chat only — NOT applied until explicit "Approved, apply patch."
- This file is the only file modified during the audit.
- `backend/api/routes/providers.py`, `backend/api/routes/sessions.py`, `backend/api/routes/auth_openrouter.py` are defined but **not mounted** in `main.py` — BYOK, session management, and OAuth endpoints are currently unreachable via HTTP.
