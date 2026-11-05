"""Judges: a deterministic heuristic judge (mock mode) and repeated-median helpers.

The heuristic judge is NOT a substitute for an LLM judge. It exists so the whole pipeline,
the report and the gate can run offline and deterministically. Its definitions:

* faithfulness      — share of answer sentences whose content words are >= 60 % covered by
                      the retrieved contexts (citations stripped). N/A for refusals/clarify.
* answer_relevancy  — share of the question's content words that appear in the answer or the
                      titles of the cited documents (synonym-normalised).
* context_precision — average precision of the retrieved doc ranking, using
                      ``expected_sources`` as relevance labels (label-based, no LLM).
* context_recall    — share of ``required_facts`` that appear in the retrieved contexts.
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Callable

from rqg.evals.checks import fact_present
from rqg.evals.dataset import GoldenCase
from rqg.llm.mock import canon
from rqg.rag.assistant import AssistantResponse
from rqg.rag.text import content_tokens, split_sentences

_CIT = re.compile(r"\[[^\]]+\]")


def median_of(fn: Callable[[], float | None], n: int) -> tuple[float | None, list[float]]:
    """Run a noisy scorer ``n`` times; return (median, all samples). ``None`` samples dropped."""
    samples = [s for s in (fn() for _ in range(max(1, n))) if s is not None]
    if not samples:
        return None, []
    return float(statistics.median(samples)), samples


def average_precision(retrieved: list[str], relevant: set[str]) -> float | None:
    if not relevant:
        return None
    hits, total = 0, 0.0
    seen: set[str] = set()
    for i, d in enumerate(retrieved, 1):
        if d in relevant and d not in seen:
            hits += 1
            total += hits / i
        seen.add(d)
    return total / len(relevant)


class HeuristicJudge:
    """Deterministic lexical judge used in mock mode."""

    name = "heuristic-judge-v1"
    coverage = 0.6

    def faithfulness(self, answer: str, contexts: list[str]) -> float | None:
        ctx = set()
        for c in contexts:
            ctx |= canon(content_tokens(c))
        claims = [s for s in split_sentences(_CIT.sub("", answer)) if canon(content_tokens(s))]
        if not claims:
            return None
        ok = 0
        for s in claims:
            toks = canon(content_tokens(s))
            if len(toks & ctx) / len(toks) >= self.coverage:
                ok += 1
        return ok / len(claims)

    def answer_relevancy(self, question: str, answer: str, cited_titles: list[str]) -> float | None:
        q = canon(content_tokens(question))
        if not q:
            return None
        a = canon(content_tokens(answer + " " + " ".join(cited_titles)))
        return len(q & a) / len(q)

    @staticmethod
    def context_precision(case: GoldenCase, r: AssistantResponse) -> float | None:
        return average_precision(r.retrieved_doc_ids, set(case.expected_sources))

    @staticmethod
    def context_recall(case: GoldenCase, r: AssistantResponse) -> float | None:
        if not case.required_facts or not r.retrieved_contexts:
            return None
        blob = " ".join(r.retrieved_contexts)
        return sum(fact_present(f, blob) for f in case.required_facts) / len(case.required_facts)
