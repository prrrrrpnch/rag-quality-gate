"""Ragas second-opinion metrics (non-deprecated ``ragas.metrics.collections`` API, 0.4.3).

* Real mode: Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall with a Claude
  judge via ``llm_factory(provider="anthropic")`` and local ONNX embeddings.
* Mock mode: only Ragas' non-LLM ``NonLLMStringSimilarity`` (answer vs reference) runs, so
  the integration is exercised offline. LLM-based Ragas scores are reported as n/a.
"""

from __future__ import annotations

from typing import Any

from ragas.embeddings.base import BaseRagasEmbedding
from ragas.metrics.collections import NonLLMStringSimilarity


class LocalRagasEmbedding(BaseRagasEmbedding):
    """Adapts our local embedder to Ragas' embedding interface (no API key needed)."""

    def __init__(self, embedder: Any) -> None:
        self.embedder = embedder

    def embed_text(self, text: str, **kwargs: Any) -> list[float]:
        return self.embedder.embed([text])[0]

    async def aembed_text(self, text: str, **kwargs: Any) -> list[float]:
        return self.embed_text(text)


class RagasScorer:
    """Computes Ragas scores for one case. ``llm`` is None in mock mode."""

    def __init__(self, llm: Any = None, embeddings: BaseRagasEmbedding | None = None) -> None:
        self.string_sim = NonLLMStringSimilarity()
        self.llm_metrics: dict[str, Any] = {}
        if llm is not None:
            from ragas.metrics.collections import (
                AnswerRelevancy,
                ContextPrecision,
                ContextRecall,
                Faithfulness,
            )

            self.llm_metrics = {
                "faithfulness": Faithfulness(llm=llm),
                "context_precision": ContextPrecision(llm=llm),
                "context_recall": ContextRecall(llm=llm),
            }
            if embeddings is not None:
                self.llm_metrics["answer_relevancy"] = AnswerRelevancy(
                    llm=llm, embeddings=embeddings
                )

    @classmethod
    def for_settings(cls, settings: Any, embedder: Any = None) -> RagasScorer:
        if settings.use_mock:
            return cls()
        from ragas.llms import llm_factory

        if settings.llm_provider == "anthropic":
            import anthropic

            key = settings.anthropic_api_key.get_secret_value()
            llm = llm_factory(
                settings.judge_model, provider="anthropic", client=anthropic.Anthropic(api_key=key)
            )
        else:
            from openai import OpenAI

            key = settings.openai_api_key.get_secret_value()
            client = OpenAI(api_key=key, base_url=settings.openai_base_url)
            llm = llm_factory(settings.judge_model, provider="openai", client=client)
        emb = LocalRagasEmbedding(embedder) if embedder is not None else None
        return cls(llm=llm, embeddings=emb)

    def score(
        self, question: str, answer: str, contexts: list[str], reference: str
    ) -> dict[str, float | None]:
        out: dict[str, float | None] = {
            "ragas_string_similarity": float(
                self.string_sim.score(reference=reference, response=answer).value
            )
        }
        for name in ("faithfulness", "answer_relevancy", "context_precision", "context_recall"):
            m = self.llm_metrics.get(name)
            if m is None:
                out[f"ragas_{name}"] = None
                continue
            try:
                if name == "faithfulness":
                    res = m.score(user_input=question, response=answer, retrieved_contexts=contexts)
                elif name == "answer_relevancy":
                    res = m.score(user_input=question, response=answer)
                elif name == "context_precision":
                    res = m.score(
                        user_input=question, reference=reference, retrieved_contexts=contexts
                    )
                else:
                    res = m.score(
                        user_input=question, retrieved_contexts=contexts, reference=reference
                    )
                out[f"ragas_{name}"] = float(res.value)
            except Exception:  # a judge failure must not crash the run; it is reported as n/a
                out[f"ragas_{name}"] = None
        return out
