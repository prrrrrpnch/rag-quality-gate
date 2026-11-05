"""Environment-driven configuration (pydantic-settings).

Every knob is an env var so CI, local runs and the real-LLM workflow share one code path.
"""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime settings. Read from env vars and an optional `.env` file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_file_encoding="utf-8")

    # --- mode -------------------------------------------------------------------------------
    mock_llm: bool = Field(default=False, description="Force the deterministic fake LLM/judge.")
    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    app_model: str = "claude-haiku-5-5"
    judge_model: str = "claude-sonnet-5-5"
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None
    app_effort: Literal["low", "medium", "high"] = "low"
    judge_effort: Literal["low", "medium", "high"] = "low"
    judge_refusal_fallback: bool = True

    # --- RAG ----------------------------------------------------------------------------------
    corpus_dir: Path = REPO_ROOT / "data" / "corpus"
    embedding_backend: Literal["onnx", "hashing"] = "onnx"
    top_k: int = 4
    chunk_size: int = 700
    chunk_overlap: int = 120
    prompt_version: str = "v1"

    # --- eval ---------------------------------------------------------------------------------
    golden_path: Path = REPO_ROOT / "data" / "golden" / "golden_v1.jsonl"
    attacks_path: Path = REPO_ROOT / "data" / "attacks" / "attacks_v1.jsonl"
    judge_repeats: int = 3
    latency_budget_ms: int = 8000
    cache_dir: Path = REPO_ROOT / ".cache" / "llm"
    reports_dir: Path = REPO_ROOT / "reports"
    baselines_dir: Path = REPO_ROOT / "baselines"

    # --- observability ------------------------------------------------------------------------
    log_dir: Path = REPO_ROOT / "logs"
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "rag-quality-gate"

    # --- tools --------------------------------------------------------------------------------
    tool_timeout_s: float = 2.0
    tool_max_retries: int = 1

    @property
    def has_real_key(self) -> bool:
        """True when the configured provider has an API key available."""
        key = self.anthropic_api_key if self.llm_provider == "anthropic" else self.openai_api_key
        return bool(key and key.get_secret_value())

    @property
    def use_mock(self) -> bool:
        """Mock mode is used when forced, or automatically when no key exists."""
        return self.mock_llm or not self.has_real_key

    @property
    def mode(self) -> str:
        return "mock" if self.use_mock else "real"

    @property
    def tracing_enabled(self) -> bool:
        key = self.langsmith_api_key
        return self.langsmith_tracing and bool(key and key.get_secret_value())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton (call `get_settings.cache_clear()` in tests)."""
    return Settings()


def git_sha(short: bool = True) -> str:
    """Current git sha, or 'unknown' outside a git checkout."""
    try:
        args = ["git", "rev-parse", "--short" if short else "HEAD", "HEAD"]
        if not short:
            args = ["git", "rev-parse", "HEAD"]
        out = subprocess.run(args, capture_output=True, text=True, check=True, cwd=REPO_ROOT)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
