#!/usr/bin/env python
"""Run every curated attack (guardrails on, and off for comparison). Exit 1 if any attack in
the must-never-succeed set succeeds with guardrails on."""

from __future__ import annotations

import _bootstrap  # noqa: F401
from rqg.config import get_settings
from rqg.safety.attack_runner import run_suite, write_safety


def main() -> int:
    s = get_settings()
    report = run_suite(s)
    p = write_safety(report, s.reports_dir)
    print(p.read_text(encoding="utf-8"))
    fails = report["summary"]["must_never_failures"]
    if fails:
        print(f"SAFETY GATE FAILED: must-never attacks succeeded: {fails}")
        return 1
    print("SAFETY GATE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
