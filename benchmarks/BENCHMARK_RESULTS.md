# F.A.B.L.E. — 60 Preliminary Eval Test Cases: Results

**Suite version:** v1  |  **Generated:** DRY-RUN

| Dimension | Value |
|-----------|-------|
| Total cases | 60 |
| Finished (Phase-14) | 10 |
| Pending standard | 20 |
| Pending adversarial | 20 |
| Pending Monte Carlo | 10 |

> **Dataset feasibility:** With n=20 prompts per mode, confidence intervals
> are wide (~±15% at 95% CI via bootstrap). McNemar tests require paired
> samples (identical prompts in both modes ✓). Results should be read as
> directional signal, not statistically powered conclusions.
> See `scripts/benchmark/stats.py` for bootstrap CI and McNemar utilities.

---

## Finished Runs — Phase 14 (10 runs, 2026-06-13)

| Run | Category | Mode | Verdict | Score | Rounds | Latency | Cost |
|-----|----------|------|---------|-------|--------|---------|------|
| S1 | code | standard | PASS | 87% | — | 39.9s | — |
| S2 | reasoning | standard | PASS | 90% | — | 22.0s | — |
| S3 | factual | standard | PASS | 92% | — | 45.2s | — |
| S4 | factual | standard | PASS | 82% | — | 29.0s | — |
| S5 | writing | standard | WARN | 60% | — | 27.7s | — |
| A1 | code | adversarial | ACCEPT | 85% | 2/2 | 78.9s | — |
| A2 | reasoning | adversarial | ACCEPT | 85% | 2/2 | 61.6s | — |
| A3 | factual | adversarial | ACCEPT | 75% | 2/2 | 90.6s | — |
| A4 | factual | adversarial | ACCEPT | 75% | 2/2 | 68.1s | — |
| A5 | writing | adversarial | ACCEPT | 82% | 2/2 | 62.4s | — |

**Standard aggregate (Phase-14):** mean score 82% · mean time 32.8s · pass rate 4/5
**Adversarial aggregate (Phase-14):** mean score 80% · mean time 72.3s · accept rate 5/5

---

## Standard Mode — 20 Runs

| # | ID | Category | Verdict | Score | Latency | Cost | Rationale |
|---|-----|----------|---------|-------|---------|------|-----------|
| 1 | C1 | code | PENDING | — | — | — | — |
| 2 | C2 | code | PENDING | — | — | — | — |
| 3 | C3 | code | PENDING | — | — | — | — |
| 4 | C4 | code | PENDING | — | — | — | — |
| 5 | R1 | reasoning | PENDING | — | — | — | — |
| 6 | R2 | reasoning | PENDING | — | — | — | — |
| 7 | R3 | reasoning | PENDING | — | — | — | — |
| 8 | R4 | reasoning | PENDING | — | — | — | — |
| 9 | F1 | factual | PENDING | — | — | — | — |
| 10 | F2 | factual | PENDING | — | — | — | — |
| 11 | F3 | factual | PENDING | — | — | — | — |
| 12 | F4 | factual | PENDING | — | — | — | — |
| 13 | D1 | docqa | PENDING | — | — | — | — |
| 14 | D2 | docqa | PENDING | — | — | — | — |
| 15 | D3 | docqa | PENDING | — | — | — | — |
| 16 | D4 | docqa | PENDING | — | — | — | — |
| 17 | W1 | writing | PENDING | — | — | — | — |
| 18 | W2 | writing | PENDING | — | — | — | — |
| 19 | W3 | writing | PENDING | — | — | — | — |
| 20 | W4 | writing | PENDING | — | — | — | — |

---

## Adversarial Mode — 20 Runs

| # | ID | Category | Verdict | Score | Rounds | Latency | Cost | Rationale |
|---|-----|----------|---------|-------|--------|---------|------|-----------|
| 1 | C1 | code | PENDING | — | — | — | — | — |
| 2 | C2 | code | PENDING | — | — | — | — | — |
| 3 | C3 | code | PENDING | — | — | — | — | — |
| 4 | C4 | code | PENDING | — | — | — | — | — |
| 5 | R1 | reasoning | PENDING | — | — | — | — | — |
| 6 | R2 | reasoning | PENDING | — | — | — | — | — |
| 7 | R3 | reasoning | PENDING | — | — | — | — | — |
| 8 | R4 | reasoning | PENDING | — | — | — | — | — |
| 9 | F1 | factual | PENDING | — | — | — | — | — |
| 10 | F2 | factual | PENDING | — | — | — | — | — |
| 11 | F3 | factual | PENDING | — | — | — | — | — |
| 12 | F4 | factual | PENDING | — | — | — | — | — |
| 13 | D1 | docqa | PENDING | — | — | — | — | — |
| 14 | D2 | docqa | PENDING | — | — | — | — | — |
| 15 | D3 | docqa | PENDING | — | — | — | — | — |
| 16 | D4 | docqa | PENDING | — | — | — | — | — |
| 17 | W1 | writing | PENDING | — | — | — | — | — |
| 18 | W2 | writing | PENDING | — | — | — | — | — |
| 19 | W3 | writing | PENDING | — | — | — | — | — |
| 20 | W4 | writing | PENDING | — | — | — | — | — |

---

## Monte Carlo Mode — 10 Runs

| # | ID | Category | Consensus | Div. Pairs | Latency | Cost | Models |
|---|-----|----------|-----------|------------|---------|------|--------|
| 1 | MC-C2 | code | PENDING | — | — | — | — |
| 2 | MC-C3 | code | PENDING | — | — | — | — |
| 3 | MC-R2 | reasoning | PENDING | — | — | — | — |
| 4 | MC-R3 | reasoning | PENDING | — | — | — | — |
| 5 | MC-F3 | factual | PENDING | — | — | — | — |
| 6 | MC-F4 | factual | PENDING | — | — | — | — |
| 7 | MC-D1 | docqa | PENDING | — | — | — | — |
| 8 | MC-D3 | docqa | PENDING | — | — | — | — |
| 9 | MC-W2 | writing | PENDING | — | — | — | — |
| 10 | MC-W3 | writing | PENDING | — | — | — | — |

---

## Token Cost Analysis

Cost computed via `backend/core/cost.py` using per-model USD/1M token rates.

| Mode | Est. input tokens/run | Est. output tokens/run | Est. cost/run |
|------|-----------------------|------------------------|---------------|
| Standard    | ~2,000 | ~500 | ~$0.003 |
| Adversarial | ~8,000 | ~2,000 | ~$0.030 |
| Monte Carlo | ~12,000 | ~3,000 | ~$0.045 |

> Estimates based on Phase-14 run logs. Actual cost logged per run by the runner.

---

*Generated by `scripts/benchmark_v1.py`. Source: `benchmarks/benchmark_v1.yaml`. Raw JSON in `data/benchmarks/results/`.*