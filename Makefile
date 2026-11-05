# rag-quality-gate — every target works offline in mock mode (no API key needed).
VENV    ?= .venv
PY      ?= $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python)
PROMPTFOO ?= npx --yes promptfoo@0.125.1
export DEEPEVAL_TELEMETRY_OPT_OUT := 1
export PROMPTFOO_DISABLE_TELEMETRY := 1
export ANONYMIZED_TELEMETRY := False

.PHONY: help setup lint format test eval-fast eval eval-pytest safety redteam promptfoo-ab \
        gate baseline drift-report synthetic-logs sql-local tf-validate demo serve clean

help:  ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

setup:  ## create .venv and install (pinned) deps
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q --upgrade pip
	$(VENV)/bin/pip install -q -e ".[dev]"
	@echo "setup done. Mock mode is used automatically when no API key is set."

lint:  ## ruff lint + format check
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

format:
	$(PY) -m ruff check --fix .
	$(PY) -m ruff format .

test:  ## unit tests (fast, offline) with coverage
	$(PY) -m pytest tests/unit -q --cov --cov-report=term --cov-report=xml

eval-fast:  ## 25-case stratified smoke eval
	$(PY) scripts/run_eval.py --subset smoke

eval:  ## full golden-set eval -> reports/latest.{json,md}
	$(PY) scripts/run_eval.py --subset full

eval-pytest:  ## per-case DeepEval suites (deepeval test run)
	$(VENV)/bin/deepeval test run tests/evals -q || $(PY) -m pytest tests/evals -q

gate:  ## compare reports/latest.json with the committed baseline (exit 1 on regression)
	$(PY) scripts/compare_to_baseline.py

baseline: eval  ## full eval, then freeze it as the baseline
	$(PY) scripts/build_baseline.py

safety:  ## curated attack suite (deterministic detectors) + report
	$(PY) scripts/run_safety.py
	$(PY) -m pytest tests/safety -q

promptfoo-ab:  ## promptfoo A/B (2 prompts x 2 models) against the local HTTP wrapper
	$(PY) scripts/serve_assistant.py --port 8787 & echo $$! > .serve.pid; sleep 6; \
	  $(PROMPTFOO) eval -c promptfoo/promptfooconfig.yaml --no-cache -o reports/promptfoo_ab.json; rc=$$?; \
	  kill `cat .serve.pid`; rm -f .serve.pid; exit $$rc

redteam:  ## promptfoo red team (needs a generator: promptfoo cloud or an LLM key; costs money)
	$(PY) scripts/serve_assistant.py --port 8787 & echo $$! > .serve.pid; sleep 6; \
	  $(PROMPTFOO) redteam run -c promptfoo/redteam.yaml -o reports/redteam.json; rc=$$?; \
	  kill `cat .serve.pid`; rm -f .serve.pid; exit $$rc

synthetic-logs:  ## seed 1,500 clearly-labelled SYNTHETIC log rows (fixed seed)
	$(PY) scripts/generate_synthetic_logs.py

drift-report: synthetic-logs  ## PSI/KS drift report between two windows (exit 3 = ALERT, not an error here)
	$(PY) scripts/drift_report.py || [ $$? -eq 3 ]

sql-local: synthetic-logs  ## run the Athena SQL checks locally in DuckDB
	$(PY) scripts/run_athena_checks.py --local

tf-validate:  ## terraform fmt + validate (no apply)
	cd infra/terraform && terraform fmt -check -recursive && terraform init -backend=false -input=false >/dev/null && terraform validate

serve:  ## HTTP wrapper used by promptfoo
	$(PY) scripts/serve_assistant.py --port 8787

demo:  ## ingest, a few live queries, a mini eval and the report
	$(PY) scripts/demo.py

clean:
	rm -rf reports/runs reports/latest.* reports/gate.md reports/safety* .pytest_cache .ruff_cache \
	  .coverage coverage.xml htmlcov logs data/synthetic_logs .deepeval
