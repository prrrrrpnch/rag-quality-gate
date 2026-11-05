"""Golden dataset schema and loader (pydantic-validated, versioned JSONL)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Category = Literal[
    "single_fact",
    "multi_doc",
    "out_of_scope",
    "conflict",
    "blocked_topic",
    "multi_turn",
    "tool_call",
    "adversarial_phrasing",
]
Behavior = Literal["answer", "refuse", "clarify", "tool_call"]


class ExpectedTool(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["check_warranty", "book_service"]
    args: dict[str, str] = Field(default_factory=dict)


class GoldenCase(BaseModel):
    """One evaluation case. Expectations apply to the assistant's reply to the LAST turn."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z]{2,4}-\d{3}$")
    dataset_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    category: Category
    turns: list[str] = Field(min_length=1, max_length=4)
    expected_answer: str
    required_facts: list[str] = Field(default_factory=list)
    forbidden_facts: list[str] = Field(default_factory=list)
    expected_sources: list[str] = Field(default_factory=list)
    source_match: Literal["all", "any"] = "all"
    expected_behavior: Behavior
    expected_tools: list[ExpectedTool] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    status: Literal["approved", "pending_review"] = "approved"
    origin: Literal["authored", "promoted_from_prod"] = "authored"
    notes: str = ""

    @field_validator("turns")
    @classmethod
    def _non_empty_turns(cls, v: list[str]) -> list[str]:
        if any(not t.strip() for t in v):
            raise ValueError("turns must be non-empty strings")
        return v

    @model_validator(mode="after")
    def _consistent(self) -> GoldenCase:
        if self.expected_behavior == "tool_call" and not self.expected_tools:
            raise ValueError(f"{self.id}: tool_call cases need expected_tools")
        if self.expected_behavior == "refuse" and self.required_facts:
            raise ValueError(f"{self.id}: refuse cases must not have required_facts")
        if self.expected_behavior == "answer" and not self.required_facts:
            raise ValueError(f"{self.id}: answer cases need at least one required_fact")
        if self.category == "multi_turn" and len(self.turns) < 2:
            raise ValueError(f"{self.id}: multi_turn cases need 2-4 turns")
        return self

    @property
    def question(self) -> str:
        return self.turns[-1]


class GoldenDataset(BaseModel):
    version: str
    cases: list[GoldenCase]

    def by_id(self) -> dict[str, GoldenCase]:
        return {c.id: c for c in self.cases}

    def approved(self) -> list[GoldenCase]:
        return [c for c in self.cases if c.status == "approved"]

    def category_counts(self) -> dict[str, int]:
        return dict(Counter(c.category for c in self.cases))


def load_golden(path: Path, include_pending: bool = False) -> GoldenDataset:
    """Load + validate a golden JSONL file. Raises ``ValueError`` with the line number."""
    cases: list[GoldenCase] = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            cases.append(GoldenCase.model_validate(json.loads(line)))
        except Exception as e:
            raise ValueError(f"{path}:{n}: {e}") from e
    ids = [c.id for c in cases]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"duplicate case ids: {dupes}")
    versions = {c.dataset_version for c in cases}
    version = (
        max(versions, key=lambda v: tuple(int(x) for x in v.split("."))) if versions else "0.0.0"
    )
    if not include_pending:
        cases = [c for c in cases if c.status == "approved"]
    return GoldenDataset(version=version, cases=cases)


def smoke_subset(cases: list[GoldenCase], n: int = 25) -> list[GoldenCase]:
    """Deterministic stratified subset: round-robin over categories in id order."""
    by_cat: dict[str, list[GoldenCase]] = {}
    for c in sorted(cases, key=lambda c: c.id):
        by_cat.setdefault(c.category, []).append(c)
    out: list[GoldenCase] = []
    i = 0
    while len(out) < min(n, len(cases)):
        for cat in sorted(by_cat):
            if i < len(by_cat[cat]) and len(out) < n:
                out.append(by_cat[cat][i])
        i += 1
    return out


def bump_minor(version: str) -> str:
    major, minor, _ = (int(x) for x in version.split("."))
    return f"{major}.{minor + 1}.0"


def append_case(path: Path, case: dict[str, Any]) -> GoldenCase:
    """Validate and append one case (used by promote_failure)."""
    gc = GoldenCase.model_validate(case)
    with Path(path).open("a", encoding="utf-8") as f:
        f.write(json.dumps(gc.model_dump(), ensure_ascii=False) + "\n")
    return gc
