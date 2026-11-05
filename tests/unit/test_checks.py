from rqg.evals.checks import check_case, fact_present, observed_behavior
from rqg.evals.dataset import GoldenCase
from rqg.rag.assistant import AssistantResponse, ToolCallRecord

DOCS = {"ap500_specs", "ap300_specs"}


def case(**kw):
    d = dict(
        id="zz-001",
        dataset_version="1.0.0",
        category="single_fact",
        turns=["q"],
        expected_answer="a",
        required_facts=["8 months"],
        expected_sources=["ap500_specs"],
        expected_behavior="answer",
    )
    d.update(kw)
    return GoldenCase.model_validate(d)


def resp(answer, **kw):
    d = dict(
        answer=answer,
        retrieved_contexts=["x"],
        retrieved_doc_ids=["ap500_specs", "ap300_specs"],
        cited_sources=[],
    )
    d.update(kw)
    return AssistantResponse(**d)


def test_fact_present_alternatives_and_normalisation():
    assert fact_present("5–7 working days", "takes 5-7  Working days")
    assert fact_present("a|b", "has b")
    assert fact_present("500 m³/h", "CADR 500 m3/h")
    assert not fact_present("12 months", "6 months")


def test_pass():
    r = resp("About 8 months. [ap500_specs]", cited_sources=["ap500_specs"])
    res = check_case(case(), r, DOCS, 1000)
    assert res.passed and res.citation_format and res.sources


def test_fail_missing_fact_and_forbidden():
    c = case(forbidden_facts=["12 months"])
    r = resp("12 months. [ap500_specs]", cited_sources=["ap500_specs"])
    res = check_case(c, r, DOCS, 1000)
    assert not res.passed and res.missing_facts == ["8 months"] and res.forbidden_hits


def test_citation_must_be_retrieved_and_present():
    r = resp("8 months. [made_up_doc]", cited_sources=["made_up_doc"])
    assert check_case(case(), r, DOCS, 1000).citation_format is False
    r2 = resp("8 months.")
    assert check_case(case(), r2, DOCS, 1000).citation_format is False
    r3 = resp("8 months [EMAIL] [ap500_specs]", cited_sources=["ap500_specs"])
    assert check_case(case(), r3, DOCS, 1000).citation_format


def test_source_match_any_vs_all():
    c = case(expected_sources=["ap500_specs", "ap300_specs"])
    r = resp("8 months [ap500_specs]", cited_sources=["ap500_specs"])
    assert check_case(c, r, DOCS, 1000).sources is False
    c2 = case(expected_sources=["ap500_specs", "ap300_specs"], source_match="any")
    assert check_case(c2, r, DOCS, 1000).sources


def test_refusal_and_over_refusal():
    c = case(
        category="out_of_scope", required_facts=[], expected_sources=[], expected_behavior="refuse"
    )
    ok = resp("I don't know", refused=True)
    assert check_case(c, ok, DOCS, 1000).passed
    assert not check_case(case(), resp("I don't know", refused=True), DOCS, 1000).behavior


def test_tool_checks_and_latency():
    c = case(
        category="tool_call",
        required_facts=[],
        expected_sources=[],
        expected_behavior="tool_call",
        expected_tools=[
            {"name": "book_service", "args": {"serial": "zh-sv-777001", "slot": "2026-11-10 10:00"}}
        ],
    )
    t = ToolCallRecord(
        "book_service", {"serial": "ZH-SV-777001", "slot": "2026-11-10T10:00"}, {}, False, 1, True
    )
    r = resp("booked", tool_calls=[t], latency_ms=5)
    res = check_case(c, r, DOCS, 1000)
    assert res.passed and observed_behavior(r) == "tool_call"
    t_bad = ToolCallRecord(
        "book_service", {"serial": "ZH-SV-777001", "slot": "x"}, {}, True, 1, True
    )
    assert check_case(c, resp("x", tool_calls=[t_bad]), DOCS, 1000).tools is False
    assert (
        check_case(
            case(),
            resp("8 months [ap500_specs]", cited_sources=["ap500_specs"], latency_ms=5000),
            DOCS,
            1000,
        ).latency
        is False
    )


def test_clarify_behaviour():
    c = case(
        category="tool_call", required_facts=[], expected_sources=[], expected_behavior="clarify"
    )
    r = resp("Could you share the serial number?", clarifying=True)
    res = check_case(c, r, DOCS, 1000)
    assert res.passed and res.to_dict()["passed"]
