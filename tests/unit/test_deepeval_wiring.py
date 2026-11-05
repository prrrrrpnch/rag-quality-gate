"""Proves the real-mode DeepEval path (ClaudeJudge -> DeepEval metric) works end to end,
using a fake LLM that returns schema-valid JSON. No network, no key.

This checks *plumbing*, not judge quality: the scores are whatever the fake returns.
"""

import json
import re

from deepeval.test_case import LLMTestCase

from rqg.evals.metrics_deepeval import (
    ClaudeJudge,
    real_conversational_metrics,
    real_single_turn_metrics,
    real_tool_metrics,
    refusal_geval,
)
from rqg.llm.base import LLMClient, LLMResponse


def _fill(schema: dict, defs: dict) -> object:
    if "$ref" in schema:
        return _fill(defs[schema["$ref"].split("/")[-1]], defs)
    if "anyOf" in schema:
        return _fill(next(s for s in schema["anyOf"] if s.get("type") != "null"), defs)
    if "enum" in schema:
        return schema["enum"][0]
    t = schema.get("type")
    if t == "object":
        return {k: _fill(v, defs) for k, v in schema.get("properties", {}).items()}
    if t == "array":
        return [_fill(schema.get("items", {"type": "string"}), defs)]
    if t == "integer":
        return 8
    if t == "number":
        return 0.8
    if t == "boolean":
        return True
    return "yes"


class SchemaFillingLLM(LLMClient):
    """Returns a minimal JSON instance of whatever schema the judge prompt asks for."""

    model = "fake-judge"

    def __init__(self):
        self.prompts = []

    def complete(self, system, messages, tools=None, max_tokens=1024):
        prompt = messages[-1]["content"]
        self.prompts.append(prompt)
        m = re.search(r"JSON schema, no prose:\n(\{.*\})\s*$", prompt, re.DOTALL)
        if not m:
            return LLMResponse(text="yes")
        schema = json.loads(m.group(1))
        return LLMResponse(text=json.dumps(_fill(schema, schema.get("$defs", {}))))


def test_faithfulness_and_geval_run_through_claude_judge():
    llm = SchemaFillingLLM()
    judge = ClaudeJudge(llm)
    assert judge.get_model_name() == "fake-judge" and judge.load_model() is llm
    tc = LLMTestCase(
        input="What is the filter life of the AeroPure 500?",
        actual_output="About 8 months. [ap500_specs]",
        expected_output="About 8 months.",
        retrieval_context=["AeroPure 500 filter life: about 8 months."],
        context=["AeroPure 500 filter life: about 8 months."],
    )
    metrics = real_single_turn_metrics(judge)
    names = {m.__name__ for m in metrics}
    assert {"Faithfulness", "Answer Relevancy", "Hallucination"} <= names
    faith = metrics[0]
    score = faith.measure(tc)
    assert 0.0 <= score <= 1.0 and faith.error is None
    assert judge.calls >= 2 and llm.prompts  # truths/claims/verdicts went through our judge
    g = refusal_geval(judge)
    assert 0.0 <= g.measure(tc) <= 1.0


def test_other_real_metric_factories_construct():
    judge = ClaudeJudge(SchemaFillingLLM())
    assert real_tool_metrics(judge)[0].threshold == 1.0
    assert len(real_conversational_metrics(judge)) == 2
