-- Athena external table over the JSONL interaction logs in S3.
-- Partition projection on `dt` means no MSCK REPAIR / crawler is needed, and queries that
-- filter on dt only scan those days (Athena bills per byte scanned).
-- {{bucket}} is substituted by scripts/run_athena_checks.py; ${dt} is Athena's own template.
CREATE EXTERNAL TABLE IF NOT EXISTS interactions (
  ts                  string,
  session_id          string,
  trace_id            string,
  prompt_version      string,
  model               string,
  latency_ms          double,
  input_tokens        int,
  output_tokens       int,
  cost_usd            double,
  guardrail_flags     array<string>,
  refused             boolean,
  tools_called        array<string>,
  retrieved_doc_ids   array<string>,
  user_input_redacted string,
  answer_redacted     string,
  eval_scores         struct<faithfulness:double, answer_relevancy:double, hallucination:boolean, retrieval_hit:boolean>,
  synthetic           boolean
)
PARTITIONED BY (dt string)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
LOCATION 's3://{{bucket}}/logs/'
TBLPROPERTIES (
  'projection.enabled'          = 'true',
  'projection.dt.type'          = 'date',
  'projection.dt.format'        = 'yyyy-MM-dd',
  'projection.dt.range'         = '2026-01-01,NOW',
  'projection.dt.interval'      = '1',
  'projection.dt.interval.unit' = 'DAYS',
  'storage.location.template'   = 's3://{{bucket}}/logs/dt=${dt}/'
);
