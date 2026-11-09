#!/usr/bin/env bash
# One-command project setup:  make setup   (or: bash scripts/setup.sh [--recreate] [--skip-model])
#
#  1. checks prerequisites (git, Python 3.11-3.13; Node/Terraform are optional)
#  2. creates .venv and installs the pinned dependencies
#  3. creates .env from .env.example (mock mode, no API key needed)
#  4. downloads the local embedding model once (~80 MB, cached in ~/.cache/chroma)
#  5. runs a smoke check (golden-set validation + one question to the assistant)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VENV="${VENV:-.venv}"
RECREATE=0
SKIP_MODEL=0
for arg in "$@"; do
  case "$arg" in
    --recreate) RECREATE=1 ;;
    --skip-model) SKIP_MODEL=1 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg"; exit 2 ;;
  esac
done

ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m✘\033[0m %s\n' "$*"; exit 1; }
step() { printf '\n\033[1m[%s] %s\033[0m\n' "$1" "$2"; }

py_ok() { "$1" -c 'import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 13) else 1)' 2>/dev/null; }

step 1/5 "Checking prerequisites"
command -v git >/dev/null || fail "git not found (macOS: xcode-select --install)"
ok "git $(git --version | awk '{print $3}')"
PYTHON=""
if [ -n "${PYTHON_BIN:-}" ] && ! py_ok "$PYTHON_BIN"; then
  fail "PYTHON_BIN=$PYTHON_BIN is not Python 3.11-3.13 ($("$PYTHON_BIN" --version 2>&1 || echo 'not found'))"
fi
for cand in "${PYTHON_BIN:-}" python3.12 python3.13 python3.11 python3; do
  [ -n "$cand" ] && command -v "$cand" >/dev/null && py_ok "$cand" && { PYTHON="$(command -v "$cand")"; break; }
done
if [ -z "$PYTHON" ]; then
  found="$(command -v python3 >/dev/null && python3 --version 2>&1 || echo none)"
  fail "Python 3.11-3.13 is required (found: $found).
     macOS:  brew install python@3.12        Ubuntu: sudo apt install python3.12 python3.12-venv
     or point to one: PYTHON_BIN=/path/to/python3.12 make setup"
fi
ok "python $("$PYTHON" -c 'import platform; print(platform.python_version())') ($PYTHON)"
if command -v node >/dev/null; then ok "node $(node --version) (for promptfoo: make promptfoo-ab / make redteam)"
else warn "node not found: optional, only needed for promptfoo (macOS: brew install node)"; fi
if command -v terraform >/dev/null; then ok "terraform $(terraform version | head -1 | awk '{print $2}') (for make tf-validate)"
else warn "terraform not found: optional, only needed for make tf-validate (brew install terraform)"; fi

step 2/5 "Creating $VENV and installing pinned dependencies (takes a few minutes the first time)"
if [ "$RECREATE" = 1 ] && [ -d "$VENV" ]; then rm -rf "$VENV"; ok "removed old $VENV"; fi
if [ -x "$VENV/bin/python" ] && ! py_ok "$VENV/bin/python"; then
  fail "$VENV uses an unsupported Python. Re-run with: bash scripts/setup.sh --recreate"
fi
[ -x "$VENV/bin/python" ] || "$PYTHON" -m venv "$VENV"
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q -e ".[dev]"
ok "installed $("$VENV/bin/python" -m pip list 2>/dev/null | grep -ciE '^(deepeval|ragas|chromadb|anthropic|duckdb) ') core packages (deepeval, ragas, chromadb, anthropic, duckdb)"

step 3/5 "Configuring .env"
if [ -f .env ]; then ok ".env already exists (left unchanged)"
else cp .env.example .env; ok "created .env from .env.example (MOCK_LLM=1: offline, no API key needed)"; fi

step 4/5 "Downloading the local embedding model"
if [ "$SKIP_MODEL" = 1 ]; then
  warn "skipped (--skip-model): set EMBEDDING_BACKEND=hashing in .env to run without it"
else
  "$VENV/bin/python" - <<'PY'
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
v = ONNXMiniLM_L6_V2()(["warm-up"])[0]
print(f"  \033[32m✔\033[0m all-MiniLM-L6-v2 (ONNX) ready, {len(v)}-dim embeddings, cached in ~/.cache/chroma")
PY
fi

step 5/5 "Smoke check"
"$VENV/bin/python" scripts/validate_golden.py | head -1 | sed 's/^/  /'
answer="$(DEEPEVAL_TELEMETRY_OPT_OUT=1 "$VENV/bin/rqg" ask "What is the filter life of the AeroPure 500?" 2>/dev/null)"
case "$answer" in
  *"8 months"*) ok "assistant answered: $answer" ;;
  *) fail "unexpected assistant answer: $answer" ;;
esac

printf '\n\033[1mSetup complete.\033[0m Next:\n'
cat <<'TXT'
  make demo        live queries + mini eval
  make verify      lint + unit tests + 25-case eval + regression gate (~1 min)
  make eval gate   full 108-case eval and the gate
  make help        every target
  Real LLM mode: put ANTHROPIC_API_KEY in .env and set MOCK_LLM=0 (see SETUP.md)
TXT
