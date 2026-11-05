"""Tool-calling cases: correct tool + args, slot filling, failure recovery."""

import pytest
from _helpers import assert_case

from conftest import golden_params, run_turns


@pytest.mark.eval
@pytest.mark.parametrize("case", golden_params({"tool_call"}))
def test_tool_case(case, eval_assistant, doc_ids, judge):
    turns = run_turns(eval_assistant, case)
    extra = []
    if judge is not None and case.expected_tools:
        from rqg.evals.metrics_deepeval import real_tool_metrics

        extra = real_tool_metrics(judge)
    for t in turns[-1].tool_calls:  # deterministic: never an unauthorised call
        assert t.authorized, f"unauthorised tool call {t}"
    assert_case(case, turns, doc_ids, judge, extra)
