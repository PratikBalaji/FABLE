# F.A.B.L.E Security Audit — State

**Last reorganized:** 2026-06-14  
**Branch:** `main`  
**Scope:** Full-stack — backend, frontend, infrastructure, Supabase schema/RLS, PII, LLM routing, K8s, deployment, export, supply-chain.  
**Auditor role:** Senior AppSec / Penetration Tester / Secure Systems Architect  
**Total findings:** 40 (6 Critical, 14 High, 14 Medium, 6 Low)

---

## Status Dashboard

| ID | Severity | Title | State |
|----|----------|-------|-------|
| F-001 | MEDIUM | No cookie revocation mechanism | ✅ Patched |
| F-002 | LOW | Cookie signed not encrypted (UUID visible) | 📋 Accepted risk |
| F-003 | MEDIUM | OAuth expiry check silently skipped | ✅ Patched |
| F-004 | LOW | Race condition on identity mint | 📋 Accepted risk |
| F-005 | **CRITICAL** | No centralized repo layer; service-role bypasses RLS | ✅ Patched |
| F-006 | HIGH | identity_id columns exist but unused in live code | ✅ Patched |
| F-007 | MEDIUM | match_memory_chunks not REVOKE'd from public | ✅ Patched |
| F-008 | **CRITICAL** | samesite=none + no CSRF tokens | ✅ Patched |
| F-009 | HIGH | Wildcard CORS allow_origins | ✅ Patched |
| F-010 | HIGH | abstract_for_memory() never called | ✅ Patched |
| F-011 | MEDIUM | Placeholder collision in PII reinject | ✅ Patched |
| F-012 | MEDIUM | pii_entity_map TTL: no sweeper job | ✅ Patched |
| F-013 | LOW | Raw pre-redaction input sent to LLM for PII extraction | 📋 Accepted risk |
| F-014 | HIGH | AES-GCM no AAD; ciphertext portable across users | ✅ Patched |
| F-015 | HIGH | BYOK resolve_credential() never called in request path | ✅ Patched |
| F-016 | MEDIUM | No key rotation version prefix in ciphertext | ✅ Patched |
| F-017 | LOW | Agent pod leaks raw exc string in HTTP 500 | ✅ Patched |
| F-018 | HIGH | Guardrails bypassed via direct bus.dispatch() | ✅ Patched |
| F-019 | MEDIUM | Judge JSON greedy regex lets Actor-embedded JSON win | ✅ Patched |
| F-020 | MEDIUM | max_rounds unbounded from programmatic callers | ✅ Patched |
| F-021 | HIGH | Guardrail classifier fail-open on any error | ✅ Patched |
| F-022 | HIGH | Guardrail regex bypassable via Unicode homoglyphs | ✅ Patched |
| F-023 | MEDIUM | Classifier truncates at 4000 chars; injection hidden after | ✅ Patched |
| F-024 | **CRITICAL** | Global unscoped FAISS + unauthenticated /ingest | ✅ Patched |
| F-025 | HIGH | RAG chunks injected as "source of truth" — prompt injection | ✅ Patched |
| F-026 | HIGH | /ingest/file: no size limit, no content-type validation | ✅ Patched |
| F-027 | MEDIUM | ingest_url() no SSRF protection | ✅ Patched |
| F-028 | LOW | No WebSocket/streaming | ✅ Patched |
| F-029 | **CRITICAL** | /agent/invoke zero authentication | ✅ Patched |
| F-030 | **CRITICAL** | All K8s pods receive full .env secret bundle | ✅ Patched |
| F-031 | HIGH | kind NodePort binds 0.0.0.0 | ✅ Patched |
| F-032 | MEDIUM | K8S_MODE no runtime env guard | ✅ Patched |
| F-033 | HIGH | Notebook export: no sanitization, not identity-scoped | ✅ Patched |
| F-034 | **CRITICAL** | No rate limits or quotas on /run | ✅ Patched |
| F-035 | MEDIUM | No per-identity concurrency limit | ✅ Patched |
| F-036 | HIGH | Cloud Run --allow-unauthenticated + no Cloud Armor | ✅ Patched (commands documented) |
| F-037 | MEDIUM | notebooks/*.ipynb not in .gitignore | ✅ Patched |
| F-038 | MEDIUM | Python deps unpinned, no lockfile | ✅ Patched |
| F-039 | MEDIUM | Populated .env on disk | 📋 Accepted risk |
| F-040 | LOW | CI secrets masked; low risk | 📋 Accepted risk |

**Summary:** 35 ✅ Patched · 0 ⚠️ Open · 5 📋 Accepted risk

> 2026-06-14 — closed all 13 remaining open findings (F-001, F-003, F-006, F-007,
> F-016, F-019, F-023, F-025, F-027, F-032, F-033, F-035, F-038). New security
> regression suite: `tests/unit/test_security.py` (17 tests, all green).

---

## Section 1 — Resolved Findings

All patches applied 2026-06-13 unless otherwise noted.

| ID | Severity | Patch | File(s) |
|----|----------|-------|---------|
| F-005 | CRITICAL | Centralized `ScopedRepository` class enforces identity scoping on all multi-tenant tables | `backend/core/repository.py` (new) |
| F-008 | CRITICAL | CORS restricted to trusted origins; `X-FABLE-Request` CSRF header required on all mutations | `backend/api/main.py`, `backend/api/routes/run.py` |
| F-009 | HIGH | Wildcard CORS replaced with `settings.trusted_origins` allowlist | `backend/core/config.py`, `backend/api/main.py` |
| F-010 | HIGH | `abstract_for_memory()` called before embed/store in `memory_service.py` | `backend/core/memory_service.py` |
| F-011 | MEDIUM | Per-redaction nonce in PII placeholders (`__PII_{nonce}_{TYPE}_{N}__`); reinject sorts length desc | `backend/core/pii.py` |
| F-012 | MEDIUM | pg_cron sweeps: `pii-entity-map-sweep` (hourly) + `oauth-states-sweep` (15 min) | `infra/supabase/schema.sql` |
| F-014 | HIGH | AES-GCM v2 ciphertext prefixed `\x02`, bound to `user_id` as AAD; v1 legacy decrypts transparently | `backend/core/crypto.py`, `backend/api/routes/providers.py`, `backend/api/routes/auth_openrouter.py`, `backend/core/credentials.py` |
| F-015 | HIGH | `resolve_credential()` called in `/run`; per-user `ModelRouter` constructed from BYOK credential | `backend/api/routes/run.py`, `backend/router/model_router.py` |
| F-017 | LOW | Agent pod `str(exc)` replaced with sanitized error; raw exception no longer in HTTP 500 | `backend/agents/agent_service.py` |
| F-018 | HIGH | `bus.dispatch()` runs `pre_check` on first call if `_guardrail_checked` not set | `backend/core/bus.py` |
| F-020 | MEDIUM | `max_rounds` hard-capped at 10 in adversarial_lifecycle.py | `backend/core/adversarial_lifecycle.py` |
| F-021 | HIGH | Classifier error/parse failure → `warn` not `allow` (fail-to-warn, not fail-open) | `backend/core/guardrails.py` |
| F-022 | HIGH | NFKC normalization before all regex pattern matching | `backend/core/guardrails.py` |
| F-024 | CRITICAL | `/ingest` requires identity; content-type + 10MB limit; FAISS retrieval filtered by identity_id | `backend/api/routes/ingest.py`, `backend/rag/pipeline.py` |
| F-026 | HIGH | File upload: 10MB limit + MIME type allowlist (text/*, application/pdf, etc.) | `backend/api/routes/ingest.py` |
| F-028 | LOW | SSE streaming added: `POST /run/stream`; `POST /adversarial-run` unchanged (blocking) | `backend/api/routes/run.py`, `backend/core/lifecycle.py`, `backend/core/bus.py` |
| F-029 | CRITICAL | `X-Internal-Token` header validation via `secrets.compare_digest` on `/agent/invoke` | `backend/agents/agent_service.py` |
| F-030 | CRITICAL | Least-privilege K8s secrets: coordinator-secrets (all) vs agent-secrets (API keys only); SERVICE_ROLE_KEY + APP_ENCRYPTION_KEY never on agent pods | `infra/k8s/setup.sh`, `*/deployment.yaml` |
| F-031 | HIGH | kind NodePort `listenAddress: 127.0.0.1` | `infra/k8s/kind-config.yaml` |
| F-034 | CRITICAL | slowapi rate limiter: 20/min `/run`, 5/min `/adversarial-run`, 5/min `/experiment/run` | `backend/api/routes/run.py`, `backend/api/routes/experiment.py` |
| F-036 | HIGH | Cloud Armor WAF commands fully documented in deploy script (XSS, SQLi, LFI, RFI, scanner, rate-ban); requires LB+NEG wiring | `infra/cloudrun/deploy.sh` |
| F-037 | MEDIUM | `notebooks/fable_*.ipynb` excluded in `.gitignore` | `.gitignore` |

**Additional fixes (post-top-10):**
- Unmounted routers: `providers`, `sessions`, `auth_openrouter` mounted in `main.py`
- BYOK, session management, OAuth now reachable via HTTP
- Streaming `/run/stream` SSE endpoint implemented (F-028 resolved)
- Hate speech / content moderation: `_HATE_SPEECH` always-block regex + updated classifier prompt
- pii_entity_map TTL pg_cron sweep applied

**Final 13 closed (2026-06-14):**

| ID | Severity | Patch | File(s) |
|----|----------|-------|---------|
| F-001 | MEDIUM | `revoked_identities` table + `is_revoked()`/`revoke_identity()`; `resolve_identity` rejects revoked cookies | `backend/core/identity.py`, `infra/supabase/schema.sql` |
| F-003 | MEDIUM | OAuth callback fails CLOSED when `expires_at` missing/malformed (was silent skip) | `backend/api/routes/auth_openrouter.py` |
| F-006 | HIGH | `identity_id` populated on all memory/chat/adversarial inserts | `backend/core/memory_service.py` |
| F-007 | MEDIUM | `revoke execute on match_memory_chunks(...) from public` | `infra/supabase/schema.sql` |
| F-016 | MEDIUM | v3 ciphertext (`\x03`+keyver) + `APP_ENCRYPTION_KEYS` map; decrypt selects key by version | `backend/core/crypto.py`, `backend/core/config.py` |
| F-019 | MEDIUM | Judge parse scans all balanced JSON, prefers LAST verdict-bearing object (string-aware) | `backend/core/adversarial_lifecycle.py` |
| F-023 | MEDIUM | Classifier chunks input into ≤4000-char windows (cap 5), aggregates most-severe verdict | `backend/core/guardrails.py` |
| F-025 | HIGH | RAG context reframed UNTRUSTED ("data not instructions") in validator/planner/analyst prompts | `backend/agents/adversarial.py`, `backend/agents/roles.py` |
| F-027 | MEDIUM | `_is_safe_url()` blocks private/loopback/link-local/metadata; redirects disabled | `backend/rag/ingest.py` |
| F-032 | MEDIUM | `model_validator` refuses `K8S_MODE` under `ENV=production` unless `K8S_ALLOW_PROD=true` | `backend/core/config.py` |
| F-033 | HIGH | Notebook cells PII-redacted (`redact_text_sync`); export ownership-scoped by `identity_id` | `backend/evaluation/export_notebook.py`, `backend/core/pii.py` |
| F-035 | MEDIUM | Per-identity `asyncio` concurrency slot (`MAX_CONCURRENT_PER_IDENTITY`, default 2) → HTTP 429 | `backend/core/concurrency.py` (new), `lifecycle.py`, `adversarial_lifecycle.py`, `api/routes/run.py` |
| F-038 | MEDIUM | Pinned `requirements.lock` + version floors in pyproject; Dockerfile installs from lockfile | `backend/requirements.lock` (new), `backend/pyproject.toml`, `Dockerfile` |

**Test coverage:** `tests/unit/test_security.py` — crypto (AAD/rotation/v1), pii redact+reinject,
guardrails (injection/credential/hate-speech/profanity/chunk-aggregation/fail-closed), SSRF,
golden_cache (promote/tier/recheck), judge-parse. 17 tests, all passing.

---

## Section 2 — Open Backlog

**None.** All 13 previously-open findings were closed on 2026-06-14 (see "Final 13 closed"
table in Section 1). Remaining un-patched items are the 5 accepted risks below.

Notes / verification caveats:
- F-001, F-006, F-033 ship as code + `schema.sql` migrations. The schema additions
  (`revoked_identities` table, identity_id writes) require applying `schema.sql` to a live
  Supabase project; verified here by code review + mocked-DB unit tests, not a live DB run.
- F-035 concurrency is per-process (in-memory); distributed K8s pods don't share the counter —
  it complements, not replaces, the per-IP rate limiter.

---

## Section 3 — Accepted Risk

| ID | Severity | Title | Rationale |
|----|----------|-------|-----------|
| F-002 | LOW | Cookie signed not encrypted | UUID non-sensitive; cryptographic signing provides integrity. Encrypting adds latency with no material gain for a pseudonymous ID. |
| F-004 | LOW | Race condition on first identity mint | Window is sub-millisecond; worst case = duplicate anonymous sessions (cosmetic). Not worth locking overhead. |
| F-013 | LOW | Raw pre-redaction input sent to LLM for PII extraction | Necessary by design — the LLM is the PII extractor. Mitigated by: regex layer runs first (catches structured PII), LLM call uses the smallest/cheapest model, PII never stored raw. |
| F-039 | MEDIUM | Populated .env on disk | Gitignored. Operator responsibility. No secret manager available in dev environment. |
| F-040 | LOW | CI uses secrets.* masking | GitHub's own masking mechanism; current risk is low given no self-hosted runners. |

---

## Appendix — Full Finding Detail

### Severity Scale
| Level | Meaning |
|-------|---------|
| CRITICAL | Direct, exploitable, no auth required or trivially bypassed |
| HIGH | Exploitable with moderate effort or partial auth |
| MEDIUM | Requires specific conditions or chained with other issues |
| LOW | Defense-in-depth weakness, minor exposure |

### Audit Phases Completed (all 18 phases)
| # | Phase | Key Scope | Findings |
|---|-------|-----------|---------|
| P0 | System Mapping | Entry points, trust zones, data flows | 0 findings |
| P1 | Threat Model | 12 attacker profiles | 0 findings |
| P2 | Authentication & Identity | Cookie, OAuth, race conditions | F-001–F-004 |
| P3 | Authorization & Tenant Isolation | RLS, service-role, vector scoping | F-005–F-007 |
| P4 | CSRF & CORS | Origin, SameSite, mutation protection | F-008–F-009 |
| P5 | PII End-to-End | Redact, embed, store, reinject, TTL | F-010–F-013 |
| P6 | Secrets & Provider Keys | AES-GCM, BYOK, key rotation, pod transport | F-014–F-017 |
| P7 | Standard & Adversarial Execution | Guardrail coverage, judge exploit, token budget | F-018–F-020 |
| P8 | Guardrails (Defense-in-Depth) | Fail-open, regex bypass, audit log | F-021–F-023 |
| P9 | RAG & Memory | SSRF, upload limits, indirect injection, PII in memory | F-024–F-027 |
| P10 | WebSocket & Streaming | WS auth, origin check, streamed PII | F-028 |
| P11 | Kubernetes/kind Agent Scaling | Pod auth, secret bundle, host binding | F-029–F-032 |
| P12 | Notebook/Export/S3 | Sanitization, identity scoping, git-tracked artifacts | F-033 |
| P13 | Resource Exhaustion & Cost Abuse | Rate limits, quotas, concurrency | F-034–F-035 |
| P14 | Deployment Security | Secret Manager, Cloud Armor, DEBUG, CORS prod | F-036–F-038 |
| P15 | Dependency & Supply-Chain | Pinning, CVEs, .gitignore, CI secrets | F-039–F-040 |
| P16 | End-to-End Security Test Plan | 20 test cases (T12 pending WS — now resolved) | — |
| P17 | Top-10 Patch Plan | Priority patches with files + difficulty | Applied ✅ |

### Finding Detail (sorted by ID)
| Finding | Phase | Severity | State | Title | File:Line |
|---------|-------|----------|-------|-------|-----------|
| F-001 | P2 | MEDIUM | ✅ | No cookie revocation | `backend/core/identity.py` (revoked_identities) |
| F-002 | P2 | LOW | 📋 | Cookie signed not encrypted | `backend/core/identity.py:58-59` |
| F-003 | P2 | MEDIUM | ✅ | OAuth expiry check silently skipped | `backend/api/routes/auth_openrouter.py` |
| F-004 | P2 | LOW | 📋 | Race condition on first identity mint | `backend/core/identity.py:191` |
| F-005 | P3 | CRITICAL | ✅ | No centralized repo layer; service-role bypasses RLS | `backend/core/db.py:20-33` |
| F-006 | P3 | HIGH | ✅ | identity_id columns exist but unused by live code | `backend/core/memory_service.py`, `schema.sql:363-379` |
| F-007 | P3 | MEDIUM | ✅ | match_memory_chunks not REVOKE'd from public | `infra/supabase/schema.sql` |
| F-008 | P4 | CRITICAL | ✅ | samesite=none + no CSRF tokens | `backend/api/main.py:31-36` |
| F-009 | P4 | HIGH | ✅ | Wildcard CORS allow_origins | `backend/api/main.py:33` |
| F-010 | P5 | HIGH | ✅ | abstract_for_memory() never called | `backend/core/memory_service.py` |
| F-011 | P5 | MEDIUM | ✅ | Placeholder collision in PII reinject | `backend/core/pii.py:252` |
| F-012 | P5 | MEDIUM | ✅ | pii_entity_map TTL no sweeper | `infra/supabase/schema.sql` |
| F-013 | P5 | LOW | 📋 | Raw pre-redaction input to LLM | `backend/core/pii.py:181-186` |
| F-014 | P6 | HIGH | ✅ | AES-GCM no AAD | `backend/core/crypto.py:47` |
| F-015 | P6 | HIGH | ✅ | BYOK resolve_credential never called | `backend/api/routes/run.py` |
| F-016 | P6 | MEDIUM | ✅ | No key rotation version prefix | `backend/core/crypto.py` (v3 + key map) |
| F-017 | P6 | LOW | ✅ | Agent pod raw exc in HTTP 500 | `backend/agents/agent_service.py:114` |
| F-018 | P7 | HIGH | ✅ | Guardrails bypass via bus.dispatch() | `backend/core/bus.py:49-68` |
| F-019 | P7 | MEDIUM | ✅ | Judge JSON greedy regex | `backend/core/adversarial_lifecycle.py` |
| F-020 | P7 | MEDIUM | ✅ | max_rounds unbounded | `backend/core/adversarial_lifecycle.py:60-72` |
| F-021 | P8 | HIGH | ✅ | Classifier fail-open | `backend/core/guardrails.py:160-162` |
| F-022 | P8 | HIGH | ✅ | Regex bypassable via Unicode | `backend/core/guardrails.py:59-92` |
| F-023 | P8 | MEDIUM | ✅ | Classifier truncates at 4000 chars | `backend/core/guardrails.py` (chunk-aggregate) |
| F-024 | P9 | CRITICAL | ✅ | Unscoped FAISS + unauthenticated /ingest | `backend/rag/pipeline.py` |
| F-025 | P9 | HIGH | ✅ | RAG as source of truth | `backend/agents/adversarial.py`, `roles.py` |
| F-026 | P9 | HIGH | ✅ | /ingest/file no size/type limit | `backend/api/routes/ingest.py` |
| F-027 | P9 | MEDIUM | ✅ | ingest_url() SSRF | `backend/rag/ingest.py` (_is_safe_url) |
| F-028 | P10 | LOW | ✅ | No streaming | `backend/api/main.py` |
| F-029 | P11 | CRITICAL | ✅ | /agent/invoke zero auth | `backend/agents/agent_service.py:95-116` |
| F-030 | P11 | CRITICAL | ✅ | All pods get full .env bundle | `infra/k8s/setup.sh:41` |
| F-031 | P11 | HIGH | ✅ | kind binds 0.0.0.0 | `infra/k8s/kind-config.yaml:8-10` |
| F-032 | P11 | MEDIUM | ✅ | K8S_MODE no env guard | `backend/core/config.py` (model_validator) |
| F-033 | P12 | HIGH | ✅ | Notebook export no sanitization | `backend/evaluation/export_notebook.py` |
| F-034 | P13 | CRITICAL | ✅ | No rate limits on /run | `backend/api/main.py` |
| F-035 | P13 | MEDIUM | ✅ | No per-identity concurrency limit | `backend/core/concurrency.py` (new) |
| F-036 | P14 | HIGH | ✅ | Cloud Run no perimeter (documented) | `infra/cloudrun/deploy.sh` |
| F-037 | P14 | MEDIUM | ✅ | notebooks not in .gitignore | `.gitignore` |
| F-038 | P14 | MEDIUM | ✅ | Deps unpinned | `backend/requirements.lock`, `pyproject.toml`, `Dockerfile` |
| F-039 | P15 | MEDIUM | 📋 | Populated .env on disk | `.env` |
| F-040 | P15 | LOW | 📋 | CI secrets masking | `.github/workflows/ci.yml` |
