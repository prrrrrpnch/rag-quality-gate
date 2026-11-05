## Regression gate: ✅ PASS

baseline `c2d17cb` (dataset v1.0.0, mock) vs run `95e59e3` (prompt v1, 108 cases)

| Metric | Baseline | Current | Delta | Allowed | Status |
|---|---|---|---|---|---|
| pass_rate | 0.8056 | 0.8056 | 0 | -0.02 | ✅ PASS |
| hallucination_rate | 0 | 0 | 0 | +0.02 | ✅ PASS |
| groundedness_mean | 1 | 1 | 0 | -0.03 | ✅ PASS |
| relevance_mean | 0.7883 | 0.7883 | 0 | -0.05 | ✅ PASS |
| refusal_recall | 0.8261 | 0.8261 | 0 | -0.0 | ✅ PASS |
| over_refusal_rate | 0.0471 | 0.0471 | 0 | +0.05 | ✅ PASS |
| tool_success_rate | 1 | 1 | 0 | -0.0 | ✅ PASS |
| context_recall_mean | 0.8095 | 0.8095 | 0 | -0.05 | ✅ PASS |
| latency_p95_ms | 43.81 | 43.83 | +0.02 | +25% (min 50) | ✅ PASS |
| cost_per_100_queries_usd | 0 | 0 | 0 | +25% (min 0.01) | ✅ PASS |

