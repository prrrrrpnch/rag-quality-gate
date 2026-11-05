"""Single-turn RAG cases: facts, comparisons, refusals, conflicts, blocked topics, phrasing."""

import pytest
from _helpers import assert_case

from conftest import golden_params, run_turns

CATS = {
    "single_fact",
    "multi_doc",
    "out_of_scope",
    "conflict",
    "blocked_topic",
    "adversarial_phrasing",
}


@pytest.mark.eval
@pytest.mark.parametrize("case", golden_params(CATS))
def test_rag_case(case, eval_assistant, doc_ids, judge):
    assert_case(case, run_turns(eval_assistant, case), doc_ids, judge)
