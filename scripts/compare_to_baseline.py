#!/usr/bin/env python
"""Regression gate. Exit 0 = pass, 1 = regression, 2 = incompatible baseline.

python scripts/compare_to_baseline.py [--run reports/latest.json] [--baseline ...]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import _bootstrap  # noqa: F401
from rqg.config import get_settings
from rqg.evals.gate import IncompatibleBaseline, compare, load_json, load_thresholds, render_gate


def main() -> int:
    s = get_settings()
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, default=s.reports_dir / "latest.json")
    ap.add_argument("--baseline", type=Path, default=None)
    ap.add_argument("--thresholds", type=Path, default=s.baselines_dir / "thresholds.json")
    ap.add_argument("--out", type=Path, default=s.reports_dir / "gate.md")
    args = ap.parse_args()
    run = load_json(args.run)
    base_path = args.baseline or s.baselines_dir / (
        "baseline.json" if run["meta"]["mode"] == "mock" else "baseline.real.json"
    )
    if not base_path.exists():
        print(f"no baseline at {base_path}; build one with `make baseline`")
        return 2
    baseline = load_json(base_path)
    try:
        res = compare(baseline, run, load_thresholds(args.thresholds))
    except IncompatibleBaseline as e:
        print(f"INCOMPATIBLE BASELINE: {e}")
        return 2
    md = render_gate(res, baseline, run)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md, encoding="utf-8")
    print(md)
    return 0 if res.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
