"""LangSmith tracing that degrades to a silent no-op.

``traceable(...)`` wraps ``langsmith.traceable`` only when ``LANGSMITH_TRACING=true`` *and*
``LANGSMITH_API_KEY`` are set. Otherwise it returns the function unchanged, so there is no
network call, no warning and no overhead.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def tracing_enabled() -> bool:
    return os.getenv("LANGSMITH_TRACING", "").lower() == "true" and bool(
        os.getenv("LANGSMITH_API_KEY")
    )


def default_metadata() -> dict[str, str]:
    from rqg.config import git_sha
    from rqg.rag.prompts import PROMPT_VERSION

    return {
        "git_sha": git_sha(),
        "prompt_version": PROMPT_VERSION,
        "dataset_version": os.getenv("RQG_DATASET_VERSION", "n/a"),
    }


def traceable(name: str, run_type: str = "chain") -> Callable[[F], F]:
    """Decorator: LangSmith span when configured, identity otherwise."""

    def deco(fn: F) -> F:
        if not tracing_enabled():
            return fn
        from langsmith import traceable as ls_traceable

        meta = default_metadata()
        return ls_traceable(  # type: ignore[no-any-return]
            name=name, run_type=run_type, metadata=meta, tags=[f"prompt:{meta['prompt_version']}"]
        )(fn)

    return deco
