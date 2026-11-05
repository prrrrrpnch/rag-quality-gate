#!/usr/bin/env python
"""Generate a SYNTHETIC interaction log set (fixed seed) for the SQL and drift demos.

Every row has ``"synthetic": true`` and a ``synthetic-`` session id. This is NOT production
data. Planted on purpose:

* a latency regression in the last 3 days (p95 roughly x1.6),
* a higher refusal rate in the last 3 days,
* 5 rows whose ``answer_redacted`` still contains a raw email or phone (a simulated
  redaction bug) — the SQL PII check must find exactly these.

    python scripts/generate_synthetic_logs.py [--out data/synthetic_logs] [--rows 1500] [--clean]
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import _bootstrap  # noqa: F401
from rqg.config import REPO_ROOT
from rqg.observability.cost import cost_usd

START = datetime(2026, 10, 15, tzinfo=UTC)
DAYS = 14
QUESTIONS = [
    ("What is the filter life of the AeroPure 500?", "About 8 months. [ap500_specs]", False),
    (
        "How do I descale the BrewMate K2?",
        "Use 1 tablespoon of citric acid in 1 litre of water. [brewmate_k2_manual]",
        False,
    ),
    (
        "What does E12 mean on the RoboSweep S7?",
        "Cliff sensor error; wipe the sensors. [robosweep_s7_troubleshooting]",
        False,
    ),
    (
        "Is my product [SERIAL] under warranty?",
        "Your product is under warranty until 2027-06-10.",
        False,
    ),
    (
        "Do you ship to Nepal?",
        "I don't know — that isn't covered in the Zephyr Home manuals.",
        True,
    ),
    (
        "Will the purifier cure my asthma?",
        "I can't give medical advice. Please consult a doctor.",
        True,
    ),
    ("My email is [EMAIL], can you book a visit?", "Which time slot would you like?", False),
]
LEAKS = [
    "Sure, I've noted your email priya.k@example.com for the booking.",
    "We will call you on 9876543210 to confirm.",
    "Your contact rohan.m@example.net is saved.",
    "Technician will call +91 98123 45678.",
    "Confirmation sent to a.s@example.org.",
]
DOCS = [
    "ap500_specs",
    "ap300_specs",
    "brewmate_k2_manual",
    "robosweep_s7_troubleshooting",
    "warranty_policy_2026",
]


def generate(out: Path, n_rows: int = 1500, seed: int = 42, leaks: bool = True) -> int:
    rnd = random.Random(seed)
    if out.exists():
        shutil.rmtree(out)
    leak_rows = set(rnd.sample(range(n_rows), len(LEAKS))) if leaks else set()
    leak_iter = iter(LEAKS)
    rows_by_day: dict[str, list[str]] = {}
    for i in range(n_rows):
        day = i * DAYS // n_rows
        late = day >= DAYS - 3
        ts = START + timedelta(days=day, seconds=rnd.randint(0, 86_399))
        q, a, refusal_q = QUESTIONS[rnd.randrange(len(QUESTIONS))]
        refused = refusal_q or (rnd.random() < (0.10 if late else 0.03))
        model = "claude-haiku-5-5" if rnd.random() < 0.9 else "claude-sonnet-5-5"
        lat = rnd.lognormvariate(7.0 if not late else 7.45, 0.35)  # ~1.1 s median, ~1.7 s late
        it, ot = rnd.randint(900, 1600), rnd.randint(40, 160)
        answer = (
            next(leak_iter)
            if i in leak_rows
            else (
                "I don't know — that isn't covered in the Zephyr Home manuals."
                if refused and not refusal_q
                else a
            )
        )
        scored = rnd.random() < 0.3
        faith = None
        if scored:
            faith = round(min(1.0, max(0.0, rnd.gauss(0.88 if not late else 0.84, 0.08))), 3)
        rec = {
            "ts": ts.isoformat(),
            "session_id": f"synthetic-{rnd.randrange(10**8):08d}",
            "trace_id": f"syn{i:06d}",
            "prompt_version": "v1",
            "model": model,
            "latency_ms": round(lat, 1),
            "input_tokens": it,
            "output_tokens": ot,
            "cost_usd": round(cost_usd(model, it, ot), 8),
            "guardrail_flags": ["blocked:medical"] if "asthma" in q else [],
            "refused": refused,
            "tools_called": ["check_warranty"] if "warranty" in q else [],
            "retrieved_doc_ids": rnd.sample(DOCS, 3),
            "user_input_redacted": q,
            "answer_redacted": answer,
            "eval_scores": {
                "faithfulness": faith,
                "answer_relevancy": round(min(1.0, max(0.0, rnd.gauss(0.85, 0.07))), 3)
                if scored
                else None,
                "hallucination": (faith is not None and faith < 0.7),
                "retrieval_hit": (rnd.random() < (0.93 if not late else 0.9)) if scored else None,
            },
            "synthetic": True,
        }
        rows_by_day.setdefault(ts.strftime("%Y-%m-%d"), []).append(
            json.dumps(rec, ensure_ascii=False)
        )
    for d, lines in rows_by_day.items():
        p = out / f"dt={d}" / "interactions.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return n_rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "synthetic_logs")
    ap.add_argument("--rows", type=int, default=1500)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--clean", action="store_true", help="no planted PII leaks")
    a = ap.parse_args()
    n = generate(a.out, a.rows, a.seed, leaks=not a.clean)
    print(f"wrote {n} SYNTHETIC rows to {a.out} ({'no' if a.clean else '5'} planted PII leaks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
