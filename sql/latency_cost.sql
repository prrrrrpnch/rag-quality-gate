-- p50 / p95 latency and cost per day and model.
SELECT
  dt,
  model,
  count(*)                                        AS n,
  round(approx_percentile(latency_ms, 0.5), 1)    AS p50_ms,
  round(approx_percentile(latency_ms, 0.95), 1)   AS p95_ms,
  round(sum(cost_usd), 6)                         AS cost_usd,
  round(sum(cost_usd) / count(*) * 100, 6)        AS cost_per_100_queries_usd
FROM interactions
WHERE dt >= '{{since}}'
GROUP BY dt, model
ORDER BY dt, model;
