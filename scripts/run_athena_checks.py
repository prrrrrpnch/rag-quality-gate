#!/usr/bin/env python
"""Run the SQL data-validation checks, locally (DuckDB) or on Athena.

    python scripts/run_athena_checks.py --local                                 # synthetic logs
    python scripts/run_athena_checks.py --local --log-dir logs --expect-pii 0   # real app logs
    python scripts/run_athena_checks.py --athena   # needs AWS creds + RQG_ATHENA_* env vars

Zero-row checks (pii_leak_check, data_quality_check) fail the run when they return rows,
unless --expect-pii N says exactly N planted leaks are expected (synthetic demo set).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import _bootstrap  # noqa: F401
from rqg.config import REPO_ROOT, get_settings
from rqg.data_validation import REPORT_QUERIES, ZERO_ROW_CHECKS
from rqg.data_validation.pii_scan import scan_logs


def _table(rows: list[dict], limit: int = 15) -> str:
    if not rows:
        return "_no rows_\n"
    cols = list(rows[0])
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows[:limit]:
        out.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    if len(rows) > limit:
        out.append(f"| … {len(rows) - limit} more rows |" + " |" * (len(cols) - 1))
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    s = get_settings()
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--local", action="store_true", default=True)
    g.add_argument("--athena", action="store_true")
    ap.add_argument("--log-dir", type=Path, default=REPO_ROOT / "data" / "synthetic_logs")
    ap.add_argument("--since", default="2026-01-01")
    ap.add_argument(
        "--expect-pii", type=int, default=None, help="exact number of PII rows expected"
    )
    ap.add_argument("--out", type=Path, default=s.reports_dir / "sql_checks.md")
    a = ap.parse_args(argv)
    if a.expect_pii is None:
        a.expect_pii = 5 if a.log_dir.name == "synthetic_logs" and not a.athena else 0

    if a.athena:
        from rqg.data_validation.athena import AthenaRunner

        runner = AthenaRunner(
            workgroup=os.environ["RQG_ATHENA_WORKGROUP"],
            database=os.environ.get("RQG_ATHENA_DATABASE", "rqg_logs"),
            region=os.environ.get("AWS_REGION"),
        )
        engine = f"Athena workgroup {runner.workgroup}"
    else:
        from rqg.data_validation.duckdb_local import LocalSQL

        runner = LocalSQL(a.log_dir)
        engine = f"DuckDB over {a.log_dir}"

    md = [f"# SQL data-validation checks ({engine})", ""]
    ok = True
    for name in ZERO_ROW_CHECKS:
        rows = runner.run(name, since=a.since)
        expected = a.expect_pii if name == "pii_leak_check" else 0
        passed = len(rows) == expected
        ok &= passed
        md += [
            f"## {name}: {'PASS' if passed else 'FAIL'} ({len(rows)} rows, expected {expected})",
            "",
            _table(rows),
        ]
    for name in REPORT_QUERIES:
        md += [f"## {name}", "", _table(runner.run(name, since=a.since))]
    if not a.athena:
        py = scan_logs(a.log_dir)
        agree = len(py) >= a.expect_pii
        md += [f"## Python PII scan (independent check): {len(py)} findings", ""]
        ok &= agree if a.expect_pii else not py
    text = "\n".join(md)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(text, encoding="utf-8")
    print(text)
    print("SQL CHECKS PASSED" if ok else "SQL CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
