"""Deterministic (non-LLM) checks. These are the hard assertions of the gate.

They never call a model, so they are free, fast and do not flake.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from rqg.evals.dataset import GoldenCase
from rqg.rag.assistant import AssistantResponse
from rqg.rag.text import normalize

_BRACKET = re.compile(r"\[([^\]\n]{1,60})\]")
PLACEHOLDERS = {"EMAIL", "PHONE", "CUSTOMER_ID", "SERIAL", "NATIONAL_ID", "CARD"}


def _norm(s: str) -> str:
    return normalize(s).replace("’", "'")


def fact_present(fact: str, text: str) -> bool:
    """``fact`` may hold alternatives separated by ``|``; any one must appear."""
    t = _norm(text)
    return any(_norm(alt) in t for alt in fact.split("|") if alt.strip())


def observed_behavior(r: AssistantResponse) -> str:
    if r.tool_calls:
        return "tool_call"
    if r.refused:
        return "refuse"
    if r.clarifying:
        return "clarify"
    return "answer"


@dataclass
class CheckResult:
    """``None`` means the check does not apply to this case."""

    required_facts: bool | None
    forbidden_facts: bool | None
    sources: bool | None
    behavior: bool
    tools: bool | None
    citation_format: bool | None
    latency: bool
    observed_behavior: str
    missing_facts: list[str]
    forbidden_hits: list[str]

    @property
    def passed(self) -> bool:
        return all(v is not False for v in self.values().values())

    def values(self) -> dict[str, bool | None]:
        keys = (
            "required_facts",
            "forbidden_facts",
            "sources",
            "behavior",
            "tools",
            "citation_format",
            "latency",
        )
        return {k: getattr(self, k) for k in keys}

    def to_dict(self) -> dict:
        d = asdict(self)
        d["passed"] = self.passed
        return d


def _norm_args(args: dict) -> dict:
    return {k: str(v).strip().upper().replace(" ", "T") for k, v in args.items()}


def check_case(
    case: GoldenCase, r: AssistantResponse, known_doc_ids: set[str], latency_budget_ms: float
) -> CheckResult:
    ans = r.answer
    missing = [f for f in case.required_facts if not fact_present(f, ans)]
    forbidden = [f for f in case.forbidden_facts if fact_present(f, ans)]
    obs = observed_behavior(r)

    # behaviour: tool_call cases must call a tool; others must match exactly
    behavior_ok = obs == case.expected_behavior

    sources: bool | None = None
    if case.expected_behavior == "answer" and case.expected_sources:
        cited = set(r.cited_sources)
        exp = set(case.expected_sources)
        sources = exp <= cited if case.source_match == "all" else bool(exp & cited)

    tools: bool | None = None
    if case.expected_tools:
        called = [(t.name, _norm_args(t.args)) for t in r.tool_calls if t.authorized]
        tools = all((e.name, _norm_args(e.args)) in called for e in case.expected_tools)
    elif case.expected_behavior in {"answer", "refuse", "clarify"}:
        tools = not r.tool_calls

    citation: bool | None = None
    if obs == "answer":
        brackets = [b for b in _BRACKET.findall(ans) if b not in PLACEHOLDERS]
        valid = all(b in known_doc_ids and b in r.retrieved_doc_ids for b in brackets)
        citation = valid and len(brackets) > 0

    return CheckResult(
        required_facts=(not missing) if case.required_facts else None,
        forbidden_facts=(not forbidden) if case.forbidden_facts else None,
        sources=sources,
        behavior=behavior_ok,
        tools=tools,
        citation_format=citation,
        latency=r.latency_ms <= latency_budget_ms,
        observed_behavior=obs,
        missing_facts=missing,
        forbidden_hits=forbidden,
    )
