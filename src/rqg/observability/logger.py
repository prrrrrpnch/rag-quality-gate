"""Append-only JSONL interaction log, partitioned ``dt=YYYY-MM-DD/``.

The logger redacts *every* PII kind itself (including serials), so raw user text can never be
written even if a caller forgets. The same files are queried by Athena (S3) and DuckDB (local).
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rqg.guardrails.pii import redact

LOG_FIELDS = (
    "ts",
    "session_id",
    "trace_id",
    "prompt_version",
    "model",
    "latency_ms",
    "input_tokens",
    "output_tokens",
    "cost_usd",
    "guardrail_flags",
    "refused",
    "tools_called",
    "retrieved_doc_ids",
    "user_input_redacted",
    "answer_redacted",
    "eval_scores",
    "synthetic",
)


class InteractionLogger:
    """Writes one JSON object per interaction."""

    def __init__(self, log_dir: Path, enabled: bool = True) -> None:
        self.log_dir = Path(log_dir)
        self.enabled = enabled
        self._lock = threading.Lock()

    def path_for(self, ts: datetime) -> Path:
        return self.log_dir / f"dt={ts:%Y-%m-%d}" / "interactions.jsonl"

    def log(self, *, user_input: str, answer: str, **fields: Any) -> dict[str, Any]:
        """Redact, normalise and append. Returns the stored record."""
        ts = fields.pop("ts", None) or datetime.now(UTC)
        record = {k: None for k in LOG_FIELDS}
        record.update({k: v for k, v in fields.items() if k in LOG_FIELDS})
        record["ts"] = ts.isoformat() if isinstance(ts, datetime) else str(ts)
        record["user_input_redacted"] = redact(user_input)[0]
        record["answer_redacted"] = redact(answer)[0]
        record["guardrail_flags"] = list(record["guardrail_flags"] or [])
        record["tools_called"] = list(record["tools_called"] or [])
        record["retrieved_doc_ids"] = list(record["retrieved_doc_ids"] or [])
        record["synthetic"] = bool(record["synthetic"])
        if self.enabled:
            dt = datetime.fromisoformat(record["ts"])
            p = self.path_for(dt)
            p.parent.mkdir(parents=True, exist_ok=True)
            with self._lock, p.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record


def read_logs(log_dir: Path) -> list[dict[str, Any]]:
    """Read every record under ``log_dir`` (all partitions)."""
    rows: list[dict[str, Any]] = []
    for p in sorted(Path(log_dir).glob("dt=*/*.jsonl")):
        with p.open(encoding="utf-8") as f:
            rows.extend(json.loads(line) for line in f if line.strip())
    return rows


def find_log_record(log_dir: Path, trace_id: str) -> dict[str, Any] | None:
    for r in read_logs(log_dir):
        if r.get("trace_id") == trace_id:
            return r
    return None
