"""Fixtures for golden-dataset eval tests (`deepeval test run tests/evals` or pytest).

* One assistant per session (real ONNX retrieval unless EMBEDDING_BACKEND says otherwise).
* Cases that already fail in the committed baseline are marked xfail (non-strict): the suite
  goes red only on NEW failures; aggregate KPI regressions are the gate's job.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from rqg.config import get_settings
from rqg.evals.dataset import load_golden, smoke_subset

ROOT = Path(__file__).resolve().parents[2]


def _known_failures() -> set[str]:
    s = get_settings()
    name = "baseline.json" if s.use_mock else "baseline.real.json"
    p = ROOT / "baselines" / name
    if not p.exists():
        return set()
    return set(json.loads(p.read_text(encoding="utf-8")).get("failing_case_ids", []))


def golden_params(categories: set[str]):
    ds = load_golden(get_settings().golden_path)
    cases = ds.cases
    if os.getenv("EVAL_SUBSET") == "smoke":
        cases = smoke_subset(cases, 25)
    known = _known_failures()
    out = []
    for c in cases:
        if c.category not in categories:
            continue
        marks = (
            [pytest.mark.xfail(reason="fails in baseline", strict=False)] if c.id in known else []
        )
        out.append(pytest.param(c, id=c.id, marks=marks))
    return out


@pytest.fixture(scope="session")
def eval_assistant():
    from rqg.rag.assistant import build_assistant

    return build_assistant(get_settings())


@pytest.fixture(scope="session")
def doc_ids():
    from rqg.rag.ingest import load_corpus

    return {d.doc_id for d in load_corpus(get_settings().corpus_dir)}


@pytest.fixture(scope="session")
def judge():
    """None in mock mode; a ClaudeJudge in real mode."""
    s = get_settings()
    if s.use_mock:
        return None
    from rqg.evals.metrics_deepeval import ClaudeJudge
    from rqg.llm.factory import build_judge_llm

    return ClaudeJudge(build_judge_llm(s))


def run_turns(assistant, case):
    session = f"pytest-{case.id}"
    turns = [assistant.ask(t, session_id=session) for t in case.turns]
    assistant.reset(session)
    return turns
