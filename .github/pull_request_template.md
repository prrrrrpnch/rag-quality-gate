## What changed

## Why

## Quality gate
- [ ] `make lint test` pass locally
- [ ] `make eval gate` passes (or the regression is intended and the baseline is rebuilt in this PR with a reason below)
- [ ] `make safety` — no must-never-succeed attack succeeds
- [ ] New behaviour has a golden case or attack (production failures: `scripts/promote_failure.py`)

## Baseline / threshold changes (if any) and justification
