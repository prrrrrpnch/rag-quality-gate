# Regression-gate demo: the gate fails on a deliberate regression and passes on `main`

Everything below is **real output**, captured on 2026-11-05 by running the commands shown.
It ran in **mock mode** (no API key was available while this repo was built), so read it as
evidence that the *gate* works, not as a measurement of a real LLM:

- The mock app model (`rqg.llm.mock.MockSupportLLM`) reads the system prompt. When the grounding
  rule `"Answer ONLY from the provided context…"` is missing, it deterministically does what an
  ungrounded model tends to do: it answers unanswerable questions with a guess, and adds an
  uncited generalisation to answers. Real models degrade less uniformly, so with a real model
  the deltas will be smaller and noisier. That is why the gate uses tolerance bands
  (see [non-determinism.md](non-determinism.md)).
- The hallucination rate of ~0.98 is inflated for the same reason: the mock appends the uncited
  sentence to almost every answer.

## 1. The regression (branch `demo/regression`)

One line of the system prompt changed (`src/rqg/rag/prompts.py`):

```diff
 Rules:
-1. {GROUNDING_RULE}
+1. Be as helpful as possible and always give the customer an answer.
```

## 2. Gate on `demo/regression`: FAIL (exit code 1)

```text
$ git checkout demo/regression && make eval && make gate
## Headline KPIs

| KPI | Value |
|---|---|
| Pass rate (all deterministic checks) | 0.7037 |
| Hallucination rate (1 - faithfulness pass rate) | 0.9767 |
| Groundedness (mean faithfulness) | 0.4884 |
| Answer relevance (mean) | 0.6673 |
| Refusal recall (refused / should refuse) | 0.3478 |
| Refusal precision | 1 |
| Over-refusal rate | 0 |
| Tool success rate | 1 |
| Retrieval hit rate | 0.9583 |
| Context precision (label-based) | 0.8538 |
| Context recall (label-based) | 0.8095 |
| Ragas NonLLMStringSimilarity (mean) | 0.1662 |
| DeepEval vs Ragas faithfulness agreement | n/a |
| Latency p50 (ms) | 35.48 |
| Latency p95 (ms) | 45.84 |
| Cost per 100 queries (USD, app model) | 0 |

## Regression gate: ❌ FAIL — regression detected

baseline `c2d17cb` (dataset v1.0.0, mock) vs run `deebd98` (prompt v1, 108 cases)

| Metric | Baseline | Current | Delta | Allowed | Status |
|---|---|---|---|---|---|
| pass_rate | 0.8056 | 0.7037 | -0.1019 | -0.02 | ❌ FAIL |
| hallucination_rate | 0 | 0.9767 | +0.9767 | +0.02 | ❌ FAIL |
| groundedness_mean | 1 | 0.4884 | -0.5116 | -0.03 | ❌ FAIL |
| relevance_mean | 0.7883 | 0.6673 | -0.121 | -0.05 | ❌ FAIL |
| refusal_recall | 0.8261 | 0.3478 | -0.4783 | -0.0 | ❌ FAIL |
| over_refusal_rate | 0.0471 | 0 | -0.0471 | +0.05 | ✅ PASS |
| tool_success_rate | 1 | 1 | 0 | -0.0 | ✅ PASS |
| context_recall_mean | 0.8095 | 0.8095 | 0 | -0.05 | ✅ PASS |
| latency_p95_ms | 43.81 | 45.84 | +2.03 | +25% (min 50) | ✅ PASS |
| cost_per_100_queries_usd | 0 | 0 | 0 | +25% (min 0.01) | ✅ PASS |

**Newly failing cases (11):** `oos-001`, `oos-003`, `oos-004`, `oos-005`, `oos-006`, `oos-007`, `oos-008`, `oos-009`, `oos-010`, `oos-011`, `oos-015`

demo/regression: compare_to_baseline.py exit=1
```

What one of the newly failing cases looks like (from `reports/latest.md` on the branch):

```text
| oos-001 | out_of_scope | refuse → answer | behavior, citation_format | Yes, that is supported on Zephyr Home products and usually takes about 2 hours. |
| oos-006 | out_of_scope | refuse → answer | behavior, citation_format | Yes, that is supported on Zephyr Home products and usually takes about 2 hours. |
```

The CI job `eval-gate` runs the same `scripts/compare_to_baseline.py` and fails the PR on a
non-zero exit; the gate table is posted as a PR comment.

## 3. Gate on `main`: PASS (exit code 0)

```text
$ git checkout main && make eval && make gate
## Regression gate: ✅ PASS

baseline `c2d17cb` (dataset v1.0.0, mock) vs run `5e71477` (prompt v1, 108 cases)

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
| latency_p95_ms | 43.81 | 44.79 | +0.98 | +25% (min 50) | ✅ PASS |
| cost_per_100_queries_usd | 0 | 0 | 0 | +25% (min 0.01) | ✅ PASS |


exit code: 0
```

## Reproduce

```bash
git checkout demo/regression
make eval gate        # exits non-zero
git checkout main
make eval gate        # exits 0
```

Unit tests also pin this behaviour: `tests/unit/test_assistant.py::test_degraded_prompt_hallucinates`
and the gate maths in `tests/unit/test_gate.py`.
