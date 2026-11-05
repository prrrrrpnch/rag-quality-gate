# SQL data-validation checks (DuckDB over data/synthetic_logs)

## pii_leak_check: PASS (5 rows, expected 5)

| dt | trace_id | model | pii_kind | answer_preview |
|---|---|---|---|---|
| 2026-10-15 | syn000051 | claude-haiku-5-5 | email | Sure, I've noted your email priya.k@example.com for the book |
| 2026-10-17 | syn000228 | claude-haiku-5-5 | phone | We will call you on 9876543210 to confirm. |
| 2026-10-19 | syn000501 | claude-haiku-5-5 | email | Your contact rohan.m@example.net is saved. |
| 2026-10-20 | syn000563 | claude-haiku-5-5 | phone | Technician will call +91 98123 45678. |
| 2026-10-27 | syn001309 | claude-haiku-5-5 | email | Confirmation sent to a.s@example.org. |

## data_quality_check: PASS (0 rows, expected 0)

_no rows_

## quality_trend

| dt | n | refusal_rate | n_scored | groundedness_mean | hallucination_flags |
|---|---|---|---|---|---|
| 2026-10-15 | 108 | 0.2963 | 25 | 0.8934 | 0 |
| 2026-10-16 | 107 | 0.2523 | 33 | 0.8771 | 0 |
| 2026-10-17 | 107 | 0.3178 | 33 | 0.8638 | 0 |
| 2026-10-18 | 107 | 0.2897 | 22 | 0.8844 | 1 |
| 2026-10-19 | 107 | 0.3271 | 32 | 0.8632 | 0 |
| 2026-10-20 | 107 | 0.2523 | 31 | 0.8844 | 0 |
| 2026-10-21 | 107 | 0.3925 | 32 | 0.8761 | 1 |
| 2026-10-22 | 108 | 0.3056 | 31 | 0.8965 | 0 |
| 2026-10-23 | 107 | 0.4019 | 33 | 0.8572 | 0 |
| 2026-10-24 | 107 | 0.2897 | 31 | 0.8622 | 0 |
| 2026-10-25 | 107 | 0.243 | 26 | 0.86 | 1 |
| 2026-10-26 | 107 | 0.3271 | 30 | 0.8444 | 1 |
| 2026-10-27 | 107 | 0.3738 | 30 | 0.8436 | 2 |
| 2026-10-28 | 107 | 0.3551 | 26 | 0.8142 | 2 |

## latency_cost

| dt | model | n | p50_ms | p95_ms | cost_usd | cost_per_100_queries_usd |
|---|---|---|---|---|---|---|
| 2026-10-15 | claude-haiku-5-5 | 97 | 1070.5 | 1898.5 | 0.016728 | 0.017245 |
| 2026-10-15 | claude-sonnet-5-5 | 11 | 1215.0 | 1631.1 | 0.037724 | 0.342945 |
| 2026-10-16 | claude-haiku-5-5 | 99 | 1089.2 | 1882.8 | 0.017049 | 0.017222 |
| 2026-10-16 | claude-sonnet-5-5 | 8 | 1006.3 | 1270.1 | 0.030228 | 0.37785 |
| 2026-10-17 | claude-haiku-5-5 | 100 | 1162.4 | 1892.1 | 0.01762 | 0.01762 |
| 2026-10-17 | claude-sonnet-5-5 | 7 | 1298.9 | 1711.7 | 0.023338 | 0.3334 |
| 2026-10-18 | claude-haiku-5-5 | 101 | 991.5 | 1784.5 | 0.01772 | 0.017545 |
| 2026-10-18 | claude-sonnet-5-5 | 6 | 1103.4 | 1365.2 | 0.021802 | 0.363367 |
| 2026-10-19 | claude-haiku-5-5 | 95 | 1095.1 | 1976.6 | 0.016547 | 0.017417 |
| 2026-10-19 | claude-sonnet-5-5 | 12 | 1072.1 | 1873.3 | 0.041262 | 0.34385 |
| 2026-10-20 | claude-haiku-5-5 | 100 | 1098.1 | 1780.6 | 0.017803 | 0.017803 |
| 2026-10-20 | claude-sonnet-5-5 | 7 | 1173.1 | 2265.4 | 0.025198 | 0.359971 |
| 2026-10-21 | claude-haiku-5-5 | 94 | 1159.7 | 2027.7 | 0.016168 | 0.0172 |
| 2026-10-21 | claude-sonnet-5-5 | 13 | 1119.2 | 1994.1 | 0.045518 | 0.350138 |
| 2026-10-22 | claude-haiku-5-5 | 105 | 1099.9 | 1808.0 | 0.018623 | 0.017736 |
| … 13 more rows | | | | | | |

## Python PII scan (independent check): 5 findings
