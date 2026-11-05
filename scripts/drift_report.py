#!/usr/bin/env python
"""Drift report: compare two time windows of logs, or two eval runs.

    python scripts/drift_report.py                                   # synthetic logs, days 1-7 vs last 3
    python scripts/drift_report.py --log-dir logs --ref 2026-10-15:2026-10-21 --cur 2026-10-26:2026-10-28
    python scripts/drift_report.py --runs reports/runs/A.json reports/runs/B.json

Exit code: 0 OK/WARN, 3 ALERT (so a scheduled job can page on it).
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import _bootstrap  # noqa: F401
from rqg.config import REPO_ROOT, get_settings
from rqg.evals.gate import load_json
from rqg.observability.drift import (
    compare_windows,
    overall_status,
    render_drift,
    runs_to_rows,
    split_by_date,
)
from rqg.observability.logger import read_logs


def _rng(s: str) -> tuple[date, date]:
    a, b = s.split(":")
    return date.fromisoformat(a), date.fromisoformat(b)


def main(argv: list[str] | None = None) -> int:
    s = get_settings()
    ap = argparse.ArgumentParser()
    ap.add_argument("--log-dir", type=Path, default=REPO_ROOT / "data" / "synthetic_logs")
    ap.add_argument("--ref", default="2026-10-15:2026-10-21")
    ap.add_argument("--cur", default="2026-10-26:2026-10-28")
    ap.add_argument("--runs", nargs=2, type=Path)
    ap.add_argument("--out", type=Path, default=s.reports_dir / "drift.md")
    a = ap.parse_args(argv)
    if a.runs:
        ref, cur = (runs_to_rows(load_json(p)) for p in a.runs)
        title = f"Eval run `{a.runs[0].name}` (reference) vs `{a.runs[1].name}` (current)"
        note = ""
    else:
        rows = read_logs(a.log_dir)
        ref, cur = split_by_date(rows, _rng(a.ref), _rng(a.cur))
        title = f"Logs in `{a.log_dir.relative_to(REPO_ROOT) if a.log_dir.is_relative_to(REPO_ROOT) else a.log_dir}`: reference {a.ref} (n={len(ref)}) vs current {a.cur} (n={len(cur)})"
        note = (
            "SYNTHETIC data (scripts/generate_synthetic_logs.py, seed 42) — not production traffic."
            if all(r.get("synthetic") for r in rows) and rows
            else ""
        )
    drift = compare_windows(ref, cur)
    md = render_drift(drift, title, note)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(md, encoding="utf-8")
    print(md)
    return 3 if overall_status(drift) == "ALERT" else 0


if __name__ == "__main__":
    raise SystemExit(main())
