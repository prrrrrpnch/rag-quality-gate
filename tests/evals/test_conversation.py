"""Multi-turn cases: follow-ups resolve against session history."""

import pytest
from _helpers import assert_case

from conftest import golden_params, run_turns


@pytest.mark.eval
@pytest.mark.parametrize("case", golden_params({"multi_turn"}))
def test_conversation_case(case, eval_assistant, doc_ids, judge):
    turns = run_turns(eval_assistant, case)
    assert len(turns) == len(case.turns)
    if judge is not None:  # real mode: conversational DeepEval metrics on the whole dialogue
        from deepeval import assert_test

        from rqg.evals.metrics_deepeval import (
            real_conversational_metrics,
            to_conversational_test_case,
        )

        assert_test(
            to_conversational_test_case(case, turns),
            real_conversational_metrics(judge),
            run_async=False,
        )
    assert_case(case, turns, doc_ids, judge)
