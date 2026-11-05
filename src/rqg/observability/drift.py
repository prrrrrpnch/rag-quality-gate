"""Drift detection between two windows of logs (or two eval runs).

* Continuous metrics (latency, cost, judge scores): Population Stability Index (PSI) on
  reference-quantile bins, plus the two-sample Kolmogorov–Smirnov test.
  PSI < 0.10 OK · 0.10–0.25 WARN · > 0.25 ALERT (common industry rule of thumb).
* Rates (refusal, retrieval hit, guardrail flags): absolute change with a two-proportion
  z-test. WARN if |Δ| >= 3 pts and p < 0.05; ALERT if |Δ| >= 6 pts and p < 0.05.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
from scipy import stats

SEVERITY = {"OK": 0, "WARN": 1, "ALERT": 2}


def psi(reference: list[float], current: list[float], bins: int = 10, eps: float = 1e-4) -> float:
    """Population Stability Index of ``current`` against ``reference``."""
    ref = np.asarray(reference, dtype=float)
    cur = np.asarray(current, dtype=float)
    if ref.size == 0 or cur.size == 0:
        return float("nan")
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if edges.size < 2:  # constant reference
        return 0.0 if np.allclose(cur, ref[0]) else float("inf")
    edges[0], edges[-1] = -np.inf, np.inf
    r = np.histogram(ref, edges)[0] / ref.size
    c = np.histogram(cur, edges)[0] / cur.size
    r, c = np.clip(r, eps, None), np.clip(c, eps, None)
    return float(np.sum((c - r) * np.log(c / r)))


def psi_status(v: float) -> str:
    if math.isnan(v) or v < 0.10:
        return "OK"
    return "WARN" if v < 0.25 else "ALERT"


def two_proportion_p(x1: int, n1: int, x2: int, n2: int) -> float:
    if n1 == 0 or n2 == 0:
        return 1.0
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = (x2 / n2 - x1 / n1) / se
    return float(2 * (1 - stats.norm.cdf(abs(z))))


def rate_status(delta: float, p: float) -> str:
    if p >= 0.05 or abs(delta) < 0.03:
        return "OK"
    return "ALERT" if abs(delta) >= 0.06 else "WARN"


@dataclass
class DriftRow:
    metric: str
    kind: str  # "distribution" | "rate"
    reference: float | None
    current: float | None
    statistic: str
    status: str


def _num(rows: list[dict[str, Any]], key: str) -> list[float]:
    """Numeric values of a top-level field, or of ``eval_scores.<name>`` for ``score:<name>``."""
    out = []
    for r in rows:
        val = (r.get("eval_scores") or {}).get(key[6:]) if key.startswith("score:") else r.get(key)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            out.append(float(val))
    return out


def _rate(rows: list[dict[str, Any]], fn) -> tuple[int, int]:
    vals = [fn(r) for r in rows]
    vals = [v for v in vals if v is not None]
    return sum(bool(v) for v in vals), len(vals)


DISTRIBUTIONS = {
    "latency_ms": "latency_ms",
    "cost_usd": "cost_usd",
    "faithfulness": "score:faithfulness",
    "answer_relevancy": "score:answer_relevancy",
}
RATES = {
    "refusal_rate": lambda r: r.get("refused"),
    "retrieval_hit_rate": lambda r: (r.get("eval_scores") or {}).get("retrieval_hit"),
    "guardrail_flag_rate": lambda r: bool(r.get("guardrail_flags")),
}


def compare_windows(
    reference: list[dict[str, Any]], current: list[dict[str, Any]]
) -> list[DriftRow]:
    rows: list[DriftRow] = []
    for name, key in DISTRIBUTIONS.items():
        a, b = _num(reference, key), _num(current, key)
        if len(a) < 20 or len(b) < 20:
            rows.append(
                DriftRow(name, "distribution", None, None, f"n={len(a)}/{len(b)} too small", "OK")
            )
            continue
        v = psi(a, b)
        ks = stats.ks_2samp(a, b)
        rows.append(
            DriftRow(
                name,
                "distribution",
                round(float(np.mean(a)), 4),
                round(float(np.mean(b)), 4),
                f"PSI={v:.3f}, KS={ks.statistic:.3f} (p={ks.pvalue:.2g})",
                psi_status(v),
            )
        )
    for name, fn in RATES.items():
        x1, n1 = _rate(reference, fn)
        x2, n2 = _rate(current, fn)
        if n1 == 0 or n2 == 0:
            rows.append(DriftRow(name, "rate", None, None, "no data", "OK"))
            continue
        r1, r2 = x1 / n1, x2 / n2
        p = two_proportion_p(x1, n1, x2, n2)
        rows.append(
            DriftRow(
                name,
                "rate",
                round(r1, 4),
                round(r2, 4),
                f"Δ={r2 - r1:+.3f} (p={p:.2g})",
                rate_status(r2 - r1, p),
            )
        )
    return rows


def overall_status(rows: list[DriftRow]) -> str:
    return max((r.status for r in rows), key=SEVERITY.__getitem__, default="OK")


def split_by_date(rows: list[dict[str, Any]], ref: tuple[date, date], cur: tuple[date, date]):
    def d(r):
        return date.fromisoformat(r["ts"][:10])

    a = [r for r in rows if ref[0] <= d(r) <= ref[1]]
    b = [r for r in rows if cur[0] <= d(r) <= cur[1]]
    return a, b


def runs_to_rows(run: dict[str, Any]) -> list[dict[str, Any]]:
    """Adapt an eval run JSON to log-like rows so two runs can be compared the same way."""
    out = []
    for c in run["cases"]:
        out.append(
            {
                "latency_ms": c["turn_latencies_ms"][-1],
                "cost_usd": c["cost_usd"],
                "refused": c["observed_behavior"] == "refuse",
                "guardrail_flags": c.get("guardrail_flags", []),
                "eval_scores": {
                    "faithfulness": c["scores"].get("faithfulness"),
                    "answer_relevancy": c["scores"].get("answer_relevancy"),
                    "retrieval_hit": (c["scores"].get("context_precision_labels") or 0) > 0
                    if c["scores"].get("context_precision_labels") is not None
                    else None,
                },
            }
        )
    return out


def render_drift(rows: list[DriftRow], title: str, note: str = "") -> str:
    status = overall_status(rows)
    icon = {"OK": "🟢", "WARN": "🟡", "ALERT": "🔴"}[status]
    lines = [f"# Drift report — {icon} {status}", "", title, ""]
    if note:
        lines += [f"> {note}", ""]
    lines += [
        "| Metric | Type | Reference | Current | Statistic | Status |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        ref = "n/a" if r.reference is None else r.reference
        cur = "n/a" if r.current is None else r.current
        lines.append(f"| {r.metric} | {r.kind} | {ref} | {cur} | {r.statistic} | {r.status} |")
    lines += [
        "",
        "PSI: <0.10 OK, 0.10–0.25 WARN, >0.25 ALERT. Rates: two-proportion z-test, WARN ≥3 pts, ALERT ≥6 pts (p<0.05).",
    ]
    return "\n".join(lines) + "\n"
