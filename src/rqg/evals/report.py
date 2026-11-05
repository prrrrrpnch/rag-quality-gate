"""Headline KPIs, per-category breakdowns and the markdown report."""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

FAITHFULNESS_PASS = 0.7  # a case is "grounded" when faithfulness >= this


def _mean(xs: list[float]) -> float | None:
    return round(statistics.fmean(xs), 4) if xs else None


def _pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 2)


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def compute_kpis(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """KPIs over a list of case rows (see ``CaseResult``)."""
    answered = [
        c
        for c in cases
        if c["observed_behavior"] == "answer" and c["scores"].get("faithfulness") is not None
    ]
    faith = [c["scores"]["faithfulness"] for c in answered]
    rel = [
        c["scores"]["answer_relevancy"]
        for c in answered
        if c["scores"].get("answer_relevancy") is not None
    ]
    should = [c for c in cases if c["expected_behavior"] == "refuse"]
    refused = [c for c in cases if c["observed_behavior"] == "refuse"]
    tp = [c for c in should if c["observed_behavior"] == "refuse"]
    not_should = [c for c in cases if c["expected_behavior"] != "refuse"]
    over = [c for c in not_should if c["observed_behavior"] == "refuse"]
    tool_cases = [c for c in cases if c["expected_behavior"] == "tool_call"]
    tool_ok = [
        c for c in tool_cases if c["checks"]["tools"] and c["checks"]["required_facts"] is not False
    ]
    with_src = [
        c
        for c in cases
        if c["checks"].get("sources") is not None
        or c["scores"].get("context_precision_labels") is not None
    ]
    hit = [c for c in with_src if (c["scores"].get("context_precision_labels") or 0) > 0]
    lat = [x for c in cases for x in c["turn_latencies_ms"]]
    n_turns = len(lat)
    cp = [
        c["scores"]["context_precision_labels"]
        for c in cases
        if c["scores"].get("context_precision_labels") is not None
    ]
    cr = [
        c["scores"]["context_recall_labels"]
        for c in cases
        if c["scores"].get("context_recall_labels") is not None
    ]
    sim = [
        c["scores"]["ragas_string_similarity"]
        for c in answered
        if c["scores"].get("ragas_string_similarity") is not None
    ]

    kpis: dict[str, Any] = {
        "n_cases": len(cases),
        "pass_rate": _rate(sum(c["passed"] for c in cases), len(cases)),
        "hallucination_rate": round(1 - sum(f >= FAITHFULNESS_PASS for f in faith) / len(faith), 4)
        if faith
        else None,
        "groundedness_mean": _mean(faith),
        "relevance_mean": _mean(rel),
        "refusal_recall": _rate(len(tp), len(should)),
        "refusal_precision": _rate(len(tp), len(refused)),
        "over_refusal_rate": _rate(len(over), len(not_should)),
        "tool_success_rate": _rate(len(tool_ok), len(tool_cases)),
        "retrieval_hit_rate": _rate(len(hit), len(with_src)),
        "context_precision_mean": _mean(cp),
        "context_recall_mean": _mean(cr),
        "ragas_string_similarity_mean": _mean(sim),
        "latency_p50_ms": _pct(lat, 0.5),
        "latency_p95_ms": _pct(lat, 0.95),
        "cost_per_100_queries_usd": round(sum(c["cost_usd"] for c in cases) / n_turns * 100, 6)
        if n_turns
        else None,
        "app_input_tokens": sum(c["input_tokens"] for c in cases),
        "app_output_tokens": sum(c["output_tokens"] for c in cases),
        "n_answered_scored": len(answered),
    }
    agree = [
        (c["scores"]["faithfulness"] >= FAITHFULNESS_PASS)
        == (c["scores"]["ragas_faithfulness"] >= FAITHFULNESS_PASS)
        for c in answered
        if c["scores"].get("ragas_faithfulness") is not None
    ]
    kpis["deepeval_ragas_faithfulness_agreement"] = _rate(sum(agree), len(agree))
    return kpis


def per_category(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in cases:
        groups[c["category"]].append(c)
    out = {}
    for cat in sorted(groups):
        g = groups[cat]
        k = compute_kpis(g)
        out[cat] = {
            "n": len(g),
            "pass_rate": k["pass_rate"],
            "groundedness_mean": k["groundedness_mean"],
            "behavior_accuracy": _rate(sum(c["checks"]["behavior"] for c in g), len(g)),
        }
    return out


def _fmt(v: Any) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.4f}".rstrip("0").rstrip(".") if abs(v) < 1000 else f"{v:,.0f}"
    return str(v)


HEADLINE = [
    ("pass_rate", "Pass rate (all deterministic checks)"),
    ("hallucination_rate", "Hallucination rate (1 - faithfulness pass rate)"),
    ("groundedness_mean", "Groundedness (mean faithfulness)"),
    ("relevance_mean", "Answer relevance (mean)"),
    ("refusal_recall", "Refusal recall (refused / should refuse)"),
    ("refusal_precision", "Refusal precision"),
    ("over_refusal_rate", "Over-refusal rate"),
    ("tool_success_rate", "Tool success rate"),
    ("retrieval_hit_rate", "Retrieval hit rate"),
    ("context_precision_mean", "Context precision (label-based)"),
    ("context_recall_mean", "Context recall (label-based)"),
    ("ragas_string_similarity_mean", "Ragas NonLLMStringSimilarity (mean)"),
    ("deepeval_ragas_faithfulness_agreement", "DeepEval vs Ragas faithfulness agreement"),
    ("latency_p50_ms", "Latency p50 (ms)"),
    ("latency_p95_ms", "Latency p95 (ms)"),
    ("cost_per_100_queries_usd", "Cost per 100 queries (USD, app model)"),
]


def render_markdown(run: dict[str, Any]) -> str:
    m, k = run["meta"], run["kpis"]
    lines = [f"# Eval report — {m['run_id']}", ""]
    if m["mode"] == "mock":
        lines += [
            "> **MOCK MODE.** App model = deterministic extractive mock, judge = heuristic. "
            "These numbers test the pipeline and the gate, not a real LLM.",
            "",
        ]
    lines += [
        f"- mode: `{m['mode']}` · subset: `{m['subset']}` · cases: {m['n_cases']} · dataset: v{m['dataset_version']}",
        f"- git: `{m['git_sha']}` · prompt: `{m['prompt_version']}` · app model: `{m['app_model']}` · judge: `{m['judge']}` (x{m['judge_repeats']})",
        f"- embeddings: `{m['embedding_backend']}` · wall time: {m['wall_time_s']} s",
        "",
        "## Headline KPIs",
        "",
        "| KPI | Value |",
        "|---|---|",
    ]
    lines += [f"| {label} | {_fmt(k.get(key))} |" for key, label in HEADLINE]
    lines += [
        "",
        "## Per category",
        "",
        "| Category | n | Pass rate | Behaviour accuracy | Groundedness |",
        "|---|---|---|---|---|",
    ]
    for cat, v in run["per_category"].items():
        lines.append(
            f"| {cat} | {v['n']} | {_fmt(v['pass_rate'])} | {_fmt(v['behavior_accuracy'])} | {_fmt(v['groundedness_mean'])} |"
        )
    failing = [c for c in run["cases"] if not c["passed"]]
    lines += ["", f"## Failing cases ({len(failing)})", ""]
    if failing:
        lines += [
            "| Case | Category | Expected → observed | Failed checks | Answer (truncated) |",
            "|---|---|---|---|---|",
        ]
        for c in failing:
            failed = [
                n
                for n in (
                    "required_facts",
                    "forbidden_facts",
                    "sources",
                    "behavior",
                    "tools",
                    "citation_format",
                    "latency",
                )
                if c["checks"][n] is False
            ]
            ans = c["answer"].replace("|", "/").replace("\n", " ")
            ans = ans[:90] + ("…" if len(ans) > 90 else "")
            lines.append(
                f"| {c['case_id']} | {c['category']} | {c['expected_behavior']} → {c['observed_behavior']} | {', '.join(failed)} | {ans} |"
            )
    lines += [
        "",
        "## Cost",
        "",
        f"- App tokens: {k['app_input_tokens']:,} in / {k['app_output_tokens']:,} out; "
        f"cost this run: ${sum(c['cost_usd'] for c in run['cases']):.4f}",
        f"- Judge calls: {m['judge_calls']}",
    ]
    if m["mode"] == "mock":
        from rqg.observability.cost import PRICING

        p = PRICING["claude-haiku-5-5"]
        est = (k["app_input_tokens"] * p[0] + k["app_output_tokens"] * p[1]) / 1e6
        lines.append(
            f"- Estimated app-model cost of the same traffic on claude-haiku-5-5 (mock token counts are "
            f"len/4 approximations): ${est:.4f}"
        )
    return "\n".join(lines) + "\n"
