"""Anthropic Messages API client (app model and judge).

Note on temperature: current Claude models reject sampling parameters (``temperature``,
``top_p``, ``top_k``) and the installed SDK no longer exposes them. Reproducibility therefore
comes from the disk cache plus repeated-judge medians, not from temperature 0.
See docs/non-determinism.md.
"""

from __future__ import annotations

import json
from typing import Any

import anthropic

from rqg.llm.base import LLMClient, LLMResponse, ToolCall, ToolSpec

FALLBACK_BETA = "server-side-fallback-2026-07-01"


def to_anthropic_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert neutral messages to Messages-API format (tool results grouped per turn)."""
    out: list[dict[str, Any]] = []
    for m in messages:
        if m["role"] == "user":
            out.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant":
            blocks: list[dict[str, Any]] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m.get("tool_calls", []):
                blocks.append(
                    {"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["args"]}
                )
            out.append({"role": "assistant", "content": blocks or m.get("content", "")})
        elif m["role"] == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": m["tool_call_id"],
                "content": m["content"],
                "is_error": bool(m.get("is_error")),
            }
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
    return out


class AnthropicClient(LLMClient):
    """Thin wrapper over ``client.messages.create`` returning ``LLMResponse``."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        effort: str = "low",
        refusal_fallback: bool = False,
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self.effort = effort
        self.refusal_fallback = refusal_fallback
        self.client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=3)

    def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": to_anthropic_messages(messages),
            "output_config": {"effort": self.effort},
        }
        if tools:
            kwargs["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                    "strict": True,
                }
                for t in tools
            ]
        if self.refusal_fallback:
            resp = self.client.beta.messages.create(
                betas=[FALLBACK_BETA], fallbacks="default", **kwargs
            )
        else:
            resp = self.client.messages.create(**kwargs)
        texts, calls = [], []
        for block in resp.content:
            if block.type == "text":
                texts.append(block.text)
            elif block.type == "tool_use":
                args = block.input if isinstance(block.input, dict) else json.loads(block.input)
                calls.append(ToolCall(id=block.id, name=block.name, args=args))
        return LLMResponse(
            text="\n".join(texts).strip(),
            tool_calls=calls,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            model=resp.model,
            stop_reason=resp.stop_reason or "",
        )
