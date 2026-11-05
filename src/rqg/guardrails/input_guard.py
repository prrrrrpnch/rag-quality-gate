"""Input guardrail: prompt-injection heuristics and blocked topics.

Heuristics run on several *views* of the input (raw, leetspeak-normalised, base64-decoded
segments) so trivial encodings do not bypass them. See docs/safety.md for what is NOT caught.
"""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass, field

INJECTION_PATTERNS: dict[str, str] = {
    "ignore_instructions": r"\b(ignor\w*|disregard\w*|forget\w*|override\w*|bypass\w*)\b.{0,40}\b(previous|prior|above|earlier|all|your|system|the)\b.{0,20}\b(instructions?|rules?|prompts?|guidelines?|directives?)",
    # added after the first safety-suite run found bypasses (docs/evidence/safety_first_run_before_fix.md)
    "new_instructions": r"\b(new|updated|revised) (instructions?|rules?|directives?)\s*[:\-]|\bsystem override\b",
    "answer_substitution": r"\b(respond|reply|answer|say|output)\b.{0,40}\binstead of (answering|responding|replying)",
    "role_override": r"\byou are (now|no longer)\b|\bfrom now on,? you\b|\bact as (an? )?(unfiltered|unrestricted|evil|dan|jailbroken|developer)",
    "dan_jailbreak": r"\b(dan|do anything now|developer mode|jailbreak|jailbroken|god mode|no restrictions|without (any )?restrictions|unfiltered mode)\b",
    "prompt_extraction": r"\b(system prompt|initial prompt|hidden prompt|your (instructions|rules|prompt|guidelines)|internal reference|canary)\b|\b(repeat|print|show|reveal|output|display|dump)\b.{0,30}\b(above|everything|instructions|rules|configuration|prompt)\b",
    "tag_injection": r"</?\s*(context|system|question|doc|instructions?)\b[^>]*>",
    "fake_authority": r"\b(i am|this is) (the |a |your )?(admin|administrator|developer|zephyr (engineer|staff|employee)|system)\b|\b(admin|maintenance) (mode|override|command)\b",
    "multilingual_ignore": r"ignora (las|todas) .{0,20}instrucciones|ignore[sz]? les instructions|ignoriere (alle|die) .{0,20}anweisungen|nirdesh(on)? ko (bhool|ignore|nazarandaaz)|पिछले निर्देश|निर्देशों को",
}

BLOCKED_TOPICS: dict[str, str] = {
    "medical": r"\b(diagnos\w*|symptoms?|medicines?|medication|dosage|asthma|copd|bronchitis|allerg(y|ies|ic)|cure[sd]?|treat(ment)? for|prescri\w+|disease|doctor|pregnan\w*|lung (health|damage))\b",
    "legal": r"\b(lawsuit|sue|suing|legal advice|lawyer|attorney|consumer court|legal action|file a (case|complaint in court)|court case|legal notice)\b",
    "competitor": r"\b(nimbus appliances|aeromax|pureflow|other brands?|competitors?|rival brands?)\b",
    "politics": r"\b(election|political|politics|prime minister|vote for|political party|government policy|parliament)\b",
    "financial": r"\b(invest(ing|ment)?|stocks?|share price|crypto\w*|bitcoin|mutual funds?)\b",
}

LEET = str.maketrans(
    {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"}
)
_B64 = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")


@dataclass
class InputGuardResult:
    """Outcome of screening one user message."""

    blocked: bool
    category: str | None = None  # "injection" or a blocked-topic name
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


def _views(text: str) -> list[str]:
    base = unicodedata.normalize("NFKC", text)
    base = "".join(ch for ch in base if unicodedata.category(ch) != "Cf")  # zero-width chars
    low = base.lower()
    views = [low, low.translate(LEET), re.sub(r"(?<=\w)[.\-_*](?=\w)", "", low)]
    for m in _B64.finditer(base):
        try:
            dec = base64.b64decode(m.group() + "=" * (-len(m.group()) % 4), validate=True)
            s = dec.decode("utf-8")
            if s.isprintable():
                views.append(s.lower())
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
    return views


def detect_injection(text: str) -> list[str]:
    """Names of injection heuristics that fire on any view of ``text``."""
    hits: list[str] = []
    for view in _views(text):
        for name, pat in INJECTION_PATTERNS.items():
            if name not in hits and re.search(pat, view, re.IGNORECASE):
                hits.append(name)
    return hits


def detect_blocked_topic(text: str) -> str | None:
    for view in _views(text):
        for topic, pat in BLOCKED_TOPICS.items():
            if re.search(pat, view, re.IGNORECASE):
                return topic
    return None


class InputGuard:
    """Blocks prompt-injection attempts and blocked topics before any LLM call."""

    def check(self, text: str) -> InputGuardResult:
        inj = detect_injection(text)
        if inj:
            return InputGuardResult(True, "injection", inj, ["prompt_injection"])
        topic = detect_blocked_topic(text)
        if topic:
            return InputGuardResult(True, topic, [f"blocked_topic:{topic}"], [f"blocked:{topic}"])
        return InputGuardResult(False)

    @staticmethod
    def sanitize_context(text: str) -> tuple[str, bool]:
        """Drop lines of a retrieved chunk that look like injected instructions.

        Defends against *indirect* injection planted inside documents.
        """
        kept, dropped = [], False
        for line in text.splitlines():
            if detect_injection(line) or re.search(
                r"\b(assistant|ai|model)s?\b.{0,40}\b(must|should) (say|reply|respond|output)",
                line,
                re.I,
            ):
                dropped = True
                continue
            kept.append(line)
        return "\n".join(kept), dropped


REFUSAL_BY_CATEGORY = {
    "injection": "I can't help with that request. I can answer questions about Zephyr Home products.",
    "medical": "I can't give medical advice. Please consult a doctor. I can help with how Zephyr Home products work.",
    "legal": "I can't give legal advice. For a formal complaint please contact Zephyr Home support or a qualified professional.",
    "competitor": "I can only help with Zephyr Home products, so I can't compare them with other brands.",
    "politics": "I can't discuss political topics. I can help with Zephyr Home products.",
    "financial": "I can't give financial advice. I can help with Zephyr Home products.",
}
