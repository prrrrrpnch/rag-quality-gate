import pytest

from rqg.guardrails.pii import find_pii, redact


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("mail me at priya.sharma+zh@example.co.in", "email"),
        ("call 98765 43210", "phone"),
        ("call +91-9876543210 today", "phone"),
        ("my number is 9876543210", "phone"),
        ("US line +1 415 555 0132", "phone"),
        ("customer CUST-004512 here", "customer_id"),
        ("serial ZH-AP-104233", "serial"),
        ("aadhaar 1234 5678 9012", "national_id"),
        ("card 4111 1111 1111 1111", "card"),
    ],
)
def test_each_pattern_detected(text, kind):
    kinds = [f.kind for f in find_pii(text)]
    assert kind in kinds


@pytest.mark.parametrize(
    "text",
    [
        "The AeroPure 300 costs ₹14,990 and weighs 5.2 kg.",
        "Filter life is about 2,000 hours.",
        "Slot 2026-11-10T10:00 is free.",
        "CADR 500 m³/h, 26 dB to 58 dB.",
    ],
)
def test_no_false_positives_on_specs(text):
    assert find_pii(text) == []


def test_card_requires_luhn():
    assert "card" not in {f.kind for f in find_pii("card 4111 1111 1111 1112")}


def test_redact_and_allowlist():
    text = "Serial ZH-AP-104233, email a@b.com, phone 9876543210"
    red, findings = redact(text)
    assert red == "Serial [SERIAL], email [EMAIL], phone [PHONE]"
    assert len(findings) == 3
    red2, _ = redact(text, allow={"zh-ap-104233"})
    assert "ZH-AP-104233" in red2 and "[EMAIL]" in red2


def test_kind_filter():
    red, f = redact("a@b.com 9876543210", kinds={"email"})
    assert red == "[EMAIL] 9876543210" and len(f) == 1
