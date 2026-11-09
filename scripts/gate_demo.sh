#!/usr/bin/env bash
# Prove the regression gate works: apply a deliberate prompt regression in a throwaway git
# worktree, run the full eval + gate there (expected: FAIL), then run the gate on the
# untouched checkout (expected: PASS). Your working tree is never modified.
#
#   make gate-demo
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PY:-$ROOT/.venv/bin/python}"
[ -x "$PY" ] || PY="$(command -v python3)"
WT="$(mktemp -d "${TMPDIR:-/tmp}/rqg-gate-demo.XXXXXX")"

cleanup() { git -C "$ROOT" worktree remove --force "$WT" >/dev/null 2>&1 || rm -rf "$WT"; }
trap cleanup EXIT

echo "== 1/3  creating throwaway worktree at $WT"
git -C "$ROOT" worktree add --detach "$WT" HEAD >/dev/null
git -C "$WT" apply "$ROOT/scripts/demo_regression.patch"
echo "   applied scripts/demo_regression.patch (removes the 'answer ONLY from context' rule):"
git -C "$WT" diff --stat | sed 's/^/   /'

echo
echo "== 2/3  full eval + gate WITH the regression (expected: FAIL)"
(cd "$WT" && "$PY" scripts/run_eval.py --subset full >/dev/null)
set +e
(cd "$WT" && "$PY" scripts/compare_to_baseline.py)
regressed_exit=$?
set -e
echo "   gate exit code with regression: $regressed_exit"

echo
echo "== 3/3  full eval + gate on your checkout (expected: PASS)"
(cd "$ROOT" && "$PY" scripts/run_eval.py --subset full >/dev/null)
set +e
(cd "$ROOT" && "$PY" scripts/compare_to_baseline.py | head -3)
clean_exit=${PIPESTATUS[0]}
set -e
echo "   gate exit code without regression: $clean_exit"

echo
if [ "$regressed_exit" -eq 1 ] && [ "$clean_exit" -eq 0 ]; then
  echo "GATE DEMO OK: the gate failed on the regression and passed on the clean code."
else
  echo "GATE DEMO UNEXPECTED: regression exit=$regressed_exit, clean exit=$clean_exit"
  exit 1
fi
