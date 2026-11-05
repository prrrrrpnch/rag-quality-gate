"""Provider-neutral message, tool and response types.

Conversation messages are plain dicts in one neutral shape:

* ``{"role": "user", "content": str}``
* ``{"role": "assistant", "content": str, "tool_calls": [ToolCall-as-dict, ...]}``
* ``{"role": "tool", "tool_call_id": str, "name": str, "content": str, "is_error": bool}``

Each provider client converts this shape to its own wire format.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    """A tool the model may call (JSON-schema parameters)."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class ToolCall:
    """A tool invocation requested by the model."""

    id: str
    name: str
    args: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LLMResponse:
    """Normalised model output."""

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    stop_reason: str = "end_turn"
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> LLMResponse:
        d = dict(d)
        d["tool_calls"] = [ToolCall(**tc) for tc in d.get("tool_calls", [])]
        return cls(**d)


class LLMClient(ABC):
    """Interface every provider (real or mock) implements."""

    model: str

    @abstractmethod
    def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Return one model turn for the given conversation."""

    def complete_text(self, prompt: str, system: str = "", max_tokens: int = 2048) -> str:
        """Convenience single-turn text call (used by judges)."""
        return self.complete(system, [{"role": "user", "content": prompt}], None, max_tokens).text
