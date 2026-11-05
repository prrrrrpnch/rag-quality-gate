#!/usr/bin/env python
"""Validate every golden case against the corpus and the tool backends.

* schema (pydantic) + unique ids
* expected_sources exist in the corpus
* every required fact of an `answer` case appears in its expected source docs
* a forbidden fact must not be stated by every current expected source (else it is the truth)
* tool cases: replay expected tool calls on the mock backends; required facts must appear
  in the tool output
* refuse cases carry no sources

Exit 1 on any problem. A wrong golden answer is worse than none.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rqg.evals.checks import fact_present  # noqa: E402
from rqg.evals.dataset import load_golden  # noqa: E402
from rqg.rag.ingest import load_corpus  # noqa: E402
from rqg.tools.registry import ToolRegistry  # noqa: E402


def validate(golden: Path, corpus: Path) -> list[str]:
    errors: list[str] = []
    ds = load_golden(golden, include_pending=True)
    docs = {d.doc_id: d for d in load_corpus(corpus)}
    for c in ds.cases:
        for s in c.expected_sources:
            if s not in docs:
                errors.append(f"{c.id}: unknown source {s}")
        if c.expected_behavior == "refuse" and c.expected_sources:
            errors.append(f"{c.id}: refuse case should not list sources")
        if c.expected_behavior == "answer":
            src_text = " ".join(docs[s].text for s in c.expected_sources if s in docs)
            for f in c.required_facts:
                if not fact_present(f, src_text):
                    errors.append(f"{c.id}: required fact {f!r} not found in {c.expected_sources}")
            current = [
                docs[s].text
                for s in c.expected_sources
                if s in docs and docs[s].status == "current"
            ]
            for f in c.forbidden_facts:
                # A forbidden fact that every current source states is the truth, not a trap.
                if current and all(fact_present(f, t) for t in current):
                    errors.append(f"{c.id}: forbidden fact {f!r} is stated by all current sources")
        if c.expected_tools:
            reg = ToolRegistry(max_retries=1)
            outputs = []
            for t in c.expected_tools:
                res = reg.execute(t.name, t.args, c.turns)
                if not res.authorized:
                    errors.append(f"{c.id}: expected tool args use a serial not in the turns")
                outputs.append(json.dumps(res.output) + " " + str(res.output.get("error", "")))
            blob = " ".join(outputs)
            for f in c.required_facts:
                if not fact_present(f, blob):
                    errors.append(f"{c.id}: required fact {f!r} not produced by tool backend")
    return errors


def main() -> int:
    golden = ROOT / "data" / "golden" / "golden_v1.jsonl"
    corpus = ROOT / "data" / "corpus"
    errs = validate(golden, corpus)
    ds = load_golden(golden, include_pending=True)
    if errs:
        print("\n".join(errs))
        print(f"FAILED: {len(errs)} problem(s) in {len(ds.cases)} cases")
        return 1
    print(f"OK: {len(ds.cases)} cases (v{ds.version}) validated against corpus and tool backends")
    print("   ", ds.category_counts())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
