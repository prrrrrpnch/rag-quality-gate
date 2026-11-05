"""Regression gate: compare a run against the committed baseline with per-metric tolerance.

Rules
-----
* Compare like with like: the current run's KPIs are recomputed on the baseline's case ids
  only. Cases added since the baseline are reported separately (non-gating) until the
  baseline is rebuilt.
* A baseline is only comparable if mode (mock/real), embedding backend and dataset MAJOR
  version match; otherwise the gate exits 2 ("incompatible") rather than guessing.
* Each metric has a direction and an allowed regression. Absolute tolerance (``max_regression``)
  for rates/scores; relative tolerance (``max_regression_pct``) plus a noise floor
  (``abs_slack``) for latency and cost. A delta exactly equal to the tolerance passes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rqg.evals.report import compute_kpis

DEFAULT_THRESHOLDS: dict[str, dict[str, Any]] = {
    "pass_rate": {"direction": "higher", "max_regression": 0.02},
    "hallucination_rate": {"direction": "lower", "max_regression": 0.02},
    "groundedness_mean": {"direction": "higher", "max_regression": 0.03},
    "relevance_mean": {"direction": "higher", "max_regression": 0.05},
    "refusal_recall": {"direction": "higher", "max_regression": 0.0},
    "over_refusal_rate": {"direction": "lower", "max_regression": 0.05},
    "tool_success_rate": {"direction": "higher", "max_regression": 0.0},
    "context_recall_mean": {"direction": "higher", "max_regression": 0.05},
    "latency_p95_ms": {"direction": "lower", "max_regression_pct": 25, "abs_slack": 50},
    "cost_per_100_queries_usd": {"direction": "lower", "max_regression_pct": 25, "abs_slack": 0.01},
}
EPS = 1e-9


class IncompatibleBaseline(Exception):
    """Baseline and run cannot be compared meaningfully."""


@dataclass
class GateRow:
    metric: str
    baseline: float | None
    current: float | None
    delta: float | None
    allowed: str
    status: str  # PASS | FAIL | SKIP


@dataclass
class GateResult:
    rows: list[GateRow]
    new_failures: list[str] = field(default_factory=list)
    fixed: list[str] = field(default_factory=list)
    new_cases: list[str] = field(default_factory=list)
    new_case_pass_rate: float | None = None
    missing_cases: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.status != "FAIL" for r in self.rows)


def check_metric(name: str, base: float | None, cur: float | None, rule: dict[str, Any]) -> GateRow:
    """Evaluate one metric against its rule."""
    if base is None or cur is None:
        return GateRow(name, base, cur, None, "-", "SKIP")
    higher = rule["direction"] == "higher"
    regression = (base - cur) if higher else (cur - base)  # > 0 means worse
    if "max_regression_pct" in rule:
        allowed = max(abs(base) * rule["max_regression_pct"] / 100, rule.get("abs_slack", 0.0))
        allowed_txt = f"+{rule['max_regression_pct']}% (min {rule.get('abs_slack', 0)})"
    else:
        allowed = rule["max_regression"]
        allowed_txt = f"{'-' if higher else '+'}{allowed}"
    status = "PASS" if regression <= allowed + EPS else "FAIL"
    return GateRow(name, base, cur, round(cur - base, 6), allowed_txt, status)


def compare(
    baseline: dict[str, Any],
    run: dict[str, Any],
    thresholds: dict[str, dict[str, Any]] | None = None,
) -> GateResult:
    bm, rm = baseline["meta"], run["meta"]
    for key in ("mode", "embedding_backend"):
        if bm.get(key) != rm.get(key):
            raise IncompatibleBaseline(f"{key} differs: baseline={bm.get(key)} run={rm.get(key)}")
    if bm["dataset_version"].split(".")[0] != rm["dataset_version"].split(".")[0]:
        raise IncompatibleBaseline("dataset major version differs; rebuild the baseline")
    thresholds = thresholds or DEFAULT_THRESHOLDS
    base_cases = baseline["cases"]
    run_cases = {c["case_id"]: c for c in run["cases"]}
    shared = [cid for cid in base_cases if cid in run_cases]
    missing = sorted(cid for cid in base_cases if cid not in run_cases)
    cur_kpis = compute_kpis([run_cases[c] for c in shared]) if shared else {}
    base_kpis = baseline["kpis"]
    rows = [
        check_metric(m, base_kpis.get(m), cur_kpis.get(m), rule) for m, rule in thresholds.items()
    ]
    new_fail = sorted(c for c in shared if base_cases[c]["passed"] and not run_cases[c]["passed"])
    fixed = sorted(c for c in shared if not base_cases[c]["passed"] and run_cases[c]["passed"])
    new_ids = sorted(set(run_cases) - set(base_cases))
    npr = sum(run_cases[c]["passed"] for c in new_ids) / len(new_ids) if new_ids else None
    return GateResult(rows, new_fail, fixed, new_ids, npr, missing)


def _f(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"{v:+.4f}".rstrip("0").rstrip(".") if v != 0 else "0"


def _v(v: float | None) -> str:
    return "n/a" if v is None else (f"{v:.4f}".rstrip("0").rstrip(".") or "0")


def render_gate(res: GateResult, baseline: dict[str, Any], run: dict[str, Any]) -> str:
    verdict = "✅ PASS" if res.passed else "❌ FAIL — regression detected"
    lines = [
        f"## Regression gate: {verdict}",
        "",
        f"baseline `{baseline['meta']['git_sha']}` (dataset v{baseline['meta']['dataset_version']}, "
        f"{baseline['meta']['mode']}) vs run `{run['meta']['git_sha']}` "
        f"(prompt {run['meta']['prompt_version']}, {run['meta']['n_cases']} cases)",
        "",
        "| Metric | Baseline | Current | Delta | Allowed | Status |",
        "|---|---|---|---|---|---|",
    ]
    for r in res.rows:
        icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "➖"}[r.status]
        lines.append(
            f"| {r.metric} | {_v(r.baseline)} | {_v(r.current)} | {_f(r.delta)} | {r.allowed} | {icon} {r.status} |"
        )
    lines.append("")
    if res.new_failures:
        lines.append(
            f"**Newly failing cases ({len(res.new_failures)}):** "
            + ", ".join(f"`{c}`" for c in res.new_failures)
        )
    if res.fixed:
        lines.append(
            f"**Newly passing cases ({len(res.fixed)}):** " + ", ".join(f"`{c}`" for c in res.fixed)
        )
    if res.new_cases:
        lines.append(
            f"**New cases not in baseline ({len(res.new_cases)}, not gated):** pass rate "
            f"{_v(res.new_case_pass_rate)} — rebuild the baseline to start gating them."
        )
    if res.missing_cases:
        lines.append(f"**Baseline cases missing from this run:** {len(res.missing_cases)}")
    return "\n".join(lines) + "\n"


def load_json(p: Path) -> dict[str, Any]:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def load_thresholds(p: Path | None) -> dict[str, dict[str, Any]]:
    if p and Path(p).exists():
        return load_json(p)
    return DEFAULT_THRESHOLDS


def make_baseline(run: dict[str, Any]) -> dict[str, Any]:
    """Slim a run into a committed baseline (per-case pass/score kept for like-for-like)."""
    keep = (
        "passed",
        "observed_behavior",
        "expected_behavior",
        "category",
        "scores",
        "checks",
        "turn_latencies_ms",
        "cost_usd",
        "input_tokens",
        "output_tokens",
    )
    return {
        "meta": run["meta"],
        "kpis": run["kpis"],
        "per_category": run["per_category"],
        "failing_case_ids": sorted(c["case_id"] for c in run["cases"] if not c["passed"]),
        "cases": {
            c["case_id"]: {k: c[k] for k in keep} | {"case_id": c["case_id"]} for c in run["cases"]
        },
    }
