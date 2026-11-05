"""Python PII scan over JSONL logs — an independent second check next to the SQL one
(adds the Luhn check for card numbers, which SQL regexes cannot do)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rqg.guardrails.pii import find_pii
from rqg.observability.logger import read_logs

TEXT_FIELDS = ("user_input_redacted", "answer_redacted")


@dataclass(frozen=True)
class LeakFinding:
    trace_id: str
    field: str
    kind: str


def scan_logs(log_dir: Path) -> list[LeakFinding]:
    out: list[LeakFinding] = []
    for row in read_logs(log_dir):
        for f in TEXT_FIELDS:
            for hit in find_pii(row.get(f) or ""):
                out.append(LeakFinding(str(row.get("trace_id")), f, hit.kind))
    return out
