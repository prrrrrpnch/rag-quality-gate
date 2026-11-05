"""Tool registry: schemas, authorisation, timeouts and retry (failure recovery)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from rqg.llm.base import ToolSpec
from rqg.tools import service_booking, warranty

SERIAL_IN_TEXT = re.compile(r"\bZH-(?:AP|KT|SV)-\d{6}\b", re.IGNORECASE)


class ToolError(Exception):
    """Raised for tool failures that should be reported back to the model."""


class ToolTimeout(ToolError):
    """The backend did not answer in time."""


TOOL_SPECS = [
    ToolSpec(
        name="check_warranty",
        description="Look up warranty status for a Zephyr Home product by serial number.",
        parameters={
            "type": "object",
            "properties": {"serial": {"type": "string", "description": "e.g. ZH-AP-123456"}},
            "required": ["serial"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="book_service",
        description="Book a technician visit for a product. Slot format YYYY-MM-DDTHH:00.",
        parameters={
            "type": "object",
            "properties": {
                "serial": {"type": "string"},
                "slot": {"type": "string", "description": "e.g. 2026-11-10T10:00"},
            },
            "required": ["serial", "slot"],
            "additionalProperties": False,
        },
    ),
]


@dataclass
class ToolResult:
    name: str
    args: dict[str, Any]
    output: dict[str, Any]
    is_error: bool
    attempts: int
    authorized: bool = True


@dataclass
class ToolRegistry:
    """Executes tools with argument validation, authorisation and retry-on-timeout.

    Authorisation rule (defence against tool abuse / argument injection): a serial may only be
    used if the customer typed it in this session. The model cannot invent or smuggle one in.
    """

    max_retries: int = 1
    _timeout_once_seen: set[str] = field(default_factory=set)

    def _call_backend(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        serial = str(args.get("serial", "")).strip().upper()
        if serial in warranty.ALWAYS_TIMEOUT:
            raise ToolTimeout("backend timeout")
        if serial in warranty.TIMEOUT_ONCE and (name, serial) not in self._timeout_once_seen:
            self._timeout_once_seen.add((name, serial))  # type: ignore[arg-type]
            raise ToolTimeout("backend timeout")
        if name == "check_warranty":
            return warranty.check_warranty(serial)
        if name == "book_service":
            return service_booking.book_service(serial, str(args.get("slot", "")))
        raise ToolError(f"unknown tool {name}")

    def execute(self, name: str, args: dict[str, Any], user_texts: list[str]) -> ToolResult:
        allowed = {s.upper() for t in user_texts for s in SERIAL_IN_TEXT.findall(t)}
        serial = str(args.get("serial", "")).strip().upper()
        extra = set(args) - {"serial", "slot"}
        if name not in {t.name for t in TOOL_SPECS} or extra:
            return ToolResult(name, args, {"ok": False, "error": "invalid_arguments"}, True, 0)
        if serial and serial not in allowed:
            return ToolResult(
                name,
                args,
                {
                    "ok": False,
                    "error": "unauthorized_serial",
                    "message": "Only serial numbers provided by the customer can be used.",
                },
                True,
                0,
                authorized=False,
            )
        attempts = 0
        while True:
            attempts += 1
            try:
                out = self._call_backend(name, args)
                return ToolResult(name, args, out, not out.get("ok", False), attempts)
            except ToolTimeout:
                if attempts > self.max_retries:
                    return ToolResult(
                        name,
                        args,
                        {
                            "ok": False,
                            "error": "timeout",
                            "message": "The service system is not responding.",
                        },
                        True,
                        attempts,
                    )
