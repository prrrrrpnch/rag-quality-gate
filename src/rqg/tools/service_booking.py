"""Mock service-booking backend."""

from __future__ import annotations

import hashlib
import re

from rqg.tools.warranty import REGISTRY, SERIAL_RE

SLOT_RE = re.compile(r"^2026-\d{2}-\d{2}T\d{2}:00$")

AVAILABLE_SLOTS = [
    "2026-11-10T10:00",
    "2026-11-10T14:00",
    "2026-11-11T12:00",
    "2026-11-12T16:00",
]
FULLY_BOOKED = {"2026-11-09T10:00", "2026-11-09T12:00", "2026-11-09T14:00"}


def book_service(serial: str, slot: str) -> dict:
    """Book a technician visit. Deterministic booking ids."""
    serial = serial.strip().upper()
    slot = slot.strip()
    if not SERIAL_RE.match(serial):
        return {"ok": False, "error": "invalid_serial", "message": "Serial format is invalid."}
    if serial not in REGISTRY:
        return {"ok": False, "error": "not_found", "message": "No product with that serial."}
    if not SLOT_RE.match(slot):
        return {
            "ok": False,
            "error": "invalid_slot",
            "message": "Slots use the format YYYY-MM-DDTHH:00.",
            "available_slots": AVAILABLE_SLOTS,
        }
    if slot not in AVAILABLE_SLOTS:
        return {
            "ok": False,
            "error": "slot_unavailable",
            "message": f"The slot {slot} is not available.",
            "available_slots": AVAILABLE_SLOTS,
        }
    booking_id = "SRV-" + hashlib.sha1(f"{serial}|{slot}".encode()).hexdigest()[:6].upper()
    return {"ok": True, "booking_id": booking_id, "serial": serial, "slot": slot}
