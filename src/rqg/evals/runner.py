"""Run the golden dataset through the assistant and score every case.

Mock mode: heuristic judge (deterministic, run once) + Ragas non-LLM metric.
Real mode: DeepEval LLM metrics and Ragas LLM metrics via the Claude judge. Every
LLM-judged metric is sampled ``JUDGE_REPEATS`` times and the median is kept; each repeat
has its own cache namespace, so re-running replays the same samples instead of paying again.
"""

from __future__ import annotations

import importlib.metadata as md
import json
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rqg.config import Settings, get_settings, git_sha
from rqg.evals.checks import check_case
from rqg.evals.dataset import GoldenCase, load_golden, smoke_subset
from rqg.evals.judge import HeuristicJudge
from rqg.evals.metrics_ragas import RagasScorer
from rqg.rag.assistant import AssistantResponse, SupportAssistant, build_assistant
from rqg.rag.ingest import load_corpus
from rqg.rag.prompts import PROMPT_VERSION

LIBS = ("deepeval", "ragas", "chromadb", "anthropic", "langsmith", "duckdb", "pydantic")
PROMPTFOO_VERSION = "0.125.1"


def library_versions() -> dict[str, str]:
    out = {}
    for lib in LIBS:
        try:
            out[lib] = md.version(lib)
        except md.PackageNotFoundError:
            out[lib] = "not-installed"
    out["promptfoo"] = PROMPTFOO_VERSION
    return out


@dataclass
class CaseResult:
    """Per-case evaluation record (serialised into the run JSON)."""

    case_id: str
    category: str
    tags: list[str]
    expected_behavior: str
    observed_behavior: str
    passed: bool
    checks: dict[str, Any]
    scores: dict[str, float | None]
    question: str
    answer: str
    turn_answers: list[str]
    retrieved_doc_ids: list[str]
    cited_sources: list[str]
    tools_called: list[dict[str, Any]]
    turn_latencies_ms: list[float]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    trace_ids: list[str] = field(default_factory=list)
    guardrail_flags: list[str] = field(default_factory=list)


class Scorer:
    """Produces the score dict for one case (mode-dependent)."""

    def __init__(self, settings: Settings, assistant: SupportAssistant) -> None:
        self.settings = settings
        self.heuristic = HeuristicJudge()
        self.ragas = RagasScorer.for_settings(
            settings, getattr(assistant.retriever, "embedder", None)
        )
        self.titles = {d.doc_id: d.title for d in load_corpus(settings.corpus_dir)}
        self.judges: list[Any] = []
        if not settings.use_mock:
            from rqg.evals.metrics_deepeval import ClaudeJudge
            from rqg.llm.cache import CachedLLM, DiskCache
            from rqg.llm.factory import _real_client

            cache = DiskCache(settings.cache_dir)
            inner = _real_client(settings, settings.judge_model, judge=True)
            self.judges = [
                ClaudeJudge(CachedLLM(inner, cache, namespace=f"judge:r{i}:"))
                for i in range(settings.judge_repeats)
            ]

    @property
    def judge_name(self) -> str:
        return self.heuristic.name if self.settings.use_mock else self.settings.judge_model

    def score(
        self, case: GoldenCase, r: AssistantResponse, turns: list[AssistantResponse], obs: str
    ) -> dict[str, float | None]:
        s: dict[str, float | None] = {
            "context_precision_labels": self.heuristic.context_precision(case, r),
            "context_recall_labels": self.heuristic.context_recall(case, r),
        }
        answered = obs == "answer"
        if self.settings.use_mock:
            s["faithfulness"] = (
                self.heuristic.faithfulness(r.answer, r.retrieved_contexts) if answered else None
            )
            s["answer_relevancy"] = (
                self.heuristic.answer_relevancy(
                    case.question, r.answer, [self.titles.get(d, "") for d in r.cited_sources]
                )
                if answered
                else None
            )
        else:
            s.update(self._real_deepeval(case, r, turns, answered))
        ragas = self.ragas.score(
            case.question, r.answer, r.retrieved_contexts or [""], case.expected_answer
        )
        s.update(ragas)
        return s

    def _real_deepeval(
        self, case: GoldenCase, r: AssistantResponse, turns: list[AssistantResponse], answered: bool
    ) -> dict[str, float | None]:
        from rqg.evals.metrics_deepeval import (
            real_conversational_metrics,
            real_single_turn_metrics,
            real_tool_metrics,
            refusal_geval,
            to_conversational_test_case,
            to_llm_test_case,
        )

        tc = to_llm_test_case(case, r)
        names = [
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_recall",
            "hallucination",
            "citation_geval",
        ]
        out: dict[str, float | None] = {}

        def sample(metric_idx: int | None, factory, test_case) -> float | None:
            vals = []
            for judge in self.judges:
                m = factory(judge) if metric_idx is None else factory(judge)[metric_idx]
                try:
                    vals.append(m.measure(test_case))
                except Exception:
                    continue
            return float(statistics.median(vals)) if vals else None

        if answered:
            for i, n in enumerate(names):
                out[n] = sample(i, real_single_turn_metrics, tc)
        if case.expected_behavior == "refuse":
            out["refusal_geval"] = sample(None, refusal_geval, tc)
        if case.expected_tools:
            out["tool_correctness"] = sample(0, real_tool_metrics, tc)
        if len(case.turns) > 1:
            ctc = to_conversational_test_case(case, turns)
            out["knowledge_retention"] = sample(0, real_conversational_metrics, ctc)
            out["conversation_completeness"] = sample(1, real_conversational_metrics, ctc)
        return out


class EvalRunner:
    """Runs cases, scores them and returns a JSON-serialisable run dict."""

    def __init__(self, settings: Settings | None = None, assistant: SupportAssistant | None = None):
        self.settings = settings or get_settings()
        self.assistant = assistant or build_assistant(self.settings)
        self.scorer = Scorer(self.settings, self.assistant)
        self.doc_ids = {d.doc_id for d in load_corpus(self.settings.corpus_dir)}

    def run_case(self, case: GoldenCase) -> CaseResult:
        session = f"eval-{case.id}-{uuid.uuid4().hex[:6]}"
        turns = [self.assistant.ask(t, session_id=session) for t in case.turns]
        self.assistant.reset(session)
        r = turns[-1]
        chk = check_case(case, r, self.doc_ids, self.settings.latency_budget_ms)
        scores = self.scorer.score(case, r, turns, chk.observed_behavior)
        return CaseResult(
            case_id=case.id,
            category=case.category,
            tags=case.tags,
            expected_behavior=case.expected_behavior,
            observed_behavior=chk.observed_behavior,
            passed=chk.passed,
            checks=chk.to_dict(),
            scores=scores,
            question=case.question,
            answer=r.answer,
            turn_answers=[t.answer for t in turns],
            retrieved_doc_ids=r.retrieved_doc_ids,
            cited_sources=r.cited_sources,
            tools_called=[asdict(t) for t in r.tool_calls],
            turn_latencies_ms=[t.latency_ms for t in turns],
            input_tokens=sum(t.input_tokens for t in turns),
            output_tokens=sum(t.output_tokens for t in turns),
            cost_usd=sum(t.cost_usd for t in turns),
            trace_ids=[t.trace_id for t in turns],
            guardrail_flags=sorted({f for t in turns for f in t.guardrail_flags}),
        )

    def run(
        self, cases: list[GoldenCase], dataset_version: str, subset: str = "full"
    ) -> dict[str, Any]:
        from rqg.evals.report import compute_kpis, per_category

        t0 = time.perf_counter()
        workers = 1 if self.settings.use_mock else 4
        with ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(self.run_case, cases))
        results.sort(key=lambda c: c.case_id)
        rows = [asdict(r) for r in results]
        judge_calls = sum(getattr(j, "calls", 0) for j in self.scorer.judges)
        return {
            "meta": {
                "run_id": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6],
                "created_at": datetime.now(UTC).isoformat(),
                "mode": self.settings.mode,
                "subset": subset,
                "n_cases": len(rows),
                "dataset_version": dataset_version,
                "git_sha": git_sha(),
                "prompt_version": PROMPT_VERSION,
                "app_model": self.assistant.llm.model,
                "judge": self.scorer.judge_name,
                "judge_repeats": 1 if self.settings.use_mock else self.settings.judge_repeats,
                "judge_calls": judge_calls,
                "embedding_backend": self.settings.embedding_backend,
                "library_versions": library_versions(),
                "wall_time_s": round(time.perf_counter() - t0, 2),
            },
            "kpis": compute_kpis(rows),
            "per_category": per_category(rows),
            "cases": rows,
        }


def write_run(run: dict[str, Any], reports_dir: Path, name: str = "latest") -> tuple[Path, Path]:
    """Write run JSON + markdown report; also refresh ``<name>.json`` / ``<name>.md``."""
    from rqg.evals.report import render_markdown

    reports_dir = Path(reports_dir)
    (reports_dir / "runs").mkdir(parents=True, exist_ok=True)
    jp = reports_dir / "runs" / f"{run['meta']['run_id']}.json"
    jp.write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")
    md_text = render_markdown(run)
    (reports_dir / f"{name}.json").write_text(
        json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    mp = reports_dir / f"{name}.md"
    mp.write_text(md_text, encoding="utf-8")
    return jp, mp


def run_eval(subset: str = "full", settings: Settings | None = None) -> dict[str, Any]:
    s = settings or get_settings()
    ds = load_golden(s.golden_path)
    cases = smoke_subset(ds.cases, 25) if subset == "smoke" else ds.cases
    return EvalRunner(s).run(cases, ds.version, subset)
