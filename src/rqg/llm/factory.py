"""Build app / judge clients from settings (mock when no key, always cached)."""

from __future__ import annotations

from rqg.config import Settings
from rqg.llm.base import LLMClient
from rqg.llm.cache import CachedLLM, DiskCache
from rqg.llm.mock import MockJudgeLLM, MockSupportLLM


def _real_client(settings: Settings, model: str, judge: bool) -> LLMClient:
    if settings.llm_provider == "anthropic":
        from rqg.llm.anthropic_client import AnthropicClient

        key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        return AnthropicClient(
            model,
            api_key=key,
            effort=settings.judge_effort if judge else settings.app_effort,
            refusal_fallback=judge and settings.judge_refusal_fallback,
        )
    from rqg.llm.openai_client import OpenAICompatClient

    key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
    return OpenAICompatClient(model, key, settings.openai_base_url)


def build_app_llm(settings: Settings, cache: DiskCache | None = None) -> LLMClient:
    """The model behind the support assistant."""
    inner = (
        MockSupportLLM() if settings.use_mock else _real_client(settings, settings.app_model, False)
    )
    if settings.use_mock:
        return inner  # the mock is deterministic and free; caching adds nothing
    return CachedLLM(inner, cache or DiskCache(settings.cache_dir), namespace="app:")


def build_judge_llm(settings: Settings, cache: DiskCache | None = None) -> LLMClient:
    """The model used by LLM-judged metrics (real mode only)."""
    if settings.use_mock:
        return MockJudgeLLM()
    inner = _real_client(settings, settings.judge_model, True)
    return CachedLLM(inner, cache or DiskCache(settings.cache_dir), namespace="judge:")
