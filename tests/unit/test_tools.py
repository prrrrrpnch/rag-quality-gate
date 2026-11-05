from datetime import date

import pytest

from rqg.tools.registry import ToolRegistry
from rqg.tools.service_booking import AVAILABLE_SLOTS, book_service
from rqg.tools.warranty import check_warranty


def test_warranty_active_and_expired():
    a = check_warranty("ZH-AP-104233")
    assert a["ok"] and a["status"] == "active" and a["warranty_expires"] == "2027-06-10"
    e = check_warranty("zh-ap-200871")
    assert e["status"] == "expired"
    k = check_warranty("ZH-KT-330417")
    assert k["warranty_expires"] == "2026-07-20" and k["status"] == "expired"
    assert check_warranty("ZH-KT-330417", today=date(2026, 7, 1))["status"] == "active"


@pytest.mark.parametrize("serial", ["12345", "ZH-AP-12", "ZH-XX-123456", ""])
def test_warranty_invalid(serial):
    assert check_warranty(serial)["error"] == "invalid_serial"


def test_warranty_not_found():
    assert check_warranty("ZH-AP-999999")["error"] == "not_found"


def test_booking_paths():
    ok = book_service("ZH-SV-777001", AVAILABLE_SLOTS[0])
    assert ok["ok"] and ok["booking_id"].startswith("SRV-")
    assert ok == book_service("ZH-SV-777001", AVAILABLE_SLOTS[0])  # deterministic id
    assert book_service("ZH-SV-777001", "2026-11-09T10:00")["error"] == "slot_unavailable"
    assert book_service("ZH-SV-777001", "tomorrow")["error"] == "invalid_slot"
    assert book_service("bad", AVAILABLE_SLOTS[0])["error"] == "invalid_serial"
    assert book_service("ZH-AP-999999", AVAILABLE_SLOTS[0])["error"] == "not_found"


def test_registry_authorisation():
    reg = ToolRegistry()
    r = reg.execute("check_warranty", {"serial": "ZH-AP-104233"}, ["my serial is ZH-SV-777001"])
    assert not r.authorized and r.output["error"] == "unauthorized_serial"
    r2 = reg.execute("check_warranty", {"serial": "ZH-AP-104233"}, ["serial zh-ap-104233"])
    assert r2.authorized and r2.output["ok"]


def test_registry_rejects_extra_args_and_unknown_tool():
    reg = ToolRegistry()
    r = reg.execute("check_warranty", {"serial": "ZH-AP-104233", "admin": True}, ["ZH-AP-104233"])
    assert r.output["error"] == "invalid_arguments"
    assert reg.execute("rm_rf", {}, []).output["error"] == "invalid_arguments"


def test_registry_retry_recovers_from_transient_timeout():
    reg = ToolRegistry(max_retries=1)
    r = reg.execute("check_warranty", {"serial": "ZH-AP-000504"}, ["ZH-AP-000504"])
    assert r.output["ok"] and r.attempts == 2


def test_registry_gives_up_after_retries():
    reg = ToolRegistry(max_retries=1)
    r = reg.execute("check_warranty", {"serial": "ZH-KT-000408"}, ["ZH-KT-000408"])
    assert r.is_error and r.output["error"] == "timeout" and r.attempts == 2
