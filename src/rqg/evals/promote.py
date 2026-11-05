"""Turn a logged production failure into a pending-review golden case."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from rqg.evals.dataset import GoldenCase, append_case, bump_minor, load_golden
from rqg.guardrails.pii import redact
from rqg.observability.logger import find_log_record

BEHAVIOR_TO_CATEGORY = {
    "refuse": "out_of_scope",
    "answer": "single_fact",
    "clarify": "single_fact",
    "tool_call": "tool_call",
}


def fetch_interaction(trace_id: str, log_dir: Path) -> dict[str, Any] | None:
    """Look up a logged interaction by trace id; fall back to LangSmith when configured."""
    rec = find_log_record(log_dir, trace_id)
    if rec is not None:
        return rec
    if os.getenv("LANGSMITH_API_KEY"):
        try:  # pragma: no cover - needs a LangSmith account
            from langsmith import Client

            run = Client().read_run(trace_id)
            return {
                "trace_id": trace_id,
                "user_input_redacted": str((run.inputs or {}).get("user_message", "")),
                "answer_redacted": str((run.outputs or {}).get("answer", "")),
            }
        except Exception:
            return None
    return None


def next_case_id(golden: Path, prefix: str = "pf") -> str:
    ds = load_golden(golden, include_pending=True)
    nums = [int(c.id.split("-")[1]) for c in ds.cases if c.id.startswith(prefix + "-")]
    return f"{prefix}-{(max(nums) + 1) if nums else 1:03d}"


def build_case(
    record: dict[str, Any],
    golden: Path,
    expected_behavior: str,
    expected_answer: str,
    required_facts: list[str] | None = None,
    forbidden_facts: list[str] | None = None,
    expected_sources: list[str] | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Build (not yet write) the new case dict. User text is PII-scrubbed again."""
    question, _ = redact(record.get("user_input_redacted") or "")
    old_answer, _ = redact(record.get("answer_redacted") or "")
    if not question.strip():
        raise ValueError("logged interaction has no user input")
    ds = load_golden(golden, include_pending=True)
    return {
        "id": next_case_id(golden),
        "dataset_version": bump_minor(ds.version),
        "category": category or BEHAVIOR_TO_CATEGORY[expected_behavior],
        "turns": [question],
        "expected_answer": expected_answer,
        "required_facts": required_facts or [],
        "forbidden_facts": forbidden_facts or [],
        "expected_sources": expected_sources or [],
        "source_match": "any",
        "expected_behavior": expected_behavior,
        "expected_tools": [],
        "tags": ["promoted", f"trace:{record.get('trace_id', 'unknown')}"],
        "difficulty": "medium",
        "status": "pending_review",
        "origin": "promoted_from_prod",
        "notes": f"Promoted from production. Original (bad) answer, redacted: {old_answer[:300]}",
    }


def promote(record: dict[str, Any], golden: Path, **kwargs: Any) -> GoldenCase:
    case = build_case(record, golden, **kwargs)
    return append_case(golden, case)
