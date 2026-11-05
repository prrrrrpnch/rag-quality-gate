# Data validation: SQL on Athena and DuckDB

## The log is the data product

Every interaction becomes one JSON line in `logs/dt=YYYY-MM-DD/interactions.jsonl`
(`observability/logger.py`). Fields: `ts, session_id, trace_id, prompt_version, model,
latency_ms, input_tokens, output_tokens, cost_usd, guardrail_flags[], refused, tools_called[],
retrieved_doc_ids[], user_input_redacted, answer_redacted, eval_scores{faithfulness,
answer_relevancy, hallucination, retrieval_hit}, synthetic`.

The logger redacts every PII kind itself, so raw user text is never written even if a
caller forgets. The SQL checks below verify that this control works on the stored data.

## Queries (`sql/`, Athena / Trino dialect)

| File | Purpose | Expected |
|---|---|---|
| `create_table.sql` | external table over S3 JSONL, partition projection on `dt` | — |
| `pii_leak_check.sql` | stored text matching email / phone / customer id / serial / national-id patterns | **0 rows** (else fail) |
| `data_quality_check.sql` | data contract: missing trace id/model, negative latency/cost/tokens, unknown prompt version, scores out of range, duplicate trace ids | **0 rows** |
| `quality_trend.sql` | daily refusal rate, hallucination flags, mean groundedness | report |
| `latency_cost.sql` | p50/p95 latency and cost per day and model | report |

## Same SQL, two engines

- **Athena** (`data_validation/athena.py`): boto3 client with polling and exponential backoff,
  a timeout that calls `StopQueryExecution`, retries on throttling, paginated results, and a
  clear `AthenaQueryError` for FAILED/CANCELLED (with the `StateChangeReason`).
  Tested with moto (success path) and a stub client (failed, timeout, throttling, pagination).
- **DuckDB** (`data_validation/duckdb_local.py`): an `interactions` view over the local
  partitions with an explicit schema that mirrors the Athena DDL. Two macros let the same SQL
  text run unchanged: `regexp_like → regexp_matches` and `approx_percentile → quantile_cont`
  (DuckDB's percentile is exact, Athena's is approximate, so p95s can differ slightly).

A second, independent check (`data_validation/pii_scan.py`) scans the JSONL with the Python PII
patterns, including a Luhn check for card numbers that SQL regexes cannot do.

## Synthetic data (clearly labelled)

`scripts/generate_synthetic_logs.py` writes 1,500 rows over 14 days with a fixed seed. Every
row has `"synthetic": true`. Planted on purpose: a latency regression and a higher refusal rate
in the last 3 days, and **5 rows whose answer still contains a raw email or phone number**
(a simulated redaction bug). This is not production data.

Real output (`make sql-local`, 2026-11-05; full report in `reports/sample/sql_checks_synthetic.md`):

```text
## pii_leak_check: PASS (5 rows, expected 5)
## data_quality_check: PASS (0 rows, expected 0)
## Python PII scan (independent check): 5 findings
SQL CHECKS PASSED          <- synthetic set: exactly the 5 planted leaks found
SQL CHECKS PASSED          <- the app's own logs from eval runs: 0 leaks
```

Tests: `tests/unit/test_data_validation.py` checks that the PII query finds the planted leaks
and returns nothing on a clean generated set, and that each data-contract violation is caught.

## Drift (`observability/drift.py`, `make drift-report`)

Compares two windows of logs (or two eval runs, `--runs A.json B.json`):

- distributions (latency, cost, faithfulness, relevance): **PSI** on reference-quantile bins
  (< 0.10 OK, 0.10–0.25 WARN, > 0.25 ALERT) plus a two-sample **KS** test for a p-value;
- rates (refusal, retrieval hit, guardrail flags): absolute change with a **two-proportion
  z-test** (WARN ≥ 3 pts, ALERT ≥ 6 pts, both need p < 0.05).

On the synthetic set it reports ALERT for the planted latency regression (PSI 1.77) and for the
retrieval-hit drop (`reports/sample/drift_report_synthetic.md`). One caveat it also shows:
`answer_relevancy` is WARN on PSI 0.20 while KS p = 0.43. PSI is noisy on small samples (about
100 scored rows per window). Read PSI together with the KS p-value and the sample size.

## AWS deployment (manual, not applied)

`infra/terraform/` defines:

- KMS key (rotation on), used for both buckets and Athena results;
- logs bucket: SSE-KMS with bucket key, versioning, public access blocked, `BucketOwnerEnforced`,
  TLS-only bucket policy, lifecycle (Standard-IA after 30 days, expire after 365);
- results bucket: SSE-KMS, public access blocked, results expire after 7 days;
- Glue database + `interactions` table with the same schema and partition projection;
- Athena workgroup: enforced configuration, encrypted results, CloudWatch metrics, and a
  **1 GiB per-query scan cutoff** as a cost guard;
- least-privilege IAM policies: `log-uploader` (PutObject on `logs/*` + the KMS key only) and
  `athena-query-runner` (one workgroup, one table, read logs, read/write results).

It passes `terraform fmt -check` and `terraform validate` (CI job `terraform`). It was **never
applied**. To deploy:

```bash
cd infra/terraform
terraform init
terraform plan -out tfplan        # review: creates S3, KMS, Glue, Athena, IAM policies
terraform apply tfplan
# attach the two policies to your uploader / CI roles, then:
export RQG_S3_BUCKET=$(terraform output -raw logs_bucket)
export RQG_ATHENA_WORKGROUP=$(terraform output -raw athena_workgroup)
export RQG_ATHENA_DATABASE=$(terraform output -raw glue_database)
cd ../.. && python scripts/upload_logs_s3.py --log-dir logs
python scripts/run_athena_checks.py --athena
```

The Glue table is created by Terraform; `sql/create_table.sql` is the equivalent DDL if you
prefer to create it from the Athena console.

**Cost note.** Athena bills per byte scanned (about $5 per TB in most regions, 10 MB minimum
per query). Every query here filters on the `dt` partition (`WHERE dt >= '{{since}}'`), so it
reads only the days it needs, and the workgroup caps any single query at 1 GiB. At this
project's volume (KB per day) the cost is effectively the per-query minimum. At scale, convert
the JSONL to compressed Parquet (e.g. a daily CTAS) to cut scanned bytes by roughly an order of
magnitude, since columnar queries read only the columns they use.
