"""DeepEval integration.

* ``ClaudeJudge`` adapts any ``LLMClient`` (Anthropic by default) to ``DeepEvalBaseLLM`` so
  DeepEval's LLM metrics use our cached, provider-pluggable judge.
* ``real_*_metrics`` build the LLM-judged DeepEval metrics (real mode).
* ``Heuristic*Metric`` and ``DeterministicChecksMetric`` are DeepEval ``BaseMetric``
  subclasses, so the same ``assert_test`` / ``deepeval test run`` machinery runs offline.

Only metrics that exist in the pinned deepeval==4.3.3 are used.
"""

from __future__ import annotations

import json
import re
from typing import Any

from deepeval.metrics import (
    AnswerRelevancyMetric,
    BaseMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    ConversationCompletenessMetric,
    FaithfulnessMetric,
    GEval,
    HallucinationMetric,
    KnowledgeRetentionMetric,
    ToolCorrectnessMetric,
)
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import ConversationalTestCase, LLMTestCase, SingleTurnParams, ToolCall, Turn

from rqg.evals.checks import CheckResult
from rqg.evals.dataset import GoldenCase
from rqg.evals.judge import HeuristicJudge
from rqg.llm.base import LLMClient
from rqg.rag.assistant import AssistantResponse

_JSON = re.compile(r"\{.*\}", re.DOTALL)


class ClaudeJudge(DeepEvalBaseLLM):
    """DeepEval judge backed by our ``LLMClient`` (cached; Claude Sonnet by default)."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self.calls = 0
        super().__init__(model=llm.model)

    def load_model(self) -> LLMClient:  # type: ignore[override]
        return self.llm

    def generate(self, prompt: str, schema: Any = None, **kwargs: Any) -> Any:  # type: ignore[override]
        self.calls += 1
        if schema is not None:
            fields = json.dumps(schema.model_json_schema())
            prompt = f"{prompt}\n\nReturn ONLY a JSON object matching this JSON schema, no prose:\n{fields}"
        text = self.llm.complete_text(prompt, max_tokens=4096)
        if schema is None:
            return text
        m = _JSON.search(text)
        try:
            return schema.model_validate_json(m.group(0) if m else text)
        except Exception:
            return m.group(0) if m else text  # let DeepEval's own JSON repair try

    async def a_generate(self, prompt: str, schema: Any = None, **kwargs: Any) -> Any:  # type: ignore[override]
        return self.generate(prompt, schema=schema, **kwargs)

    def get_model_name(self) -> str:  # type: ignore[override]
        return self.llm.model


# --------------------------------------------------------------------------- test cases
def to_llm_test_case(case: GoldenCase, r: AssistantResponse) -> LLMTestCase:
    return LLMTestCase(
        input=case.question,
        actual_output=r.answer,
        expected_output=case.expected_answer,
        retrieval_context=r.retrieved_contexts or [""],
        context=r.retrieved_contexts or [""],
        tools_called=[
            ToolCall(name=t.name, input_parameters=t.args, output=t.output) for t in r.tool_calls
        ],
        expected_tools=[
            ToolCall(name=t.name, input_parameters=t.args) for t in case.expected_tools
        ],
        completion_time=r.latency_ms / 1000,
        token_cost=r.cost_usd,
        name=case.id,
        tags=[case.category, *case.tags],
        metadata={"case_id": case.id},
    )


def to_conversational_test_case(
    case: GoldenCase, turns: list[AssistantResponse]
) -> ConversationalTestCase:
    t: list[Turn] = []
    for user, resp in zip(case.turns, turns, strict=True):
        t.append(Turn(role="user", content=user))
        t.append(
            Turn(
                role="assistant",
                content=resp.answer,
                retrieval_context=resp.retrieved_contexts or None,
            )
        )
    return ConversationalTestCase(turns=t, name=case.id, expected_outcome=case.expected_answer)


# --------------------------------------------------------------------------- real metrics
def real_single_turn_metrics(judge: ClaudeJudge, threshold: float = 0.7) -> list[BaseMetric]:
    kw = {"model": judge, "async_mode": False, "threshold": threshold}
    return [
        FaithfulnessMetric(**kw),
        AnswerRelevancyMetric(**kw),
        ContextualPrecisionMetric(**kw),
        ContextualRecallMetric(**kw),
        HallucinationMetric(model=judge, async_mode=False, threshold=0.5),
        GEval(
            name="Citation correctness",
            criteria=(
                "Every factual sentence in the actual output cites a document id in square "
                "brackets, and each cited document actually supports the sentence."
            ),
            evaluation_params=[SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.RETRIEVAL_CONTEXT],
            **kw,
        ),
    ]


def refusal_geval(judge: ClaudeJudge) -> GEval:
    """Soft quality signal for refusals (politeness, offers next step). The refuse/answer
    *decision* itself is gated deterministically, never by this metric."""
    return GEval(
        name="Refusal correctness",
        criteria=(
            "The question cannot be answered from the product manuals or is a blocked topic. "
            "The actual output must decline clearly, must not invent facts, and should offer a "
            "helpful next step such as contacting support."
        ),
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
        model=judge,
        async_mode=False,
        threshold=0.7,
    )


def real_tool_metrics(judge: ClaudeJudge) -> list[BaseMetric]:
    # model must be passed explicitly: without it DeepEval falls back to an OpenAI judge.
    return [ToolCorrectnessMetric(threshold=1.0, async_mode=False, model=judge)]


def real_conversational_metrics(judge: ClaudeJudge) -> list:
    return [
        KnowledgeRetentionMetric(model=judge, async_mode=False, threshold=0.7),
        ConversationCompletenessMetric(model=judge, async_mode=False, threshold=0.7),
    ]


# --------------------------------------------------------------------------- offline metrics
class _OfflineMetric(BaseMetric):
    """Base for deterministic DeepEval metrics (no model, synchronous)."""

    _name = "offline"
    async_mode = False

    def __init__(self, threshold: float = 0.7) -> None:
        self.threshold = threshold
        self.evaluation_model = "deterministic"
        self.include_reason = True
        self.strict_mode = False

    def _score(self, tc: LLMTestCase) -> float | None:  # pragma: no cover - abstract
        raise NotImplementedError

    def measure(self, test_case: LLMTestCase, *args: Any, **kwargs: Any) -> float:
        s = self._score(test_case)
        self.skipped = s is None
        self.score = 1.0 if s is None else s
        self.success = self.score >= self.threshold
        self.reason = "not applicable" if s is None else f"{self._name}={self.score:.2f}"
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args: Any, **kwargs: Any) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return bool(self.success)

    @property
    def __name__(self) -> str:  # type: ignore[override]
        return self._name


class HeuristicFaithfulnessMetric(_OfflineMetric):
    _name = "Heuristic Faithfulness"

    def _score(self, tc: LLMTestCase) -> float | None:
        return HeuristicJudge().faithfulness(
            tc.actual_output or "", list(tc.retrieval_context or [])
        )


class HeuristicAnswerRelevancyMetric(_OfflineMetric):
    _name = "Heuristic Answer Relevancy"

    def _score(self, tc: LLMTestCase) -> float | None:
        return HeuristicJudge().answer_relevancy(tc.input, tc.actual_output or "", [])


class DeterministicChecksMetric(_OfflineMetric):
    """Wraps ``check_case`` results: 1.0 if every applicable hard check passed."""

    _name = "Deterministic Checks"

    def __init__(self, result: CheckResult) -> None:
        super().__init__(threshold=1.0)
        self.result = result

    def _score(self, tc: LLMTestCase) -> float | None:
        return 1.0 if self.result.passed else 0.0

    def measure(self, test_case: LLMTestCase, *args: Any, **kwargs: Any) -> float:
        score = super().measure(test_case)
        failed = [k for k, v in self.result.values().items() if v is False]
        self.reason = "all checks passed" if not failed else f"failed: {', '.join(failed)}"
        return score
