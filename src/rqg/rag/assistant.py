"""The system under test: a grounded, tool-using, guarded support assistant."""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from rqg.config import Settings, get_settings
from rqg.guardrails.input_guard import REFUSAL_BY_CATEGORY, InputGuard
from rqg.guardrails.output_guard import OutputGuard
from rqg.llm.base import LLMClient
from rqg.observability.cost import cost_usd
from rqg.observability.logger import InteractionLogger
from rqg.observability.tracing import traceable
from rqg.rag.prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_user_turn
from rqg.rag.retriever import RetrievedChunk, Retriever
from rqg.rag.text import contextualize
from rqg.tools.registry import SERIAL_IN_TEXT, TOOL_SPECS, ToolRegistry

CITATION = re.compile(r"\[([a-z0-9_]+)\]")
REFUSAL_MARKERS = re.compile(
    r"isn't covered in the zephyr home manuals|not covered in the (zephyr home )?manuals|"
    r"i don't know|i do not know|i can't (help|give|discuss|share|compare)|i can only help|"
    r"i cannot (help|give|discuss|share)|not in the manuals",
    re.IGNORECASE,
)
CLARIFY_MARKERS = re.compile(
    r"\?\s*$|which (model|time slot|slot|product)|could you (share|tell|provide)|please (share|provide)",
    re.IGNORECASE,
)


@dataclass
class ToolCallRecord:
    name: str
    args: dict[str, Any]
    output: dict[str, Any]
    is_error: bool
    attempts: int
    authorized: bool


@dataclass
class AssistantResponse:
    """Everything an evaluator or a log line needs about one turn."""

    answer: str
    retrieved_contexts: list[str]
    retrieved_doc_ids: list[str]
    cited_sources: list[str]
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    refused: bool = False
    clarifying: bool = False
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    guardrail_flags: list[str] = field(default_factory=list)
    trace_id: str = ""
    session_id: str = ""
    model: str = ""
    prompt_version: str = PROMPT_VERSION
    llm_calls: int = 0
    cached_calls: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_refusal(text: str) -> bool:
    return bool(REFUSAL_MARKERS.search(text))


def is_clarifying(text: str) -> bool:
    return not is_refusal(text) and bool(CLARIFY_MARKERS.search(text.strip()))


class SupportAssistant:
    """Input guard -> retrieve -> LLM (+tool loop) -> output guard -> log.

    Sessions are in-memory and isolated: history for one ``session_id`` is never visible to
    another (tested by the cross-session leakage attacks).
    """

    MAX_TOOL_ROUNDS = 4

    def __init__(
        self,
        llm: LLMClient,
        retriever: Retriever,
        settings: Settings | None = None,
        logger: InteractionLogger | None = None,
        guardrails: bool = True,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm = llm
        self.retriever = retriever
        self.logger = logger
        self.guardrails = guardrails
        self.system_prompt = system_prompt
        self.input_guard = InputGuard()
        self.output_guard = OutputGuard()
        self.sessions: dict[str, list[dict[str, Any]]] = {}
        self.session_user_texts: dict[str, list[str]] = {}
        self.tools = ToolRegistry(max_retries=self.settings.tool_max_retries)

    def reset(self, session_id: str | None = None) -> None:
        if session_id is None:
            self.sessions.clear()
            self.session_user_texts.clear()
        else:
            self.sessions.pop(session_id, None)
            self.session_user_texts.pop(session_id, None)

    @traceable("retrieve", run_type="retriever")
    def _retrieve(self, query: str) -> list[RetrievedChunk]:
        return self.retriever.retrieve(query, self.settings.top_k)

    @traceable("generate", run_type="llm")
    def _generate(self, messages: list[dict[str, Any]]):
        return self.llm.complete(self.system_prompt, messages, TOOL_SPECS, max_tokens=1024)

    @traceable("support_assistant.ask")
    def ask(
        self, user_message: str, session_id: str | None = None, customer_id: str | None = None
    ) -> AssistantResponse:
        """Answer one user turn within a session (optionally authenticated as ``customer_id``)."""
        t0 = time.perf_counter()
        session_id = session_id or uuid.uuid4().hex[:12]
        trace_id = uuid.uuid4().hex
        history = self.sessions.setdefault(session_id, [])
        user_texts = self.session_user_texts.setdefault(session_id, [])
        flags: list[str] = []

        if self.guardrails:
            g = self.input_guard.check(user_message)
            if g.blocked:
                answer = REFUSAL_BY_CATEGORY[g.category or "injection"]
                resp = AssistantResponse(
                    answer=answer,
                    retrieved_contexts=[],
                    retrieved_doc_ids=[],
                    cited_sources=[],
                    refused=True,
                    guardrail_flags=g.flags,
                    trace_id=trace_id,
                    session_id=session_id,
                    model="guardrail",
                )
                return self._finish(resp, user_message, history, user_texts, answer, t0)

        query = contextualize(user_texts, user_message)
        chunks = self._retrieve(query)
        if self.guardrails:
            clean = []
            for c in chunks:
                text, dropped = InputGuard.sanitize_context(c.text)
                if dropped and "indirect_injection_stripped" not in flags:
                    flags.append("indirect_injection_stripped")
                clean.append(RetrievedChunk(**{**c.__dict__, "text": text}))
            chunks = clean

        user_texts_now = [*user_texts, user_message]
        messages = [*history, {"role": "user", "content": build_user_turn(user_message, chunks)}]
        tool_records: list[ToolCallRecord] = []
        in_tok = out_tok = calls = cached = 0
        cost = 0.0
        model = self.llm.model
        resp_text = ""
        for _ in range(self.MAX_TOOL_ROUNDS + 1):
            r = self._generate(messages)
            calls += 1
            cached += int(r.cached)
            model = r.model or model
            in_tok += r.input_tokens
            out_tok += r.output_tokens
            cost += cost_usd(model, r.input_tokens, r.output_tokens)
            if not r.tool_calls:
                resp_text = r.text
                break
            messages.append(
                {
                    "role": "assistant",
                    "content": r.text,
                    "tool_calls": [t.to_dict() for t in r.tool_calls],
                }
            )
            for tc in r.tool_calls:
                res = self.tools.execute(tc.name, tc.args, user_texts_now, customer_id)
                tool_records.append(
                    ToolCallRecord(
                        res.name, res.args, res.output, res.is_error, res.attempts, res.authorized
                    )
                )
                if not res.authorized:
                    flags.append("unauthorized_tool_call_blocked")
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": json.dumps(res.output),
                        "is_error": res.is_error,
                    }
                )
        else:
            resp_text = (
                "Sorry, I couldn't complete that request. Please contact Zephyr Home support."
            )
            flags.append("tool_loop_limit")

        answer = resp_text
        if self.guardrails:
            allowed = {s.upper() for t in user_texts_now for s in SERIAL_IN_TEXT.findall(t)}
            og = self.output_guard.check(resp_text, allowed_values=allowed)
            answer = og.text
            flags.extend(og.flags)

        cited = list(dict.fromkeys(CITATION.findall(answer)))
        resp = AssistantResponse(
            answer=answer,
            retrieved_contexts=[c.text for c in chunks],
            retrieved_doc_ids=[c.doc_id for c in chunks],
            cited_sources=cited,
            tool_calls=tool_records,
            refused=is_refusal(answer),
            clarifying=is_clarifying(answer),
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
            guardrail_flags=flags,
            trace_id=trace_id,
            session_id=session_id,
            model=model,
            llm_calls=calls,
            cached_calls=cached,
        )
        return self._finish(resp, user_message, history, user_texts, answer, t0)

    def _finish(
        self,
        resp: AssistantResponse,
        user_message: str,
        history: list[dict[str, Any]],
        user_texts: list[str],
        answer: str,
        t0: float,
    ) -> AssistantResponse:
        # Only plain text goes into history: old contexts are re-retrieved, not replayed.
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": answer})
        user_texts.append(user_message)
        resp.latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        if self.logger:
            self.logger.log(
                user_input=user_message,
                answer=answer,
                session_id=resp.session_id,
                trace_id=resp.trace_id,
                prompt_version=resp.prompt_version,
                model=resp.model,
                latency_ms=resp.latency_ms,
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                cost_usd=resp.cost_usd,
                guardrail_flags=resp.guardrail_flags,
                refused=resp.refused,
                tools_called=[t.name for t in resp.tool_calls],
                retrieved_doc_ids=resp.retrieved_doc_ids,
            )
        return resp


def build_assistant(
    settings: Settings | None = None,
    corpus_dir=None,
    guardrails: bool = True,
    log: bool = True,
    system_prompt: str = SYSTEM_PROMPT,
) -> SupportAssistant:
    """Factory used by the CLI, eval runner, safety runner and HTTP wrapper."""
    from rqg.llm.factory import build_app_llm

    s = settings or get_settings()
    retriever = Retriever.from_corpus(
        corpus_dir or s.corpus_dir, s.embedding_backend, s.chunk_size, s.chunk_overlap
    )
    logger = InteractionLogger(s.log_dir) if log else None
    return SupportAssistant(build_app_llm(s), retriever, s, logger, guardrails, system_prompt)
