# Regression-gate demo: the gate fails on a deliberate regression and passes on `main`

```bash
make gate-demo
```

[`scripts/gate_demo.sh`](../scripts/gate_demo.sh) creates a throwaway git worktree of the
current commit, applies [`scripts/demo_regression.patch`](../scripts/demo_regression.patch),
runs the full 108-case eval and the gate there, then runs them on your untouched checkout.
Your working tree is never modified, and the worktree is deleted afterwards. The target
exits 0 only if the gate **fails** on the regression **and passes** on the clean code. CI runs
it on every push and PR, so the gate is checked continuously, not just once.

## The regression

One line of the system prompt (`src/rqg/rag/prompts.py`):

```diff
 Rules:
-1. {GROUNDING_RULE}
+1. Be as helpful as possible and always give the customer an answer.
```

## Real output

Captured on 2026-11-09 from a fresh clone (`make setup && make gate-demo`). The run with the
patch applied is labelled `-dirty`, because its tracked files differ from the commit.

```text
PY=.venv/bin/python bash scripts/gate_demo.sh
== 1/3  creating throwaway worktree at /tmp/rqg-gate-demo.XXXXXX
Preparing worktree (detached HEAD 9455944)
   applied scripts/demo_regression.patch (removes the 'answer ONLY from context' rule):
    src/rqg/rag/prompts.py | 2 +-
    1 file changed, 1 insertion(+), 1 deletion(-)

== 2/3  full eval + gate WITH the regression (expected: FAIL)
## Regression gate: ❌ FAIL — regression detected

baseline `c2d17cb` (dataset v1.0.0, mock) vs run `9455944-dirty` (prompt v1, 108 cases)

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
| latency_p95_ms | 43.81 | 34.55 | -9.26 | +25% (min 50) | ✅ PASS |
| cost_per_100_queries_usd | 0 | 0 | 0 | +25% (min 0.01) | ✅ PASS |

**Newly failing cases (11):** `oos-001`, `oos-003`, `oos-004`, `oos-005`, `oos-006`, `oos-007`, `oos-008`, `oos-009`, `oos-010`, `oos-011`, `oos-015`

   gate exit code with regression: 1

== 3/3  full eval + gate on your checkout (expected: PASS)
## Regression gate: ✅ PASS

baseline `c2d17cb` (dataset v1.0.0, mock) vs run `9455944` (prompt v1, 108 cases)
   gate exit code without regression: 0

GATE DEMO OK: the gate failed on the regression and passed on the clean code.
```

## How to read it

This ran in **mock mode** (no API key was available while the repo was built), so it shows that
the *gate* works. It is not a measurement of a real LLM:

- The mock app model (`rqg.llm.mock.MockSupportLLM`) reads the system prompt. Without the
  grounding rule it deterministically does what an ungrounded model tends to do: it guesses on
  unanswerable questions (`oos-001`, "What is the capital of France?", gets *"Yes, that is
  supported on Zephyr Home products…"*) and adds an uncited generalisation to answers.
- That is why the hallucination rate jumps to ~0.98. The mock appends the uncited sentence to
  almost every answer. A real model would degrade less uniformly, with smaller, noisier deltas,
  which is what the tolerance bands are for (see [non-determinism.md](non-determinism.md)).
- Refusal recall may not drop at all, so the 11 newly failing out-of-scope cases alone would
  fail the gate.

Unit tests pin the pieces: `tests/unit/test_assistant.py::test_degraded_prompt_hallucinates`
and the tolerance maths in `tests/unit/test_gate.py`.
