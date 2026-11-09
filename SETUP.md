# Setup, step by step

This takes about 5 minutes on a fresh machine, mostly downloading packages. Nothing here needs
an API key: without one the project runs in **mock mode** (deterministic fake LLM and judge).

## 1. Prerequisites

| Tool | Needed for | Check | Install (macOS) | Install (Ubuntu/Debian) |
|---|---|---|---|---|
| git + make | everything | `git --version && make --version` | `xcode-select --install` | `sudo apt install git make` |
| **Python 3.11, 3.12 or 3.13** | everything | `python3.12 --version` | `brew install python@3.12` | `sudo apt install python3.12 python3.12-venv` |
| Node.js 18+ | optional: promptfoo (`make promptfoo-ab`, `make redteam`) | `node --version` | `brew install node` | `sudo apt install nodejs npm` |
| Terraform 1.6+ | optional: `make tf-validate` | `terraform version` | `brew install terraform` | see developer.hashicorp.com |

macOS note: the `python3` that ships with Xcode is 3.9, which is too old. Install 3.12 with
Homebrew (`brew install python@3.12`; get Homebrew from https://brew.sh). You don't need to make it
the default: the setup script finds `python3.12` on its own.

Python 3.14 is not supported yet, because some pinned dependencies (onnxruntime, chromadb) have
no wheels for it.

## 2. Get the code

```bash
git clone https://github.com/prrrrrpnch/rag-quality-gate.git
```

```bash
cd rag-quality-gate
```

## 3. Run the setup

```bash
make setup
```

`make setup` runs [`scripts/setup.sh`](scripts/setup.sh), which:

1. checks git and finds a supported Python (and reports whether the optional Node and Terraform are present);
2. creates `.venv/` and installs the pinned dependencies from `pyproject.toml`;
3. copies `.env.example` to `.env` if you don't have one (mock mode on);
4. downloads the local embedding model once (~80 MB, cached in `~/.cache/chroma`);
5. smoke-checks the install: validates the golden dataset and asks the assistant one question.

It ends with `Setup complete.` Options:

```bash
bash scripts/setup.sh --recreate     # delete and rebuild .venv
```

```bash
bash scripts/setup.sh --skip-model   # no model download; then set EMBEDDING_BACKEND=hashing in .env
```

```bash
PYTHON_BIN=/opt/homebrew/bin/python3.12 make setup   # use a specific Python
```

## 4. Verify everything works

```bash
make verify
```

This runs lint, the unit tests (with coverage), a 25-case smoke eval and the regression gate.
It takes about a minute. The last lines should show `## Regression gate: ✅ PASS`.

## 5. Try it

All of these work offline in mock mode. Every target is listed by `make help`.

| Command | What it does |
|---|---|
| `make demo` | live questions (a normal one, a superseded-FAQ trap, out of scope, a blocked topic, an injection, a tool call, a follow-up) and a mini eval |
| `.venv/bin/rqg ask "How do I descale the kettle?"` | ask one question; `.venv/bin/rqg chat` for a multi-turn chat |
| `make eval` | full 108-case golden-set eval → `reports/latest.md` |
| `make gate` | compare the last eval with the committed baseline (exit 1 on regression) |
| `make gate-demo` | proves the gate works: applies a deliberate prompt regression in a temporary copy (gate FAILS), then checks your code (gate PASSES) |
| `make eval-pytest` | the per-case DeepEval suites (`deepeval test run tests/evals`) |
| `make safety` | 68 red-team attacks, with and without guardrails → `reports/safety.md` |
| `make sql-local` | Athena SQL data checks run in DuckDB over synthetic logs → `reports/sql_checks.md` |
| `make drift-report` | drift report (PSI / KS / z-test) on synthetic logs → `reports/drift.md` |
| `make promptfoo-ab` | promptfoo A/B, 2 prompts × 2 models (needs Node). Exits non-zero because the v2 prompt fails a test, which is the expected finding |
| `make tf-validate` | `terraform fmt -check` + `validate` (needs Terraform; never applies) |
| `make clean` | delete generated reports and logs |

Reports are written to `reports/` (git-ignored). Real examples are committed in `reports/sample/`.

## 6. Optional: real LLM mode

1. Get an Anthropic API key.
2. Edit `.env`: set `ANTHROPIC_API_KEY=...` and `MOCK_LLM=0`. `.env` is git-ignored, so never
   commit it.
3. Start small: `make eval-fast` runs 25 cases and prints tokens and an estimated cost.
4. Full run and real baseline: `make baseline` (writes `baselines/baseline.real.json`), then `make gate`.

The app model defaults to `claude-haiku-5-5` and the judge to `claude-sonnet-5-5`. Change them with
`APP_MODEL` / `JUDGE_MODEL` in `.env`. Calls are cached in `.cache/llm`, so re-running the same code on
the same data is free. LangSmith tracing: set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY`.

**In GitHub Actions:** add the key as the repository secret `ANTHROPIC_API_KEY` (Settings → Secrets and
variables → Actions), then run the **Real-LLM evals** workflow from the Actions tab. Without the secret
that workflow skips with a notice. Pull-request CI always runs in mock mode.

## 7. Optional: developer tooling

```bash
.venv/bin/pre-commit install
```

This runs ruff, YAML/JSON checks, a private-key detector and the golden-dataset validator before
each commit. `make format` auto-fixes lint and formatting.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Python 3.11-3.13 is required (found: Python 3.9…)` | `brew install python@3.12`, then `make setup` again |
| `.venv uses an unsupported Python` | `bash scripts/setup.sh --recreate` |
| `make: command not found` (macOS) | `xcode-select --install` |
| embedding-model download fails (proxy or offline) | `bash scripts/setup.sh --skip-model` and set `EMBEDDING_BACKEND=hashing` in `.env`. Note: the committed baseline uses `onnx`, so `make gate` then exits 2 ("incompatible"). Run `make baseline` to make a local one |
| `make gate` says `INCOMPATIBLE BASELINE` | the run's mode or embedding backend differs from the baseline (for example real mode against the mock baseline). Build one for your mode with `make baseline` |
| `make gate` says `no baseline` in real mode | run `make baseline` once in real mode |
| `Address already in use` for promptfoo targets | another process uses port 8787: `lsof -i :8787`, stop it, retry |
| SSL errors installing packages behind a corporate proxy | set `PIP_CERT=/path/to/corporate-ca.pem` before `make setup` |
