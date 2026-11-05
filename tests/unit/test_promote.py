import shutil
import sys
from pathlib import Path

import pytest

from rqg.evals.dataset import load_golden
from rqg.evals.promote import build_case, fetch_interaction, next_case_id, promote
from rqg.observability.logger import InteractionLogger

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture
def golden(tmp_path):
    p = tmp_path / "golden.jsonl"
    shutil.copy(ROOT / "data" / "golden" / "golden_v1.jsonl", p)
    return p


@pytest.fixture
def logged(tmp_path):
    lg = InteractionLogger(tmp_path / "logs")
    rec = lg.log(
        user_input="Does the kettle work with my smart speaker? my email is ravi@example.com",
        answer="Yes, the BrewMate K2 supports smart speakers.",
        trace_id="trace-123",
        model="claude-haiku-5-5",
    )
    return tmp_path / "logs", rec


def test_promote_appends_pending_case_and_bumps_minor(golden, logged):
    log_dir, _ = logged
    rec = fetch_interaction("trace-123", log_dir)
    before = load_golden(golden, include_pending=True)
    case = promote(
        rec,
        golden,
        expected_behavior="refuse",
        expected_answer="I don't know — that isn't covered in the Zephyr Home manuals.",
    )
    after = load_golden(golden, include_pending=True)
    assert len(after.cases) == len(before.cases) + 1
    assert case.id == "pf-001" and case.status == "pending_review"
    assert case.origin == "promoted_from_prod" and case.dataset_version == "1.1.0"
    assert after.version == "1.1.0"
    assert "ravi@example.com" not in case.turns[0] and "[EMAIL]" in case.turns[0]
    assert "trace:trace-123" in case.tags
    # pending cases are excluded from evaluation until approved
    assert "pf-001" not in load_golden(golden).by_id()
    assert next_case_id(golden) == "pf-002"


def test_promote_answer_case_needs_fact(golden, logged):
    _, rec = logged
    with pytest.raises(ValueError):
        promote(rec, golden, expected_behavior="answer", expected_answer="x")
    case = build_case(
        rec,
        golden,
        "answer",
        "No.",
        required_facts=["no wi-fi"],
        expected_sources=["brewmate_k2_manual"],
    )
    assert case["category"] == "single_fact" and case["source_match"] == "any"


def test_missing_trace_and_empty_input(golden, tmp_path, monkeypatch):
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    assert fetch_interaction("nope", tmp_path) is None
    with pytest.raises(ValueError):
        build_case({"user_input_redacted": " "}, golden, "refuse", "x")


def test_cli(golden, logged, capsys):
    import promote_failure

    log_dir, _ = logged
    args = [
        "trace-123",
        "--behavior",
        "refuse",
        "--expected-answer",
        "Not covered.",
        "--log-dir",
        str(log_dir),
        "--golden",
        str(golden),
    ]
    assert promote_failure.main(args) == 0
    assert "appended pf-001" in capsys.readouterr().out
    assert (
        promote_failure.main(["missing", "--log-dir", str(log_dir), "--golden", str(golden)]) == 1
    )
