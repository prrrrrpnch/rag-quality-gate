#!/usr/bin/env python
"""Promote a bad logged interaction to a golden case (status=pending_review).

    python scripts/promote_failure.py <trace_id> --behavior refuse \
        --expected-answer "I don't know — that isn't covered in the Zephyr Home manuals."

    python scripts/promote_failure.py <trace_id> --behavior answer \
        --expected-answer "Up to 60 minutes." --fact "60 minutes" --source brewmate_k2_manual

Missing values are prompted for interactively when stdin is a terminal. The case is appended
with origin=promoted_from_prod and the dataset minor version is bumped. A reviewer flips
status to `approved` in a PR, after which the case is evaluated and gated.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from rqg.config import get_settings
from rqg.evals.promote import fetch_interaction, promote


def _ask(label: str) -> str:
    if not sys.stdin.isatty():
        raise SystemExit(f"missing --{label} (non-interactive)")
    return input(f"{label}: ").strip()


def main(argv: list[str] | None = None) -> int:
    s = get_settings()
    ap = argparse.ArgumentParser()
    ap.add_argument("trace_id")
    ap.add_argument("--behavior", choices=["answer", "refuse", "clarify", "tool_call"])
    ap.add_argument("--expected-answer")
    ap.add_argument("--fact", action="append", default=[], help="required fact (repeatable)")
    ap.add_argument("--forbidden", action="append", default=[], help="forbidden fact (repeatable)")
    ap.add_argument("--source", action="append", default=[], help="expected source doc id")
    ap.add_argument("--category")
    ap.add_argument("--log-dir", type=Path, default=s.log_dir)
    ap.add_argument("--golden", type=Path, default=s.golden_path)
    a = ap.parse_args(argv)

    rec = fetch_interaction(a.trace_id, a.log_dir)
    if rec is None:
        print(f"trace {a.trace_id} not found in {a.log_dir} (or LangSmith)")
        return 1
    print(f"user (redacted):   {rec.get('user_input_redacted')}")
    print(f"answer (redacted): {rec.get('answer_redacted')}")
    behavior = a.behavior or _ask("behavior")
    expected = a.expected_answer or _ask("expected-answer")
    facts = a.fact or ([] if behavior == "refuse" else [_ask("fact")])
    case = promote(
        rec,
        a.golden,
        expected_behavior=behavior,
        expected_answer=expected,
        required_facts=facts,
        forbidden_facts=a.forbidden,
        expected_sources=a.source,
        category=a.category,
    )
    print(f"appended {case.id} (v{case.dataset_version}, status={case.status}) to {a.golden}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
