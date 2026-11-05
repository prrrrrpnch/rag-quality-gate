#!/usr/bin/env python
"""Run the golden-set evaluation and write reports/latest.{json,md}.

python scripts/run_eval.py --subset smoke   # 25-case stratified smoke set
python scripts/run_eval.py --subset full
"""

from __future__ import annotations

import argparse

import _bootstrap  # noqa: F401
from rqg.config import get_settings
from rqg.evals.runner import run_eval, write_run


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subset", choices=["smoke", "full"], default="full")
    args = ap.parse_args()
    s = get_settings()
    print(f"mode={s.mode} app={s.app_model if not s.use_mock else 'mock'} subset={args.subset}")
    run = run_eval(args.subset, s)
    jp, mp = write_run(run, s.reports_dir)
    k = run["kpis"]
    print(mp.read_text(encoding="utf-8").split("## Per category")[0])
    print(
        f"tokens: {k['app_input_tokens']:,} in / {k['app_output_tokens']:,} out · "
        f"est. cost this run ${sum(c['cost_usd'] for c in run['cases']):.4f}"
    )
    print(f"wrote {jp} and {mp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
