# Golden dataset schema (`golden_v1.jsonl`)

One JSON object per line. Validated by `rqg.evals.dataset.GoldenCase` (pydantic, `extra="forbid"`)
and checked against the corpus and tool backends by `scripts/validate_golden.py`
(also a pre-commit hook and a unit test).

| Field | Type | Meaning |
|---|---|---|
| `id` | `str` (`^[a-z]{2,4}-\d{3}$`) | Stable id, e.g. `sf-001`. Never reuse an id. |
| `dataset_version` | semver `str` | Version the case was added in. The dataset version is the max over cases. |
| `category` | enum | `single_fact`, `multi_doc`, `out_of_scope`, `conflict`, `blocked_topic`, `multi_turn`, `tool_call`, `adversarial_phrasing` |
| `turns` | `list[str]` (1–4) | User messages, sent in order in one session. Expectations apply to the reply to the **last** turn. |
| `expected_answer` | `str` | Reference answer (used by LLM judges for recall/correctness). |
| `required_facts` | `list[str]` | Each must appear in the answer. `a\|b` means either `a` or `b`. Matching is case/whitespace/dash-insensitive. |
| `forbidden_facts` | `list[str]` | Must NOT appear (e.g. the outdated value from a superseded doc). |
| `expected_sources` | `list[str]` | Doc ids that should be cited. |
| `source_match` | `all` \| `any` | `all`: every expected source must be cited. `any`: at least one (when several docs state the same fact). |
| `expected_behavior` | `answer` \| `refuse` \| `clarify` \| `tool_call` | The decision the assistant must make. |
| `expected_tools` | `list[{name, args}]` | Tool calls that must happen on the last turn (args compared case-insensitively). |
| `tags` | `list[str]` | Free-form (`hinglish`, `superseded`, `failure_recovery`, `blocked:medical`, ...). |
| `difficulty` | `easy` \| `medium` \| `hard` | Author's estimate. |
| `status` | `approved` \| `pending_review` | Only `approved` cases are evaluated and gated. |
| `origin` | `authored` \| `promoted_from_prod` | `promoted_from_prod` cases come from `scripts/promote_failure.py`. |
| `notes` | `str` | Optional reviewer notes. |

Consistency rules enforced by the model validator:

- `answer` cases need at least one `required_fact`; `refuse` cases must have none.
- `tool_call` cases need `expected_tools`.
- `multi_turn` cases need 2–4 turns.

Versioning: adding cases bumps the **minor** version (`1.0.0` → `1.1.0`); changing the meaning of
existing cases or the schema bumps the **major** version and requires a new baseline.

## Current distribution (v1.0.0, 108 cases)

| Category | Count | Brief minimum |
|---|---|---|
| single_fact | 26 | 25 |
| multi_doc | 12 | 12 |
| out_of_scope | 15 | 15 |
| conflict (outdated vs corrected) | 9 | 8 |
| blocked_topic | 8 | 8 |
| multi_turn | 16 | 15 |
| tool_call | 13 | 12 |
| adversarial_phrasing (typos, Hinglish, caps) | 9 | 8 |
