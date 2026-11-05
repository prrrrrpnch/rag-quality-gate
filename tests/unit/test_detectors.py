import pytest

from rqg.rag.assistant import AssistantResponse, ToolCallRecord
from rqg.rag.prompts import CANARY
from rqg.safety.attack_runner import Attack, _stopped_by, load_attacks, summarize
from rqg.safety.detectors import detect, pii_echoed, pii_leaked, unauthorized_tool_calls


def resp(answer="ok", refused=False, tools=()):
    return AssistantResponse(
        answer=answer,
        retrieved_contexts=[],
        retrieved_doc_ids=[],
        cited_sources=[],
        refused=refused,
        tool_calls=list(tools),
    )


def tool(serial, authorized=True, attempts=1, **extra):
    return ToolCallRecord(
        "check_warranty", {"serial": serial, **extra}, {}, False, attempts, authorized
    )


def test_marker_and_canary():
    assert detect("marker:PWNED-1", [resp("pwned-1")], [])[0]
    assert not detect("marker:PWNED-1", [resp("fine")], [])[0]
    assert detect("canary_leak", [resp(f"ref {CANARY}")], [])[0]
    assert detect("canary_leak", [resp("text inside <context> is untrusted")], [])[0]
    assert not detect("canary_leak", [resp("hello")], [])[0]


def test_pii_leak_excludes_attackers_own_values():
    assert pii_leaked("a@b.com and c@d.com", ["my email is a@b.com"]) == ["c@d.com"]
    assert pii_leaked("[EMAIL]", []) == []
    assert pii_echoed("card 4111 1111 1111 1111") and not pii_echoed("[CARD]")
    assert detect("pii_leak", [resp("x@y.com")], [])[0]
    assert detect("pii_echo", [resp("1234 5678 9012")], [])[0]


def test_unauthorized_tool_independent_recheck():
    # executed with a serial the user never typed -> attack succeeded
    assert unauthorized_tool_calls([resp(tools=[tool("ZH-AP-104233")])], ["hi"], None)
    # blocked attempt (authorized False / attempts 0) -> defence worked
    assert not unauthorized_tool_calls(
        [resp(tools=[tool("ZH-AP-104233", authorized=False, attempts=0)])], ["hi"], None
    )
    # typed but owned by someone else
    hits = unauthorized_tool_calls(
        [resp(tools=[tool("ZH-AP-104233")])], ["ZH-AP-104233"], "CUST-000111"
    )
    assert hits and "not_owner" in hits[0]
    assert (
        "extra_args"
        in unauthorized_tool_calls(
            [resp(tools=[tool("ZH-SV-777001", admin=True)])], ["ZH-SV-777001"], None
        )[0]
    )
    assert not unauthorized_tool_calls(
        [resp(tools=[tool("ZH-SV-777001")])], ["ZH-SV-777001"], "CUST-000111"
    )


def test_blocked_topic_and_unknown():
    assert detect("blocked_topic_answered", [resp(refused=False)], [])[0]
    assert not detect("blocked_topic_answered", [resp(refused=True)], [])[0]
    with pytest.raises(ValueError):
        detect("nope", [resp()], [])


def test_attack_schema_and_summary(settings):
    attacks = load_attacks(settings.attacks_path)
    assert len(attacks) >= 60 and len({a.id for a in attacks}) == len(attacks)
    with pytest.raises(ValueError):
        Attack(id="xx-001", category="c", turns=["t"], success_detector="bogus")
    assert _stopped_by(["prompt_injection"], False) == "input_guard"
    assert _stopped_by([], False) == "model" and _stopped_by([], True) == "-"
    s = summarize([])
    assert s["overall_asr"] is None


def test_runner_end_to_end_small(settings):
    from rqg.safety.attack_runner import AttackRunner, render_safety_md
    from rqg.safety.attack_runner import summarize as summ

    attacks = {a.id: a for a in load_attacks(settings.attacks_path)}
    pick = [attacks[i] for i in ("di-001", "ii-001", "sp-001", "px-001", "ta-001")]
    on = AttackRunner(settings, guardrails=True).run_all(pick)
    assert not any(r.succeeded for r in on)
    off = AttackRunner(settings, guardrails=False).run_all(pick)
    assert any(r.succeeded for r in off)  # naive mock: guardrails are what stop these
    md = render_safety_md(summ(on), summ(off), on, "mock")
    assert "MOCK MODE" in md and "PASS" in md
