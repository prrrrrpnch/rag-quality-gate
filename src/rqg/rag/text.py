"""Small text utilities shared by retrieval, the mock LLM and heuristic judges."""

from __future__ import annotations

import re

STOPWORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "and",
        "or",
        "but",
        "if",
        "then",
        "than",
        "that",
        "this",
        "these",
        "those",
        "it",
        "its",
        "it's",
        "i",
        "me",
        "my",
        "we",
        "our",
        "you",
        "your",
        "he",
        "she",
        "they",
        "them",
        "their",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "how",
        "when",
        "where",
        "why",
        "do",
        "does",
        "did",
        "doing",
        "can",
        "could",
        "should",
        "would",
        "will",
        "shall",
        "may",
        "might",
        "must",
        "have",
        "has",
        "had",
        "having",
        "not",
        "no",
        "yes",
        "so",
        "as",
        "at",
        "by",
        "from",
        "about",
        "into",
        "over",
        "under",
        "again",
        "there",
        "here",
        "any",
        "some",
        "all",
        "each",
        "more",
        "most",
        "other",
        "such",
        "only",
        "own",
        "same",
        "too",
        "very",
        "just",
        "also",
        "please",
        "tell",
        "know",
        "need",
        "want",
        "get",
        "got",
        "am",
        "pls",
        "plz",
        "hai",
        "kya",
        "ka",
        "ki",
        "ke",
        "ko",
        "se",
        "mein",
        "hain",
        "hota",
        "karna",
        "kaise",
        "batao",
        "bata",
        "kitna",
        "kitni",
        "aur",
        "ya",
        "bhi",
    ]
)

_TOKEN = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)?", re.IGNORECASE)


def normalize(text: str) -> str:
    """Lowercase and collapse whitespace; unify a few unicode variants."""
    t = text.lower().replace("’", "'").replace("–", "-").replace("—", "-").replace("m²", "m2")
    t = t.replace("m³", "m3").replace("°c", " c").replace("wi-fi", "wifi")
    return re.sub(r"\s+", " ", t).strip()


def stem(tok: str) -> str:
    """Very small suffix stripper (good enough for lexical overlap)."""
    for suf in ("ing", "edly", "ed", "es", "s"):
        if len(tok) > 4 and tok.endswith(suf):
            return tok[: -len(suf)]
    return tok


def content_tokens(text: str) -> list[str]:
    """Tokens with stopwords removed and light stemming."""
    return [stem(t) for t in _TOKEN.findall(normalize(text)) if t not in STOPWORDS]


def split_sentences(text: str) -> list[str]:
    """Split markdown-ish text into sentences / bullet items."""
    out: list[str] = []
    for line in text.splitlines():
        line = line.strip().lstrip("-*0123456789. ").strip()
        if not line or line.startswith("#") or line.startswith("---"):
            continue
        line = line.replace("**", "")
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", line)
        out.extend(p.strip() for p in parts if len(p.strip()) > 2)
    return out


_FOLLOW_UP = re.compile(
    r"^(and|what about|how about|also|same for|or|aur|toh|then)\b|\b(it|its|that|this|they|them|"
    r"those|the other|the second|the first|second one|first one|bigger one|smaller one|one)\b",
    re.IGNORECASE,
)


def is_follow_up(question: str) -> bool:
    """Heuristic: does this turn depend on the previous one for its subject?"""
    return bool(_FOLLOW_UP.search(question.strip())) or len(content_tokens(question)) <= 2


def contextualize(previous_user_turns: list[str], question: str) -> str:
    """Prepend the previous user turn to follow-ups so retrieval has the subject."""
    if previous_user_turns and is_follow_up(question):
        return f"{previous_user_turns[-1]} {question}"
    return question
