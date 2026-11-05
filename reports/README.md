# reports/

Generated output (git-ignored), except `sample/`, which holds reports copied from real runs
so readers can see the format without running anything:

- `latest.json` / `latest.md` — last eval run (`make eval` / `make eval-fast`)
- `runs/<run_id>.json` — every run
- `gate.md` — last regression-gate verdict (`make gate`)
- `safety.md` / `safety.json` — attack-suite results (`make safety`)
- `drift.md`, `sql_checks.md` — observability and data-validation reports
