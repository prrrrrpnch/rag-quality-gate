-- Data contract for the AI pipeline log. EXPECTED RESULT: ZERO ROWS.
SELECT dt, trace_id, violation
FROM (
  SELECT dt, trace_id,
    CASE
      WHEN trace_id IS NULL OR trace_id = ''        THEN 'missing_trace_id'
      WHEN model IS NULL OR model = ''              THEN 'missing_model'
      WHEN latency_ms IS NULL OR latency_ms < 0     THEN 'bad_latency'
      WHEN cost_usd IS NULL OR cost_usd < 0         THEN 'bad_cost'
      WHEN input_tokens < 0 OR output_tokens < 0    THEN 'bad_tokens'
      WHEN refused IS NULL                          THEN 'missing_refused'
      WHEN prompt_version NOT IN ('v1', 'v2')       THEN 'unknown_prompt_version'
      WHEN eval_scores.faithfulness < 0 OR eval_scores.faithfulness > 1 THEN 'score_out_of_range'
    END AS violation
  FROM interactions
  WHERE dt >= '{{since}}'
) t
WHERE violation IS NOT NULL
UNION ALL
SELECT min(dt) AS dt, trace_id, 'duplicate_trace_id' AS violation
FROM interactions
WHERE dt >= '{{since}}'
GROUP BY trace_id
HAVING count(*) > 1;
