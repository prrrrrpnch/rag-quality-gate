"""Content-addressed disk cache for LLM calls.

Key = sha256(model + system + messages + tools + max_tokens). A cached response is replayed
byte-for-byte, which (a) keeps API cost down on re-runs and (b) makes a re-run of the same
code + data reproducible even though the provider itself is not deterministic.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from rqg.llm.base import LLMClient, LLMResponse, ToolSpec


def cache_key(model: str, system: str, messages: list[dict[str, Any]], tools: Any, mt: int) -> str:
    payload = json.dumps(
        {"m": model, "s": system, "msgs": messages, "t": tools, "mt": mt},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DiskCache:
    """Tiny JSON-file cache, sharded by the first two hex chars of the key."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.hits = 0
        self.misses = 0

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        p = self._path(key)
        if p.exists():
            self.hits += 1
            return json.loads(p.read_text(encoding="utf-8"))
        self.misses += 1
        return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)


class CachedLLM(LLMClient):
    """Wraps any LLMClient with the disk cache. Cached responses report ``cached=True``."""

    def __init__(self, inner: LLMClient, cache: DiskCache, namespace: str = "") -> None:
        self.inner = inner
        self.cache = cache
        self.namespace = namespace
        self.model = inner.model

    def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        tool_dicts = [t.__dict__ for t in tools] if tools else None
        key = cache_key(self.namespace + self.model, system, messages, tool_dicts, max_tokens)
        hit = self.cache.get(key)
        if hit is not None:
            resp = LLMResponse.from_dict(hit)
            resp.cached = True
            return resp
        resp = self.inner.complete(system, messages, tools, max_tokens)
        self.cache.set(key, resp.to_dict())
        return resp
