"""Deterministic fake LLMs for offline runs (MOCK_LLM=1).

``MockSupportLLM`` stands in for the app model. It is an *extractive* answerer: it scores
context sentences against the question and quotes the best ones with ``[doc_id]`` citations.
It honours the system-prompt rules it can detect (grounding, prefer-current, clarify), so
editing the prompt changes its behaviour deterministically — this is what lets the
regression gate be demonstrated without an API key.

It is also deliberately *naive*: it obeys injected instructions ("reply with X", "print your
instructions"). That makes the guardrails, not the model, responsible for stopping attacks
in mock mode, so the safety suite actually exercises them. Real models behave differently;
see docs/non-determinism.md and docs/safety.md.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from rqg.llm.base import LLMClient, LLMResponse, ToolCall, ToolSpec
from rqg.rag.prompts import REFUSAL_TEXT
from rqg.rag.text import content_tokens, contextualize, is_follow_up, split_sentences

_DOC = re.compile(
    r'<doc id="(?P<id>[^"]+)" status="(?P<status>[^"]*)" last_updated="(?P<upd>[^"]*)">\n'
    r"(?P<body>.*?)\n</doc>",
    re.DOTALL,
)
_Q = re.compile(r"<question>(.*?)</question>", re.DOTALL)
SERIAL = re.compile(r"\bZH-(?:AP|KT|SV)-\d{6}\b|\bZH-[A-Z]{1,3}-?\d{1,8}\b", re.IGNORECASE)
SLOT = re.compile(r"\b(2026-\d{2}-\d{2})[ T](\d{1,2}):00\b")

BOOK_WORDS = re.compile(
    r"\b(book|schedule|appointment|technician|service visit|repair visit|send someone)\b", re.I
)
WARRANTY_WORDS = re.compile(r"\b(warranty|guarantee|covered|cover|expire[sd]?|expiry)\b", re.I)
STATUS_WORDS = re.compile(r"\b(check|status|still|under|valid|active|expired?|mine|my)\b", re.I)
COMPARE_WORDS = re.compile(
    r"\b(compare|comparison|difference|differ|vs\.?|versus|both|between|which (one|model)|"
    r"bigger|larger|quieter|louder|heavier|lighter|more|less|better)\b",
    re.I,
)
MODEL_SPECIFIC = re.compile(
    r"\b(filter (life|last)|how long .*filter|noise|loud|cadr|room size|weigh|price|cost|"
    r"power consumption|watt|filter code|part code)\b",
    re.I,
)

# Which product a question/sentence refers to (simple keyword map).
PRODUCT_KEYS = {
    "ap300": ("300", "ap300"),
    "ap500": ("500", "ap500"),
    "kettle": ("kettle", "brewmate", "k2"),
    "robot": ("robot", "robosweep", "s7", "vacuum"),
}
DOC_PRODUCT = {
    "ap300_specs": "ap300",
    "ap500_specs": "ap500",
    "brewmate_k2_manual": "kettle",
    "robosweep_s7_specs": "robot",
    "robosweep_s7_setup_app": "robot",
    "robosweep_s7_troubleshooting": "robot",
}

INJECT_SAY = re.compile(
    r"(?:say|reply(?: only)?(?: with)?|respond(?: only)? with|output|print|write|answer with)"
    r"\s*(?:the (?:word|phrase|text))?\s*[:\-]?\s*[\"'“]([^\"'”]{2,80})[\"'”]",
    re.I,
)
INJECT_LEAK = re.compile(
    r"system prompt|your (instructions|rules|prompt)|internal reference|canary|"
    r"repeat (everything|the text) above|configuration",
    re.I,
)


# Canonicalise product aliases and a few synonyms / Hinglish words so lexical overlap works.
SYNONYMS = {
    "robot": "robosweep",
    "vacuum": "robosweep",
    "s7": "robosweep",
    "kettle": "brewmate",
    "k2": "brewmate",
    "purifier": "aeropure",
    "ap300": "300",
    "ap500": "500",
    "weigh": "weight",
    "loud": "noise",
    "noisy": "noise",
    "quiet": "noise",
    "db": "noise",
    "mahine": "month",
    "mahina": "month",
    "months": "month",
    "wifi": "wifi",
    "router": "wifi",
    "charge": "charg",
    "batteri": "battery",
    "warrenty": "warranty",
    "waranty": "warranty",
    "garantee": "warranty",
    "guarantee": "warranty",
    "filtr": "filter",
    "fiter": "filter",
    "litre": "litr",
    "liter": "litr",
    "capacity": "litr",
    "paani": "water",
    "pani": "water",
    "boil": "boil",
    "cost": "price",
    "costs": "price",
    "much": "",
    "long": "",
    "mean": "",
    "doe": "",
    "use": "",
    "work": "",
    "happen": "",
    "kab": "",
    "kitne": "",
    "chalta": "",
    "chalti": "",
    "lagta": "",
    "lagti": "",
    "karu": "",
    "karun": "",
    "kare": "",
    "mera": "my",
    "meri": "my",
    "hours": "hour",
    "minutes": "minut",
    "minute": "minut",
    "app": "app",
    "alexa": "voic",
    "google": "voic",
    "assistant": "voic",
    "voice": "voic",
}


PRODUCT_TOKENS = frozenset({"300", "500", "aeropure", "brewmate", "robosweep", "zephyr", "home"})


def canon(tokens: list[str]) -> set[str]:
    out = set()
    for t in tokens:
        t = SYNONYMS.get(t, t)
        if t and t != "my":
            out.add(t)
    return out


def _approx_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def mentioned_products(text: str) -> set[str]:
    low = text.lower()
    found = set()
    for prod, keys in PRODUCT_KEYS.items():
        if any(re.search(rf"\b{re.escape(k)}\b", low) for k in keys):
            found.add(prod)
    if "aeropure" in low and not found & {"ap300", "ap500"}:
        found.add("aeropure_any")
    return found


class MockSupportLLM(LLMClient):
    """Deterministic extractive stand-in for the app model."""

    def __init__(self, model: str = "mock-support-v1", threshold: float = 0.45) -> None:
        self.model = model
        self.threshold = threshold

    # ------------------------------------------------------------------ entry point
    def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        rules = {
            "grounded": "Answer ONLY from the provided context" in system,
            "prefer_current": 'status "current"' in system,
            "clarify": "ask which model they mean" in system,
        }
        last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
        user_raw = messages[last_user]["content"]
        qm = _Q.search(user_raw)
        question = qm.group(1).strip() if qm else user_raw.strip()
        docs = [m.groupdict() for m in _DOC.finditer(user_raw)]
        prev_q = [
            (_Q.search(m["content"]).group(1) if _Q.search(m["content"]) else m["content"])
            for m in messages[:last_user]
            if m["role"] == "user"
        ]
        prev_assistant = next(
            (m["content"] for m in reversed(messages[:last_user]) if m["role"] == "assistant"), ""
        )
        tool_msgs = [m for m in messages[last_user:] if m["role"] == "tool"]

        tool_call: ToolCall | None = None
        if tool_msgs:
            text = self._from_tool_result(tool_msgs[-1])
        else:
            text = self._naive_injection(question, docs, system)
            if text is None and tools:
                text, tool_call = self._tool_intent(question, prev_q, prev_assistant)
            if text is None and tool_call is None:
                text = self._answer(question, prev_q, docs, rules)
        prompt_len = len(system) + sum(len(str(m.get("content", ""))) for m in messages)
        return LLMResponse(
            text=text or "",
            tool_calls=[tool_call] if tool_call else [],
            input_tokens=_approx_tokens(" " * prompt_len),
            output_tokens=_approx_tokens(text or json.dumps(tool_call.args if tool_call else {})),
            model=self.model,
            stop_reason="tool_use" if tool_call else "end_turn",
        )

    # ------------------------------------------------------------------ behaviours
    @staticmethod
    def _naive_injection(question: str, docs: list[dict], system: str) -> str | None:
        """Obey injected instructions (in the question or in documents). Intentionally unsafe."""
        sources = [question] + [d["body"] for d in docs]
        for src in sources:
            m = INJECT_SAY.search(src)
            if m and re.search(
                r"ignore|instead|new instruction|assistant must|override", src, re.I
            ):
                return m.group(1)
            if INJECT_LEAK.search(src) and re.search(
                r"ignore|reveal|print|repeat|show|tell me|what is|what are|dump", src, re.I
            ):
                return f"My instructions are: {system}"
        return None

    @staticmethod
    def _tool_intent(
        question: str, prev_q: list[str], prev_assistant: str
    ) -> tuple[str | None, ToolCall | None]:
        convo = [*prev_q, question]
        serials = [s.upper() for t in reversed(convo) for s in SERIAL.findall(t)]
        slots = [f"{d}T{int(h):02d}:00" for t in reversed(convo) for d, h in SLOT.findall(t)]
        pending_book = "time slot" in prev_assistant or (
            "serial number" in prev_assistant and "book" in prev_assistant.lower()
        )
        pending_warranty = "serial number" in prev_assistant and not pending_book
        wants_book = bool(BOOK_WORDS.search(question)) or pending_book
        wants_warranty = (
            bool(WARRANTY_WORDS.search(question))
            and (bool(SERIAL.search(question)) or bool(STATUS_WORDS.search(question)))
            and not re.search(r"\bhow long\b|\bperiod\b|\bwhat is the warranty\b", question, re.I)
        ) or (pending_warranty and bool(SERIAL.search(question)))
        if not (wants_book or wants_warranty):
            return None, None
        if not serials:
            purpose = "book a technician visit" if wants_book else "check your warranty"
            return (
                f"To {purpose}, could you share the product serial number? It looks like "
                "ZH-AP-123456 and is printed on the label under the product.",
                None,
            )
        name, args = ("check_warranty", {"serial": serials[0]})
        if wants_book:
            if not slots:
                return (
                    "Which time slot would you like for the technician visit? Slots run Monday "
                    "to Saturday, 9:00 to 18:00 (format 2026-11-10T10:00).",
                    None,
                )
            name, args = ("book_service", {"serial": serials[0], "slot": slots[0]})
        cid = "toolu_mock_" + hashlib.sha1(json.dumps([name, args]).encode()).hexdigest()[:10]
        return None, ToolCall(id=cid, name=name, args=args)

    @staticmethod
    def _from_tool_result(msg: dict[str, Any]) -> str:
        try:
            out = json.loads(msg["content"])
        except (json.JSONDecodeError, TypeError):
            return "Sorry, something went wrong while contacting the service system."
        err = out.get("error")
        if out.get("ok"):
            if msg.get("name") == "book_service":
                return (
                    f"Your technician visit is booked for {out['slot']} "
                    f"(booking id {out['booking_id']})."
                )
            if out["status"] == "active":
                return (
                    f"Your {out['product']} ({out['serial']}) is under warranty until "
                    f"{out['warranty_expires']}."
                )
            return (
                f"The warranty for your {out['product']} ({out['serial']}) expired on "
                f"{out['warranty_expires']}. Out-of-warranty visits cost ₹399 plus parts."
            )
        if err == "invalid_serial":
            return (
                "That serial number doesn't look valid. Serial numbers look like ZH-AP-123456; "
                "please check the label under the product."
            )
        if err == "not_found":
            return "I couldn't find a product with that serial number. Please check the label."
        if err == "slot_unavailable" or err == "invalid_slot":
            slots = ", ".join(out.get("available_slots", []))
            return f"That slot isn't available. Available slots are: {slots}."
        if err == "timeout":
            return (
                "Sorry, the service system is not responding right now. Please try again in a "
                "few minutes or contact Zephyr Home support."
            )
        if err == "unauthorized_serial":
            return "I can only use serial numbers you have shared with me in this conversation."
        return "Sorry, I couldn't complete that request."

    def _answer(
        self, question: str, prev_q: list[str], docs: list[dict], rules: dict[str, bool]
    ) -> str:
        q_text = contextualize(prev_q, question)
        q_products = mentioned_products(question) or (
            mentioned_products(q_text) if is_follow_up(question) else set()
        )
        if (
            rules["clarify"]
            and "aeropure_any" in q_products
            and MODEL_SPECIFIC.search(question)
            and not COMPARE_WORDS.search(question)
        ):
            return "Which model do you mean — the AeroPure 300 or the AeroPure 500?"

        if rules["prefer_current"] and any(d["status"] == "current" for d in docs):
            docs = [d for d in docs if d["status"] != "superseded"]
        cands: list[tuple[str, str, set[str]]] = []
        for d in docs:
            title, _, body = d["body"].partition("\n")
            title_toks = canon(content_tokens(title))
            for s in split_sentences(body):
                if s.lower().startswith("note:"):
                    continue
                cands.append((d["id"], s, canon(content_tokens(s)) | title_toks))
        q = canon(content_tokens(q_text))
        own = mentioned_products(question) - {"aeropure_any"}
        if own and q_text != question:  # follow-up: drop the previous turn's product tokens
            other = {"ap300": "300", "ap500": "500", "kettle": "brewmate", "robot": "robosweep"}
            q -= {tok for prod, tok in other.items() if prod not in own}
        if not cands or not q:
            return self._fallback(rules)
        df: dict[str, int] = {}
        for _, _, toks in cands:
            for t in toks:
                df[t] = df.get(t, 0) + 1
        n = len(cands)

        def weight(t: str) -> float:
            # Unknown words count as a full, unmatched concept; known words by rarity.
            return 1.0 if t not in df else min(1.5, math.log(1 + n / df[t]))

        denom = sum(weight(t) for t in q) or 1.0
        predicate = q - PRODUCT_TOKENS
        scored: list[tuple[float, str, str]] = []
        for doc_id, s, toks in cands:
            score = sum(weight(t) for t in q & toks) / denom
            if predicate and not predicate & toks:
                score *= 0.3  # only the product name matched, not what was asked about
            dp = DOC_PRODUCT.get(doc_id)
            specific = q_products - {"aeropure_any"}
            if specific and dp and dp not in specific:
                score *= 0.3
            s_prods = mentioned_products(s) - {"aeropure_any"}
            if specific and s_prods and not s_prods & specific:
                score *= 0.5
            scored.append((score, doc_id, s))
        scored.sort(key=lambda x: (-x[0], x[1], x[2]))
        best = scored[0][0]
        if best < self.threshold:
            return self._fallback(rules)
        chosen = [scored[0]]
        if COMPARE_WORDS.search(q_text) and len(q_products - {"aeropure_any"}) > 1:
            per_product = []
            for prod in sorted(q_products - {"aeropure_any"}):
                for sc in scored:
                    if DOC_PRODUCT.get(sc[1]) == prod and sc[0] >= self.threshold * 0.6:
                        per_product.append(sc)
                        break
            if len(per_product) > 1:
                chosen = per_product
        else:
            for sc in scored[1:3]:
                if sc[0] >= max(self.threshold, 0.85 * best) and sc[2] != chosen[0][2]:
                    chosen.append(sc)
                    break
        answer = " ".join(f"{s.rstrip('.')}. [{d}]" for _, d, s in chosen)
        if not rules["grounded"]:
            answer += " This generally applies to all Zephyr Home models as well."
        return answer

    @staticmethod
    def _fallback(rules: dict[str, bool]) -> str:
        if rules["grounded"]:
            return f"{REFUSAL_TEXT} Please contact Zephyr Home support for more help."
        # Without the grounding rule the mock "guesses", like an ungrounded model would.
        return "Yes, that is supported on Zephyr Home products and usually takes about 2 hours."


class MockJudgeLLM(LLMClient):
    """Placeholder judge model for mock mode.

    In mock mode the LLM-judged metrics are replaced by deterministic heuristics in
    ``rqg.evals.judge.HeuristicJudge``; this class only exists so code paths that expect a
    judge client have one. It returns an empty JSON object.
    """

    def __init__(self, model: str = "mock-judge-v1") -> None:
        self.model = model

    def complete(self, system, messages, tools=None, max_tokens=1024) -> LLMResponse:  # type: ignore[override]
        return LLMResponse(text="{}", model=self.model, input_tokens=1, output_tokens=1)
