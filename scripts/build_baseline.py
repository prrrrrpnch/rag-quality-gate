#!/usr/bin/env python
"""Freeze a full eval run into the committed baseline.

    python scripts/build_baseline.py                  # uses reports/latest.json
    python scripts/build_baseline.py --run reports/runs/<id>.json

Mock-mode runs write baselines/baseline.json; real-mode runs write baselines/baseline.real.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import _bootstrap  # noqa: F401
from rqg.config import get_settings
from rqg.evals.gate import load_json, make_baseline


def main() -> int:
    s = get_settings()
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, default=s.reports_dir / "latest.json")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    run = load_json(args.run)
    if run["meta"]["subset"] != "full":
        print("refusing to baseline a smoke run; run the full eval first")
        return 2
    out = args.out or s.baselines_dir / (
        "baseline.json" if run["meta"]["mode"] == "mock" else "baseline.real.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(make_baseline(run), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"baseline written: {out} (git {run['meta']['git_sha']}, dataset v{run['meta']['dataset_version']}, {run['meta']['mode']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
