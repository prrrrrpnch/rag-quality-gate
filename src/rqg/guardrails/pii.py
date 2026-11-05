"""Regex PII detection and redaction (deterministic, no LLM).

Patterns are intentionally conservative to avoid redacting prices, dates and spec numbers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    # Indian mobile (+91 optional) and generic international numbers with a leading '+'
    "phone": re.compile(
        r"(?<![\w-])(?:(?:\+91|0091)[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)"
        r"|\+\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4}(?!\d)"
    ),
    "customer_id": re.compile(r"\bCUST-\d{6}\b", re.IGNORECASE),
    "serial": re.compile(r"\bZH-(?:AP|KT|SV)-\d{6}\b", re.IGNORECASE),
    "national_id": re.compile(r"(?<!\d)\d{4}\s\d{4}\s\d{4}(?!\d)"),
    "card": re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"),
}

PLACEHOLDER = {k: f"[{k.upper()}]" for k in PATTERNS}


@dataclass(frozen=True)
class PIIFinding:
    kind: str
    value: str
    start: int
    end: int


def _luhn_ok(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def find_pii(text: str, kinds: set[str] | None = None) -> list[PIIFinding]:
    """Return non-overlapping PII findings, earliest first."""
    found: list[PIIFinding] = []
    for kind, pat in PATTERNS.items():
        if kinds is not None and kind not in kinds:
            continue
        for m in pat.finditer(text):
            if kind == "card" and not _luhn_ok(m.group()):
                continue
            found.append(PIIFinding(kind, m.group(), m.start(), m.end()))
    found.sort(key=lambda f: (f.start, -(f.end - f.start)))
    out: list[PIIFinding] = []
    last_end = -1
    for f in found:
        if f.start >= last_end:
            out.append(f)
            last_end = f.end
    return out


def redact(
    text: str, allow: set[str] | None = None, kinds: set[str] | None = None
) -> tuple[str, list[PIIFinding]]:
    """Replace PII with ``[KIND]`` placeholders. Values in ``allow`` (upper-cased) are kept."""
    allow = {a.upper() for a in (allow or set())}
    findings = [f for f in find_pii(text, kinds) if f.value.upper() not in allow]
    for f in sorted(findings, key=lambda f: f.start, reverse=True):
        text = text[: f.start] + PLACEHOLDER[f.kind] + text[f.end :]
    return text, findings
