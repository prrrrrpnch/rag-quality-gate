"""Run the Athena SQL files locally with DuckDB over the partitioned JSONL logs.

Dialect shims (DuckDB macros) make the *same SQL text* run in both engines:
``regexp_like`` -> ``regexp_matches`` and ``approx_percentile`` -> ``quantile_cont``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from rqg.data_validation import render_sql

COLUMNS = {
    "ts": "VARCHAR",
    "session_id": "VARCHAR",
    "trace_id": "VARCHAR",
    "prompt_version": "VARCHAR",
    "model": "VARCHAR",
    "latency_ms": "DOUBLE",
    "input_tokens": "INTEGER",
    "output_tokens": "INTEGER",
    "cost_usd": "DOUBLE",
    "guardrail_flags": "VARCHAR[]",
    "refused": "BOOLEAN",
    "tools_called": "VARCHAR[]",
    "retrieved_doc_ids": "VARCHAR[]",
    "user_input_redacted": "VARCHAR",
    "answer_redacted": "VARCHAR",
    "eval_scores": "STRUCT(faithfulness DOUBLE, answer_relevancy DOUBLE, hallucination BOOLEAN, retrieval_hit BOOLEAN)",
    "synthetic": "BOOLEAN",
}


class LocalSQL:
    """DuckDB connection with an ``interactions`` view matching the Athena table."""

    def __init__(self, log_dir: Path) -> None:
        self.log_dir = Path(log_dir)
        self.con = duckdb.connect()
        self.con.execute("CREATE MACRO regexp_like(s, p) AS regexp_matches(s, p)")
        self.con.execute("CREATE MACRO approx_percentile(x, p) AS quantile_cont(x, p)")
        files = list(self.log_dir.glob("dt=*/*.jsonl"))
        if not files:
            raise FileNotFoundError(f"no dt=*/ JSONL partitions under {self.log_dir}")
        cols = ", ".join(f"'{k}': '{v}'" for k, v in COLUMNS.items())
        glob = str(self.log_dir / "dt=*" / "*.jsonl").replace("'", "''")
        self.con.execute(
            f"""CREATE VIEW interactions AS SELECT * FROM read_json('{glob}',
                format='newline_delimited', hive_partitioning=true, hive_types={{'dt': 'VARCHAR'}},
                columns={{{cols}}})"""
        )

    def query(self, sql: str) -> list[dict[str, Any]]:
        cur = self.con.execute(sql)
        names = [d[0] for d in cur.description]
        return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]

    def run(self, name: str, **params: str) -> list[dict[str, Any]]:
        return self.query(render_sql(name, **params))
