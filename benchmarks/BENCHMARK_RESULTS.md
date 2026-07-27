# F.A.B.L.E. — 60 Preliminary Eval Test Cases: Results

**Suite version:** v1  |  **Generated:** 2026-07-26 13:00 UTC

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

## Finished Runs — Phase 14 (10 runs, 2026-06-13) — LEGACY PROMPT SET

> **Not comparable to the tables above.** These ran against the *original* v1
> prompts, which were rewritten on 2026-07-26 to be discriminative (interacting
> constraints, planted false premises, corpus-grounded docqa). Different prompts
> means different difficulty, so these scores must never be pooled with, or
> trended against, the current suite. Retained only as a record of the
> Phase-14 latency debugging batch.

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

**Standard aggregate (Phase-14, legacy prompts):** mean score 82% · mean time 32.8s · pass rate 4/5
**Adversarial aggregate (Phase-14, legacy prompts):** mean score 80% · mean time 72.3s · accept rate 5/5

---

## Standard Mode — 20 Runs

| # | ID | Category | Verdict | Score | Latency | Cost | Rationale |
|---|-----|----------|---------|-------|---------|------|-----------|
| 1 | C1 | code | PASS | 75% | 81.8s | $0.0000 | Strong performance: 75% across all rubric dimensions. Best on coverage. |
| 2 | C2 | code | PASS | 90% | 95.1s | $0.0000 | Strong performance: 90% across all rubric dimensions. Best on coverage. |
| 3 | C3 | code | PASS | 86% | 93.5s | $0.0000 | Strong performance: 86% across all rubric dimensions. Best on actionability. |
| 4 | C4 | code | PASS | 88% | 93.3s | $0.0000 | Strong performance: 88% across all rubric dimensions. Best on accuracy. |
| 5 | R1 | reasoning | PASS | 95% | 94.0s | $0.0000 | Strong performance: 95% across all rubric dimensions. Best on accuracy. |
| 6 | R2 | reasoning | PASS | 97% | 93.9s | $0.0000 | Strong performance: 97% across all rubric dimensions. Best on coverage. |
| 7 | R3 | reasoning | PASS | 90% | 79.5s | $0.0000 | Strong performance: 90% across all rubric dimensions. Best on accuracy. |
| 8 | R4 | reasoning | PASS | 91% | 88.2s | $0.0000 | Strong performance: 91% across all rubric dimensions. Best on coverage. |
| 9 | F1 | factual | PASS | 88% | 107.6s | $0.0000 | Strong performance: 88% across all rubric dimensions. Best on coverage. |
| 10 | F2 | factual | PASS | 93% | 113.3s | $0.0000 | Strong performance: 93% across all rubric dimensions. Best on coverage. |
| 11 | F3 | factual | PASS | 90% | 105.2s | $0.0000 | Strong performance: 90% across all rubric dimensions. Best on accuracy. |
| 12 | F4 | factual | PASS | 93% | 118.3s | $0.0000 | Strong performance: 93% across all rubric dimensions. Best on depth. |
| 13 | D1 | docqa | WARN | 74% | 73.7s | $0.0000 | Strong performance: 74% across all rubric dimensions. Best on clarity. |
| 14 | D2 | docqa | PASS | 87% | 89.5s | $0.0000 | Strong performance: 87% across all rubric dimensions. Best on clarity. |
| 15 | D3 | docqa | PASS | 80% | 63.0s | $0.0000 | Strong performance: 80% across all rubric dimensions. Best on clarity. |
| 16 | D4 | docqa | PASS | 88% | 78.6s | $0.0000 | Strong performance: 88% across all rubric dimensions. Best on accuracy. |
| 17 | W1 | writing | PASS | 83% | 87.0s | $0.0000 | Strong performance: 83% across all rubric dimensions. Best on clarity. |
| 18 | W2 | writing | PASS | 83% | 58.2s | $0.0000 | Strong performance: 83% across all rubric dimensions. Best on clarity. |
| 19 | W3 | writing | PASS | 82% | 50.4s | $0.0000 | Strong performance: 82% across all rubric dimensions. Best on clarity. |
| 20 | W4 | writing | PASS | 92% | 99.7s | $0.0000 | Strong performance: 92% across all rubric dimensions. Best on depth. |

---

## Adversarial Mode — 20 Runs

| # | ID | Category | Verdict | Score | Rounds | Latency | Cost | Rationale |
|---|-----|----------|---------|-------|--------|---------|------|-----------|
| 1 | C1 | code | ACCEPT | 65% | 2/2 | 102.2s | $0.0000 | The solution contains a critical flaw that violates the O(n) time complexity requirement by using bu |
| 2 | C2 | code | ACCEPT | 75% | 2/2 | 118.2s | $0.0000 | The Actor provides a working thread-safe singleton implementation with double-checked locking and co |
| 3 | C3 | code | ACCEPT | 75% | 2/2 | 125.5s | $0.0000 | While the Actor's implementation demonstrates understanding of the core requirements and provides a  |
| 4 | C4 | code | ACCEPT | 75% | 2/2 | 125.6s | $0.0000 | While the Actor's implementation contains critical logic errors in duplicate-skipping and same-numbe |
| 5 | R1 | reasoning | ACCEPT | 85% | 2/2 | 106.2s | $0.0000 | The Actor's calculations are mathematically correct and comprehensive. The critical issues identifie |
| 6 | R2 | reasoning | ACCEPT | 85% | 2/2 | 101.1s | $0.0000 | The Actor's response correctly computes precision (0.20) and recall (0.75), properly constructs the  |
| 7 | R3 | reasoning | ACCEPT | 92% | 2/2 | 122.8s | $0.0000 | The Actor's calculations are mathematically correct and all final answers match the required precisi |
| 8 | R4 | reasoning | ACCEPT | 82% | 2/2 | 118.5s | $0.0000 | The Actor provides mathematically correct calculations for total return (-25%), CAGR (-13.40%), and  |
| 9 | F1 | factual | ACCEPT | 72% | 2/2 | 117.5s | $0.0000 | While the response contains several unsourced claims and methodological issues identified by the Cri |
| 10 | F2 | factual | ACCEPT | 72% | 2/2 | 117.7s | $0.0000 | While the Actor's response contains critical factual errors regarding Roth contribution withdrawal r |
| 11 | F3 | factual | ACCEPT | 72% | 2/2 | 124.5s | $0.0000 | While the response contains significant conceptual issues (incorrect separation of class imbalance f |
| 12 | F4 | factual | ACCEPT | 82% | 2/2 | 136.1s | $0.0000 | The Actor provides a comprehensive TLS 1.3 handshake explanation covering all required elements. Whi |
| 13 | D1 | docqa | ACCEPT | 35% | 2/2 | 117.1s | $0.0000 | The Actor's response contains pervasive critical flaws including fabricated examples across all risk |
| 14 | D2 | docqa | ACCEPT | 72% | 2/2 | 103.5s | $0.0000 | While the Actor's response contains substantive content addressing all required components, critical |
| 15 | D3 | docqa | ACCEPT | 45% | 2/2 | 90.7s | $0.0000 | The Actor's response contains multiple critical fabrications unsupported by reference material, incl |
| 16 | D4 | docqa | ACCEPT | 45% | 2/2 | 129.1s | $0.0000 | While the Actor's response demonstrates fundamental understanding of nearest-neighbor search concept |
| 17 | W1 | writing | ACCEPT | 72% | 2/2 | 123.9s | $0.0000 | While the Actor's response contains critical methodological flaws (fabricated domain/trademark verif |
| 18 | W2 | writing | ACCEPT | 65% | 2/2 | 106.1s | $0.0000 | While the response violates the word count constraint (156 vs 150 words) and contains several major  |
| 19 | W3 | writing | ACCEPT | 65% | 2/2 | 95.9s | $0.0000 | While the Actor's response has Critical flaws (incorrect word count of 133 vs. 150, vague failure sc |
| 20 | W4 | writing | ACCEPT | 82% | 2/2 | 134.2s | $0.0000 | The Actor's response demonstrates substantial effort in creating three distinct register-specific pr |

---

## Monte Carlo Mode — 10 Runs

| # | ID | Category | Consensus | Div. Pairs | Latency | Cost | Models |
|---|-----|----------|-----------|------------|---------|------|--------|
| 1 | MC-C2 | code | 0.927 | 0 | 27.4s | $0.0000 | claude-sonnet-4-5+gpt-4o+claude-3.5-haiku |
| 2 | MC-C3 | code | 0.942 | 0 | 30.9s | $0.0000 | claude-sonnet-4-5+gpt-4o+claude-3.5-haiku |
| 3 | MC-R2 | reasoning | 0.891 | 0 | 27.3s | $0.0000 | claude-sonnet-4-5+gpt-4o+claude-3.5-haiku |
| 4 | MC-R3 | reasoning | 0.863 | 0 | 28.7s | $0.0000 | claude-sonnet-4-5+gpt-4o+claude-3.5-haiku |
| 5 | MC-F3 | factual | 0.881 | 0 | 27.4s | $0.0000 | claude-sonnet-4-5+gpt-4o+claude-3.5-haiku |
| 6 | MC-F4 | factual | 0.918 | 0 | 49.1s | $0.0000 | claude-sonnet-4-5+gpt-4o+claude-3.5-haiku |
| 7 | MC-D1 | docqa | 0.889 | 0 | 27.8s | $0.0000 | claude-sonnet-4-5+gpt-4o+claude-3.5-haiku |
| 8 | MC-D3 | docqa | 0.889 | 0 | 21.7s | $0.0000 | claude-sonnet-4-5+gpt-4o+claude-3.5-haiku |
| 9 | MC-W2 | writing | 0.881 | 0 | 21.6s | $0.0000 | claude-sonnet-4-5+gpt-4o+claude-3.5-haiku |
| 10 | MC-W3 | writing | 0.926 | 0 | 12.8s | $0.0000 | claude-sonnet-4-5+gpt-4o+claude-3.5-haiku |

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