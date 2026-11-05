"""Shared fixtures. Unit tests always run offline: mock LLM + hashing embedder."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Unit tests must never touch the network or a real key.
os.environ.setdefault("MOCK_LLM", "1")
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "1")
os.environ.setdefault("LANGSMITH_TRACING", "false")


@pytest.fixture
def settings(tmp_path, monkeypatch):
    from rqg.config import Settings, get_settings

    monkeypatch.setenv("MOCK_LLM", "1")
    monkeypatch.setenv("EMBEDDING_BACKEND", os.getenv("TEST_EMBEDDING_BACKEND", "hashing"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))
    get_settings.cache_clear()
    s = Settings()
    yield s
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def hashing_retriever():
    from rqg.rag.retriever import Retriever

    return Retriever.from_corpus(ROOT / "data" / "corpus", backend="hashing")


@pytest.fixture
def assistant(settings, hashing_retriever):
    from rqg.llm.mock import MockSupportLLM
    from rqg.observability.logger import InteractionLogger
    from rqg.rag.assistant import SupportAssistant

    return SupportAssistant(
        MockSupportLLM(), hashing_retriever, settings, InteractionLogger(settings.log_dir)
    )
