"""Run the SQL checks on Amazon Athena (boto3) with polling, timeouts and error handling."""

from __future__ import annotations

import time
from typing import Any

from botocore.exceptions import ClientError

from rqg.data_validation import render_sql

TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}
RETRYABLE = {"ThrottlingException", "TooManyRequestsException"}


class AthenaQueryError(RuntimeError):
    """A query ended in FAILED/CANCELLED or timed out."""


class AthenaRunner:
    """Thin, testable Athena client. Pass ``client`` to inject a stub or moto client."""

    def __init__(
        self,
        workgroup: str,
        database: str,
        output_location: str | None = None,
        client: Any = None,
        region: str | None = None,
        poll_interval_s: float = 1.0,
        max_poll_interval_s: float = 8.0,
        timeout_s: float = 300.0,
        sleep=time.sleep,
    ) -> None:
        if client is None:
            import boto3

            client = boto3.client("athena", region_name=region)
        self.client = client
        self.workgroup = workgroup
        self.database = database
        self.output_location = output_location
        self.poll_interval_s = poll_interval_s
        self.max_poll_interval_s = max_poll_interval_s
        self.timeout_s = timeout_s
        self.sleep = sleep

    def _call(self, fn, **kw):
        for attempt in range(5):
            try:
                return fn(**kw)
            except ClientError as e:
                if e.response.get("Error", {}).get("Code") in RETRYABLE and attempt < 4:
                    self.sleep(min(2**attempt, 16))
                    continue
                raise
        raise AssertionError("unreachable")

    def start(self, sql: str) -> str:
        kw: dict[str, Any] = {
            "QueryString": sql,
            "QueryExecutionContext": {"Database": self.database},
            "WorkGroup": self.workgroup,
        }
        if self.output_location:
            kw["ResultConfiguration"] = {"OutputLocation": self.output_location}
        return self._call(self.client.start_query_execution, **kw)["QueryExecutionId"]

    def wait(self, qid: str) -> dict[str, Any]:
        waited, interval = 0.0, self.poll_interval_s
        while True:
            ex = self._call(self.client.get_query_execution, QueryExecutionId=qid)["QueryExecution"]
            state = ex["Status"]["State"]
            if state in TERMINAL:
                if state != "SUCCEEDED":
                    reason = ex["Status"].get("StateChangeReason", "no reason given")
                    raise AthenaQueryError(f"query {qid} {state}: {reason}")
                return ex
            if waited >= self.timeout_s:
                self._call(self.client.stop_query_execution, QueryExecutionId=qid)
                raise AthenaQueryError(f"query {qid} timed out after {self.timeout_s}s")
            self.sleep(interval)
            waited += interval
            interval = min(interval * 2, self.max_poll_interval_s)

    def results(self, qid: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        header: list[str] | None = None
        token = None
        while True:
            kw = {"QueryExecutionId": qid, **({"NextToken": token} if token else {})}
            page = self._call(self.client.get_query_results, **kw)
            for r in page["ResultSet"]["Rows"]:
                vals = [d.get("VarCharValue") for d in r["Data"]]
                if header is None:
                    header = [str(v) for v in vals]
                    continue
                rows.append(dict(zip(header, vals, strict=False)))
            token = page.get("NextToken")
            if not token:
                return rows

    def query(self, sql: str) -> list[dict[str, Any]]:
        qid = self.start(sql)
        self.wait(qid)
        return self.results(qid)

    def run(self, name: str, **params: str) -> list[dict[str, Any]]:
        return self.query(render_sql(name, **params))
