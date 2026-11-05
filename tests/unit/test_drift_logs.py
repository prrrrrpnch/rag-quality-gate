import json
import math
import random
import sys
from datetime import date
from pathlib import Path

from rqg.observability.drift import (
    compare_windows,
    overall_status,
    psi,
    psi_status,
    rate_status,
    render_drift,
    runs_to_rows,
    split_by_date,
    two_proportion_p,
)
from rqg.observability.logger import InteractionLogger, find_log_record, read_logs

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


def test_psi_identical_is_zero_and_shift_is_large():
    rnd = random.Random(0)
    a = [rnd.gauss(0, 1) for _ in range(2000)]
    b = [rnd.gauss(0, 1) for _ in range(2000)]
    c = [rnd.gauss(1.5, 1) for _ in range(2000)]
    assert psi(a, a) < 1e-9
    assert psi(a, b) < 0.1 and psi_status(psi(a, b)) == "OK"
    assert psi(a, c) > 0.25 and psi_status(psi(a, c)) == "ALERT"
    assert psi_status(0.15) == "WARN"
    assert math.isnan(psi([], [1.0])) and psi_status(float("nan")) == "OK"
    assert psi([1.0] * 5, [1.0] * 5) == 0.0 and psi([1.0] * 5, [2.0] * 5) == float("inf")


def test_two_proportion():
    assert two_proportion_p(10, 100, 10, 100) == 1.0
    assert two_proportion_p(10, 1000, 100, 1000) < 1e-6
    assert two_proportion_p(0, 0, 1, 1) == 1.0 and two_proportion_p(0, 10, 0, 10) == 1.0
    assert rate_status(0.02, 0.001) == "OK"
    assert rate_status(0.04, 0.001) == "WARN" and rate_status(-0.07, 0.001) == "ALERT"
    assert rate_status(0.2, 0.5) == "OK"


def _rows(n, lat_mu, refusal, seed):
    rnd = random.Random(seed)
    return [
        {
            "latency_ms": rnd.lognormvariate(lat_mu, 0.3),
            "cost_usd": 0.001,
            "refused": rnd.random() < refusal,
            "guardrail_flags": [],
            "eval_scores": {"faithfulness": rnd.gauss(0.9, 0.05), "retrieval_hit": True},
        }
        for _ in range(n)
    ]


def test_compare_windows_flags_latency_and_refusals():
    rows = compare_windows(_rows(500, 7.0, 0.05, 1), _rows(500, 7.5, 0.15, 2))
    by = {r.metric: r for r in rows}
    assert by["latency_ms"].status == "ALERT" and by["refusal_rate"].status == "ALERT"
    assert by["cost_usd"].status == "OK"
    assert by["answer_relevancy"].statistic.startswith("n=0")
    assert overall_status(rows) == "ALERT" and "🔴" in render_drift(rows, "t")
    assert overall_status(compare_windows(_rows(500, 7.0, 0.05, 1), _rows(500, 7.0, 0.05, 3))) in {
        "OK",
        "WARN",
    }
    assert overall_status([]) == "OK"
    empty = compare_windows([], [])
    assert all(r.status == "OK" for r in empty)


def test_split_and_runs_to_rows():
    rows = [{"ts": "2026-10-15T01:00:00+00:00"}, {"ts": "2026-10-28T01:00:00+00:00"}]
    a, b = split_by_date(
        rows, (date(2026, 10, 15), date(2026, 10, 16)), (date(2026, 10, 27), date(2026, 10, 28))
    )
    assert len(a) == 1 and len(b) == 1
    run = {
        "cases": [
            {
                "turn_latencies_ms": [5.0],
                "cost_usd": 0.0,
                "observed_behavior": "refuse",
                "scores": {"faithfulness": None, "context_precision_labels": 0.0},
            }
        ]
    }
    r = runs_to_rows(run)[0]
    assert r["refused"] and r["eval_scores"]["retrieval_hit"] is False


def test_synthetic_generator_and_drift_script(tmp_path):
    import drift_report
    import generate_synthetic_logs as g

    out = tmp_path / "syn"
    assert g.generate(out, n_rows=600, seed=42) == 600
    rows = read_logs(out)
    assert len(rows) == 600 and all(r["synthetic"] for r in rows)
    leaks = [r for r in rows if "@example" in r["answer_redacted"] or "98" in r["answer_redacted"]]
    assert len(leaks) >= 5
    rc = drift_report.main(["--log-dir", str(out), "--out", str(tmp_path / "drift.md")])
    assert rc == 3 and "SYNTHETIC" in (tmp_path / "drift.md").read_text()


def test_drift_script_on_runs(tmp_path):
    import drift_report

    run = {
        "cases": [
            {
                "turn_latencies_ms": [5.0],
                "cost_usd": 0.0,
                "observed_behavior": "answer",
                "scores": {
                    "faithfulness": 1.0,
                    "answer_relevancy": 0.9,
                    "context_precision_labels": 1.0,
                },
            }
        ]
        * 30
    }
    p = tmp_path / "a.json"
    p.write_text(json.dumps(run))
    assert drift_report.main(["--runs", str(p), str(p), "--out", str(tmp_path / "d.md")]) == 0


def test_logger_partitions_and_lookup(tmp_path):
    lg = InteractionLogger(tmp_path)
    rec = lg.log(
        user_input="call me 9876543210", answer="ok a@b.com", trace_id="t1", synthetic=False
    )
    assert (
        rec["user_input_redacted"] == "call me [PHONE]" and rec["answer_redacted"] == "ok [EMAIL]"
    )
    assert list(tmp_path.glob("dt=*/interactions.jsonl"))
    assert (
        find_log_record(tmp_path, "t1")["trace_id"] == "t1"
        and find_log_record(tmp_path, "x") is None
    )
    off = InteractionLogger(tmp_path / "off", enabled=False)
    off.log(user_input="x", answer="y")
    assert not (tmp_path / "off").exists()
