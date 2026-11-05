# Handling non-determinism

LLM output and LLM-judge scores vary between runs. A gate that fails on noise gets ignored;
a gate that tolerates everything catches nothing. This repo uses six rules.

## 1. Hard assertions are deterministic and never LLM-judged

| Check | How | File |
|---|---|---|
| refuse vs answer vs clarify vs tool decision | refusal/clarify regexes on the answer, tool records | `evals/checks.py` |
| required / forbidden facts | normalised substring match with `a\|b` alternatives | `evals/checks.py` |
| cited sources and citation format | `[doc_id]` parse, ids must exist and be retrieved | `evals/checks.py` |
| correct tool + args | normalised comparison with `expected_tools` | `evals/checks.py` |
| canary leak, PII leak, unauthorised tool call | string match, regex, independent policy re-check | `safety/detectors.py` |

The refusal *decision* is gated with `refusal_recall` (may not drop at all). The GEval
"refusal correctness" metric only grades the *quality* of a refusal and is never the gate.

## 2. LLM-judged metrics are sampled N times and the median is used

`JUDGE_REPEATS` (default 3). Each repeat is a separate `ClaudeJudge` with its own cache
namespace (`judge:r0:`, `judge:r1:`, …), so

- the three samples are independent model calls on the first run, and
- re-running the same code on the same data replays the same three samples from
  `.cache/llm` at no cost. CI caches that directory.

Median, not mean: one bad judge parse (score 0) should not move the case score.

## 3. Tolerance bands, not exact equality

`baselines/thresholds.json`:

| Metric | Direction | Allowed regression |
|---|---|---|
| hallucination_rate | lower is better | +0.02 absolute |
| groundedness_mean | higher | −0.03 |
| relevance_mean | higher | −0.05 |
| refusal_recall | higher | 0 (no drop at all) |
| tool_success_rate | higher | 0 |
| over_refusal_rate | lower | +0.05 |
| pass_rate | higher | −0.02 |
| context_recall_mean | higher | −0.05 |
| latency_p95_ms | lower | +25 % relative, with a 50 ms noise floor |
| cost_per_100_queries_usd | lower | +25 % relative, with a $0.01 floor |

A delta exactly equal to the tolerance passes (tested in `tests/unit/test_gate.py`). The
noise floors exist because a relative band on a tiny number is meaningless: mock-mode p95
is around 45 ms and moves a few ms between runs.

**How to set the bands for real mode:** run the full real eval twice on the same commit,
compute the per-metric delta, and set each tolerance to at least 2× the observed run-to-run
delta. That calibration has **not** been done yet (no API key was available when the repo
was built). The current bands are reasoned defaults.

## 4. Compare like with like

- The gate recomputes current KPIs on the **baseline's case ids only**. New golden cases
  are reported separately ("not gated") until the baseline is rebuilt, so adding a hard
  case cannot fail an unrelated PR.
- Mode, embedding backend and dataset **major** version must match or the gate exits 2.
- Mock and real runs have separate baselines.

## 5. Per-case tests do not flake on known failures

`tests/evals/` marks cases that already fail in the committed baseline as `xfail`
(non-strict). The per-case suite goes red only on new failures, while aggregate KPIs are
the gate's job.

## 6. Temperature

The brief asked for temperature 0. The current Claude models reject sampling parameters
(`temperature`, `top_p`, `top_k`), and `anthropic==2.5.0` no longer exposes them on
`messages.create`. Reproducibility comes from rules 2–5 and the cache instead. The
OpenAI-compatible client still sends `temperature=0` where the provider accepts it.
Effort is set to `low` for both app and judge (`APP_EFFORT`, `JUDGE_EFFORT`) to keep cost
and variance down.

## Judge reliability

When real mode runs, the report includes **DeepEval vs Ragas faithfulness agreement**
(share of answered cases where both judges agree on pass/fail at 0.7). Low agreement means
the faithfulness KPI should not be trusted on its own; investigate disagreements before
tightening thresholds. In mock mode this KPI is `n/a`, because Ragas' LLM metrics need a
judge.
