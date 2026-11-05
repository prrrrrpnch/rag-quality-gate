import sys
from pathlib import Path

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from rqg.data_validation import render_sql
from rqg.data_validation.athena import AthenaQueryError, AthenaRunner
from rqg.data_validation.duckdb_local import LocalSQL
from rqg.data_validation.pii_scan import scan_logs

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):
    import generate_synthetic_logs as g

    leaky = tmp_path_factory.mktemp("leaky")
    clean = tmp_path_factory.mktemp("clean")
    g.generate(leaky, n_rows=800, seed=42, leaks=True)
    g.generate(clean, n_rows=800, seed=42, leaks=False)
    return leaky, clean


def test_pii_check_catches_planted_leaks(synthetic):
    leaky, clean = synthetic
    rows = LocalSQL(leaky).run("pii_leak_check")
    assert len(rows) == 5
    assert {r["pii_kind"] for r in rows} <= {"email", "phone"}
    assert LocalSQL(clean).run("pii_leak_check") == []
    assert len(scan_logs(leaky)) == 5 and scan_logs(clean) == []


def test_data_quality_and_reports(synthetic):
    db = LocalSQL(synthetic[1])
    assert db.run("data_quality_check") == []
    trend = db.run("quality_trend")
    assert len(trend) == 14 and all(0 <= t["refusal_rate"] <= 1 for t in trend)
    lc = db.run("latency_cost")
    assert {r["model"] for r in lc} == {"claude-haiku-5-5", "claude-sonnet-5-5"}
    late = [r["p95_ms"] for r in lc if r["dt"] >= "2026-10-26" and r["model"] == "claude-haiku-5-5"]
    early = [
        r["p95_ms"] for r in lc if r["dt"] <= "2026-10-20" and r["model"] == "claude-haiku-5-5"
    ]
    assert min(late) > max(early) * 0.9  # planted latency regression is visible


def test_data_quality_catches_violations(tmp_path):
    p = tmp_path / "dt=2026-10-01"
    p.mkdir()
    (p / "interactions.jsonl").write_text(
        '{"ts":"2026-10-01T00:00:00+00:00","trace_id":"a","model":"m","latency_ms":-1,"cost_usd":0,"input_tokens":1,"output_tokens":1,"refused":false,"prompt_version":"v1"}\n'
        '{"ts":"2026-10-01T00:00:00+00:00","trace_id":"a","model":"m","latency_ms":1,"cost_usd":0,"input_tokens":1,"output_tokens":1,"refused":false,"prompt_version":"v9"}\n'
    )
    v = {r["violation"] for r in LocalSQL(tmp_path).run("data_quality_check")}
    assert v == {"bad_latency", "unknown_prompt_version", "duplicate_trace_id"}


def test_missing_logs_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        LocalSQL(tmp_path)


def test_render_sql_and_create_table():
    sql = render_sql("create_table", bucket="my-bucket")
    assert "s3://my-bucket/logs/" in sql and "${dt}" in sql and "{{" not in sql
    assert "'2026-01-01'" in render_sql("quality_trend")


def test_run_checks_script(synthetic, tmp_path):
    import run_athena_checks

    leaky, clean = synthetic
    assert (
        run_athena_checks.main(
            ["--log-dir", str(leaky), "--expect-pii", "5", "--out", str(tmp_path / "a.md")]
        )
        == 0
    )
    assert (
        run_athena_checks.main(
            ["--log-dir", str(leaky), "--expect-pii", "0", "--out", str(tmp_path / "b.md")]
        )
        == 1
    )
    assert (
        run_athena_checks.main(
            ["--log-dir", str(clean), "--expect-pii", "0", "--out", str(tmp_path / "c.md")]
        )
        == 0
    )


# ------------------------------------------------------------------- S3 upload (moto)
@mock_aws
def test_upload_logs_to_s3(synthetic):
    import upload_logs_s3

    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="rqg-test")
    keys = upload_logs_s3.upload_logs(synthetic[1], "rqg-test", s3=s3)
    assert len(keys) == 14 and keys[0].startswith("logs/dt=2026-10-15/")
    head = s3.head_object(Bucket="rqg-test", Key=keys[0])
    assert head["ServerSideEncryption"] == "AES256"
    assert upload_logs_s3.upload_logs(synthetic[1], "rqg-test", s3=s3) == []  # idempotent
    assert len(upload_logs_s3.upload_logs(synthetic[0], "rqg-other", s3=s3, dry_run=True)) == 14


@mock_aws
def test_upload_cli(synthetic, monkeypatch):
    import upload_logs_s3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="cli-bucket")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    assert upload_logs_s3.main(["--bucket", "cli-bucket", "--log-dir", str(synthetic[1])]) == 0
    monkeypatch.delenv("RQG_S3_BUCKET", raising=False)
    assert upload_logs_s3.main(["--log-dir", str(synthetic[1])]) == 2


# ------------------------------------------------------------------- Athena
@mock_aws
def test_athena_runner_with_moto():
    from moto.athena.models import QueryResults, athena_backends
    from moto.core import DEFAULT_ACCOUNT_ID

    client = boto3.client("athena", region_name="us-east-1")
    client.create_work_group(
        Name="rqg", Configuration={"ResultConfiguration": {"OutputLocation": "s3://r/"}}
    )
    rows = [
        {"Data": [{"VarCharValue": "dt"}, {"VarCharValue": "n"}]},
        {"Data": [{"VarCharValue": "2026-10-15"}, {"VarCharValue": "108"}]},
    ]
    backend = athena_backends[DEFAULT_ACCOUNT_ID]["us-east-1"]
    backend.query_results_queue.append(QueryResults(rows=rows, column_info=[]))
    r = AthenaRunner("rqg", "rqg_logs", client=client, sleep=lambda s: None)
    assert r.run("quality_trend") == [{"dt": "2026-10-15", "n": "108"}]


class FakeAthena:
    """Stub for paths moto cannot simulate (FAILED state, pagination, throttling, timeout)."""

    def __init__(self, states, pages=None, throttle_first=False):
        self.states = list(states)
        self.pages = pages or [{"ResultSet": {"Rows": [{"Data": [{"VarCharValue": "x"}]}]}}]
        self.throttle_first = throttle_first
        self.stopped = False

    def start_query_execution(self, **kw):
        if self.throttle_first:
            self.throttle_first = False
            raise ClientError(
                {"Error": {"Code": "ThrottlingException", "Message": "slow down"}},
                "StartQueryExecution",
            )
        assert (
            kw["WorkGroup"] == "wg" and kw["ResultConfiguration"]["OutputLocation"] == "s3://out/"
        )
        return {"QueryExecutionId": "q1"}

    def get_query_execution(self, QueryExecutionId):
        st = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return {"QueryExecution": {"Status": {"State": st, "StateChangeReason": "SYNTAX_ERROR"}}}

    def get_query_results(self, QueryExecutionId, NextToken=None):
        return self.pages.pop(0)

    def stop_query_execution(self, QueryExecutionId):
        self.stopped = True


def _runner(fake, **kw):
    return AthenaRunner(
        "wg", "db", output_location="s3://out/", client=fake, sleep=lambda s: None, **kw
    )


def test_athena_polls_paginates_and_retries():
    pages = [
        {
            "ResultSet": {
                "Rows": [{"Data": [{"VarCharValue": "a"}]}, {"Data": [{"VarCharValue": "1"}]}]
            },
            "NextToken": "t",
        },
        {"ResultSet": {"Rows": [{"Data": [{"VarCharValue": "2"}]}]}},
    ]
    fake = FakeAthena(["QUEUED", "RUNNING", "SUCCEEDED"], pages, throttle_first=True)
    assert _runner(fake).query("select 1") == [{"a": "1"}, {"a": "2"}]


def test_athena_failed_and_timeout():
    with pytest.raises(AthenaQueryError, match="FAILED: SYNTAX_ERROR"):
        _runner(FakeAthena(["FAILED"])).query("bad")
    fake = FakeAthena(["RUNNING"])
    with pytest.raises(AthenaQueryError, match="timed out"):
        _runner(fake, timeout_s=3, poll_interval_s=1).query("slow")
    assert fake.stopped


def test_athena_non_retryable_error_raises():
    class Denied(FakeAthena):
        def start_query_execution(self, **kw):
            raise ClientError(
                {"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "Start"
            )

    with pytest.raises(ClientError):
        _runner(Denied(["SUCCEEDED"])).query("x")
