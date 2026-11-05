import json
import subprocess
import sys
from pathlib import Path

import pytest

from rqg.evals.dataset import (
    GoldenCase,
    append_case,
    bump_minor,
    load_golden,
    smoke_subset,
)

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "data" / "golden" / "golden_v1.jsonl"

MINIMUMS = {
    "single_fact": 25,
    "multi_doc": 12,
    "out_of_scope": 15,
    "conflict": 8,
    "blocked_topic": 8,
    "multi_turn": 15,
    "tool_call": 12,
    "adversarial_phrasing": 8,
}


def test_golden_loads_and_meets_distribution():
    ds = load_golden(GOLDEN)
    assert len(ds.cases) >= 100
    counts = ds.category_counts()
    for cat, n in MINIMUMS.items():
        assert counts.get(cat, 0) >= n, cat


def test_validator_script_passes():
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_golden.py")],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stdout + out.stderr


def _base(**kw):
    d = dict(
        id="zz-001",
        dataset_version="1.0.0",
        category="single_fact",
        turns=["q"],
        expected_answer="a",
        required_facts=["a"],
        expected_behavior="answer",
    )
    d.update(kw)
    return d


@pytest.mark.parametrize(
    "bad",
    [
        {"id": "bad id"},
        {"dataset_version": "v1"},
        {"category": "nope"},
        {"turns": []},
        {"turns": [" "]},
        {"expected_behavior": "tool_call"},  # missing expected_tools
        {"expected_behavior": "refuse"},  # refuse with required facts
        {"required_facts": []},  # answer without facts
        {"category": "multi_turn"},  # single turn
        {"unknown_field": 1},
        {"expected_tools": [{"name": "rm", "args": {}}], "expected_behavior": "tool_call"},
    ],
)
def test_schema_rejects(bad):
    with pytest.raises(ValueError):
        GoldenCase.model_validate(_base(**bad))


def test_duplicate_ids_and_line_numbers(tmp_path):
    p = tmp_path / "g.jsonl"
    p.write_text(json.dumps(_base()) + "\n" + json.dumps(_base()) + "\n")
    with pytest.raises(ValueError, match="duplicate"):
        load_golden(p)
    p.write_text(json.dumps(_base()) + "\n{not json}\n")
    with pytest.raises(ValueError, match=":2:"):
        load_golden(p)


def test_pending_filtered_and_version(tmp_path):
    p = tmp_path / "g.jsonl"
    rows = [_base(), _base(id="zz-002", status="pending_review", dataset_version="1.1.0")]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n\n")
    ds = load_golden(p)
    assert [c.id for c in ds.cases] == ["zz-001"] and ds.version == "1.1.0"
    assert len(load_golden(p, include_pending=True).cases) == 2
    assert ds.approved() == ds.cases and "zz-001" in ds.by_id()


def test_smoke_subset_is_stratified_and_deterministic():
    cases = load_golden(GOLDEN).cases
    s1, s2 = smoke_subset(cases, 25), smoke_subset(list(reversed(cases)), 25)
    assert [c.id for c in s1] == [c.id for c in s2] and len(s1) == 25
    assert len({c.category for c in s1}) == 8


def test_bump_and_append(tmp_path):
    assert bump_minor("1.0.0") == "1.1.0" and bump_minor("2.9.3") == "2.10.0"
    p = tmp_path / "g.jsonl"
    p.write_text("")
    gc = append_case(p, _base())
    assert gc.id == "zz-001" and load_golden(p).cases[0].question == "q"
