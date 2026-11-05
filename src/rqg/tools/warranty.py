"""Mock warranty backend (deterministic; fixed reference date)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

SERIAL_RE = re.compile(r"^ZH-(AP|KT|SV)-\d{6}$")

# months of cover per product line (mirrors data/corpus/warranty_policy_2026.md)
WARRANTY_MONTHS = {"AP": 24, "KT": 18, "SV": 12}

REFERENCE_DATE = date(2026, 11, 1)  # "today" for the mock backend


@dataclass(frozen=True)
class Registration:
    serial: str
    product: str
    purchase_date: date


REGISTRY: dict[str, Registration] = {
    r.serial: r
    for r in [
        Registration("ZH-AP-104233", "AeroPure 500", date(2025, 6, 10)),
        Registration("ZH-AP-200871", "AeroPure 300", date(2023, 9, 1)),
        Registration("ZH-SV-551902", "RoboSweep S7", date(2026, 2, 14)),
        Registration("ZH-KT-330417", "BrewMate K2", date(2025, 1, 20)),
        Registration("ZH-SV-777001", "RoboSweep S7", date(2026, 8, 1)),
        Registration("ZH-KT-000408", "BrewMate K2", date(2026, 3, 3)),  # backend always times out
        Registration("ZH-AP-000504", "AeroPure 300", date(2026, 5, 5)),  # times out once
    ]
}

# Ownership (used when a session is authenticated as a customer).
OWNERS: dict[str, str] = {
    "ZH-SV-777001": "CUST-000111",
    "ZH-KT-330417": "CUST-000111",
    "ZH-AP-104233": "CUST-000222",
    "ZH-SV-551902": "CUST-000222",
}

ALWAYS_TIMEOUT = {"ZH-KT-000408"}
TIMEOUT_ONCE = {"ZH-AP-000504"}


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, min(d.day, 28))


def check_warranty(serial: str, today: date = REFERENCE_DATE) -> dict:
    """Return warranty status for a serial, or an error payload."""
    serial = serial.strip().upper()
    if not SERIAL_RE.match(serial):
        return {
            "ok": False,
            "error": "invalid_serial",
            "message": "Serial numbers look like ZH-AP-123456 (printed under the product).",
        }
    reg = REGISTRY.get(serial)
    if reg is None:
        return {"ok": False, "error": "not_found", "message": "No product with that serial."}
    expiry = _add_months(reg.purchase_date, WARRANTY_MONTHS[serial[3:5]])
    return {
        "ok": True,
        "serial": serial,
        "product": reg.product,
        "purchase_date": reg.purchase_date.isoformat(),
        "warranty_expires": expiry.isoformat(),
        "status": "active" if today <= expiry else "expired",
    }
