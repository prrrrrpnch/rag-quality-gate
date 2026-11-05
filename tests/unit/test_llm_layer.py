import json

from rqg.llm.anthropic_client import to_anthropic_messages
from rqg.llm.base import LLMClient, LLMResponse, ToolCall
from rqg.llm.cache import CachedLLM, DiskCache, cache_key
from rqg.llm.factory import build_app_llm, build_judge_llm
from rqg.llm.mock import MockJudgeLLM, MockSupportLLM, mentioned_products
from rqg.llm.openai_client import to_openai_messages
from rqg.observability.cost import cost_usd, price_for


class CountingLLM(LLMClient):
    model = "counting"

    def __init__(self):
        self.calls = 0

    def complete(self, system, messages, tools=None, max_tokens=1024):
        self.calls += 1
        return LLMResponse(text=f"answer {self.calls}", tool_calls=[ToolCall("1", "t", {"a": 1})])


def test_cache_replays(tmp_path):
    inner = CountingLLM()
    llm = CachedLLM(inner, DiskCache(tmp_path))
    a = llm.complete("sys", [{"role": "user", "content": "hi"}])
    b = llm.complete("sys", [{"role": "user", "content": "hi"}])
    c = llm.complete("sys", [{"role": "user", "content": "other"}])
    assert inner.calls == 2 and a.text == b.text and b.cached and not a.cached
    assert b.tool_calls[0].args == {"a": 1} and c.text == "answer 2"
    assert llm.complete_text("hi", system="sys") == "answer 3"  # different max_tokens => new key


def test_cache_key_stable():
    k1 = cache_key("m", "s", [{"b": 1, "a": 2}], None, 10)
    k2 = cache_key("m", "s", [{"a": 2, "b": 1}], None, 10)
    assert k1 == k2 and k1 != cache_key("m2", "s", [], None, 10)


def test_factory_mock(settings):
    assert isinstance(build_app_llm(settings), MockSupportLLM)
    assert isinstance(build_judge_llm(settings), MockJudgeLLM)
    assert build_judge_llm(settings).complete_text("x") == "{}"


def test_message_conversion():
    msgs = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "name": "t", "args": {}}]},
        {"role": "tool", "tool_call_id": "1", "name": "t", "content": "{}", "is_error": False},
        {"role": "tool", "tool_call_id": "2", "name": "t", "content": "{}", "is_error": True},
    ]
    a = to_anthropic_messages(msgs)
    assert [m["role"] for m in a] == ["user", "assistant", "user"]
    assert len(a[2]["content"]) == 2 and a[1]["content"][0]["type"] == "tool_use"
    o = to_openai_messages("sys", msgs)
    assert o[0]["role"] == "system" and o[2]["tool_calls"][0]["function"]["arguments"] == "{}"


def test_mock_tool_result_messages():
    m = MockSupportLLM()
    for out, needle in [
        ({"ok": False, "error": "invalid_serial"}, "doesn't look valid"),
        ({"ok": False, "error": "not_found"}, "couldn't find"),
        (
            {"ok": False, "error": "unauthorized_serial", "message": "Not registered to you."},
            "Not registered",
        ),
        ({"ok": False, "error": "unauthorized_serial"}, "can't use that serial"),
        ({"ok": False, "error": "weird"}, "couldn't complete"),
    ]:
        msg = {"role": "tool", "name": "check_warranty", "content": json.dumps(out)}
        assert needle in m._from_tool_result(msg)
    assert "went wrong" in m._from_tool_result({"content": "not json"})


def test_mentioned_products():
    assert mentioned_products("AeroPure 500 vs 300") == {"ap300", "ap500"}
    assert mentioned_products("my aeropure") == {"aeropure_any"}
    assert mentioned_products("robot vacuum") == {"robot"}


def test_cost():
    assert cost_usd("claude-haiku-5-5", 1_000_000, 1_000_000) == 0.60
    assert price_for("claude-sonnet-5-5-extra") == (2.0, 10.0)
    assert cost_usd("unknown-model", 100, 100) == 0.0
