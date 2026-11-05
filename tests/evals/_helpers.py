"""Shared assertion helper for the eval suites."""

from __future__ import annotations

from deepeval import assert_test
from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric

from rqg.config import get_settings
from rqg.evals.checks import check_case
from rqg.evals.metrics_deepeval import (
    DeterministicChecksMetric,
    HeuristicFaithfulnessMetric,
    to_llm_test_case,
)


def assert_case(case, turns, doc_ids, judge, extra_metrics=()):
    s = get_settings()
    r = turns[-1]
    result = check_case(case, r, doc_ids, s.latency_budget_ms)
    metrics = [DeterministicChecksMetric(result)]
    if result.observed_behavior == "answer":
        if judge is None:
            metrics.append(HeuristicFaithfulnessMetric(threshold=0.7))
        else:
            metrics += [
                FaithfulnessMetric(model=judge, threshold=0.7, async_mode=False),
                AnswerRelevancyMetric(model=judge, threshold=0.7, async_mode=False),
            ]
    metrics += list(extra_metrics)
    assert_test(to_llm_test_case(case, r), metrics, run_async=False)
