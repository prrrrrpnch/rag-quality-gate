-- Daily quality trend: refusal rate, hallucination flags and mean groundedness
-- (eval_scores are written by the offline evaluator for a sample of traffic).
SELECT
  dt,
  count(*)                                                AS n,
  round(avg(CASE WHEN refused THEN 1.0 ELSE 0.0 END), 4)  AS refusal_rate,
  count(eval_scores.faithfulness)                         AS n_scored,
  round(avg(eval_scores.faithfulness), 4)                 AS groundedness_mean,
  sum(CASE WHEN eval_scores.hallucination THEN 1 ELSE 0 END) AS hallucination_flags
FROM interactions
WHERE dt >= '{{since}}'
GROUP BY dt
ORDER BY dt;
