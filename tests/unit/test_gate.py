import copy

import pytest

from rqg.evals.gate import (
    DEFAULT_THRESHOLDS,
    IncompatibleBaseline,
    check_metric,
    compare,
    load_thresholds,
    make_baseline,
    render_gate,
)
from rqg.evals.report import compute_kpis


def row(cid, passed=True, behavior="answer", exp="answer", faith=1.0, lat=10.0, cat="single_fact"):
    return {
        "case_id": cid,
        "category": cat,
        "passed": passed,
        "observed_behavior": behavior,
        "expected_behavior": exp,
        "scores": {
            "faithfulness": faith if behavior == "answer" else None,
            "answer_relevancy": 0.8,
            "context_precision_labels": 1.0,
            "context_recall_labels": 1.0,
        },
        "checks": {
            "tools": True,
            "required_facts": passed,
            "behavior": behavior == exp,
            "sources": True,
        },
        "turn_latencies_ms": [lat],
        "cost_usd": 0.0,
        "input_tokens": 10,
        "output_tokens": 5,
    }


def run_of(cases, mode="mock", version="1.0.0", sha="abc"):
    return {
        "meta": {
            "mode": mode,
            "embedding_backend": "onnx",
            "dataset_version": version,
            "git_sha": sha,
            "prompt_version": "v1",
            "n_cases": len(cases),
        },
        "kpis": compute_kpis(cases),
        "per_category": {},
        "cases": cases,
    }


def base_cases():
    return [row(f"c-{i:03d}") for i in range(48)] + [
        row("r-001", behavior="refuse", exp="refuse"),
        row("r-002", behavior="refuse", exp="refuse"),
    ]


def test_identical_run_passes():
    b = make_baseline(run_of(base_cases()))
    res = compare(b, run_of(base_cases()))
    assert res.passed and not res.new_failures
    assert "PASS" in render_gate(res, b, run_of(base_cases()))


def test_refusal_recall_cannot_drop_at_all():
    b = make_baseline(run_of(base_cases()))
    cur = base_cases()
    cur[-1] = row("r-002", passed=False, behavior="answer", exp="refuse")
    res = compare(b, run_of(cur))
    failed = {r.metric for r in res.rows if r.status == "FAIL"}
    assert "refusal_recall" in failed and res.new_failures == ["r-002"]
    assert "FAIL" in render_gate(res, b, run_of(cur))


def test_hallucination_tolerance_edge():
    # 1 unfaithful answer out of 50 = +0.02 exactly -> passes (inclusive); 2 -> fails
    rule = DEFAULT_THRESHOLDS["hallucination_rate"]
    assert check_metric("hallucination_rate", 0.0, 0.02, rule).status == "PASS"
    assert check_metric("hallucination_rate", 0.0, 0.0201, rule).status == "FAIL"
    assert check_metric("hallucination_rate", 0.1, 0.0, rule).status == "PASS"  # improvement


def test_groundedness_tolerance_edge():
    rule = DEFAULT_THRESHOLDS["groundedness_mean"]
    assert check_metric("g", 0.90, 0.87, rule).status == "PASS"
    assert check_metric("g", 0.90, 0.869, rule).status == "FAIL"


def test_latency_relative_with_noise_floor():
    rule = DEFAULT_THRESHOLDS["latency_p95_ms"]
    assert check_metric("l", 1000, 1250, rule).status == "PASS"
    assert check_metric("l", 1000, 1251, rule).status == "FAIL"
    assert check_metric("l", 10, 55, rule).status == "PASS"  # +45 ms below the 50 ms noise floor
    assert check_metric("l", 10, 61, rule).status == "FAIL"


def test_missing_metric_is_skipped():
    assert check_metric("x", None, 0.5, DEFAULT_THRESHOLDS["pass_rate"]).status == "SKIP"


def test_like_for_like_new_cases_not_gated():
    b = make_baseline(run_of(base_cases()))
    cur = [*base_cases(), row("n-001", passed=False, behavior="refuse", exp="answer")]
    res = compare(b, run_of(cur, version="1.1.0"))
    assert res.passed and res.new_cases == ["n-001"] and res.new_case_pass_rate == 0.0
    assert "not gated" in render_gate(res, b, run_of(cur))


def test_fixed_and_missing_reported():
    cases = base_cases()
    cases[0] = row("c-000", passed=False)
    b = make_baseline(run_of(cases))
    assert b["failing_case_ids"] == ["c-000"]
    res = compare(b, run_of(base_cases()[:-1]))
    assert res.fixed == ["c-000"] and res.missing_cases == ["r-002"]


@pytest.mark.parametrize(
    ("field", "value"),
    [("mode", "real"), ("embedding_backend", "hashing"), ("dataset_version", "2.0.0")],
)
def test_incompatible(field, value):
    b = make_baseline(run_of(base_cases()))
    r = run_of(base_cases())
    r = copy.deepcopy(r)
    r["meta"][field] = value
    with pytest.raises(IncompatibleBaseline):
        compare(b, r)


def test_threshold_file_loading(tmp_path):
    assert load_thresholds(None) == DEFAULT_THRESHOLDS
    p = tmp_path / "t.json"
    p.write_text('{"pass_rate": {"direction": "higher", "max_regression": 0.5}}')
    assert load_thresholds(p)["pass_rate"]["max_regression"] == 0.5
