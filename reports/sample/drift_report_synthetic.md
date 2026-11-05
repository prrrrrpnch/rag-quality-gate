# Drift report — 🔴 ALERT

Logs in `data/synthetic_logs`: reference 2026-10-15:2026-10-21 (n=750) vs current 2026-10-26:2026-10-28 (n=321)

> SYNTHETIC data (scripts/generate_synthetic_logs.py, seed 42) — not production traffic.

| Metric | Type | Reference | Current | Statistic | Status |
|---|---|---|---|---|---|
| latency_ms | distribution | 1162.5584 | 1857.0237 | PSI=1.769, KS=0.515 (p=5.5e-55) | ALERT |
| cost_usd | distribution | 0.0005 | 0.0005 | PSI=0.007, KS=0.035 (p=0.93) | OK |
| faithfulness | distribution | 0.8765 | 0.835 | PSI=0.332, KS=0.226 (p=0.0032) | ALERT |
| answer_relevancy | distribution | 0.8529 | 0.8513 | PSI=0.200, KS=0.109 (p=0.43) | WARN |
| refusal_rate | rate | 0.304 | 0.352 | Δ=+0.048 (p=0.12) | OK |
| retrieval_hit_rate | rate | 0.9327 | 0.8488 | Δ=-0.084 (p=0.024) | ALERT |
| guardrail_flag_rate | rate | 0.148 | 0.134 | Δ=-0.014 (p=0.55) | OK |

PSI: <0.10 OK, 0.10–0.25 WARN, >0.25 ALERT. Rates: two-proportion z-test, WARN ≥3 pts, ALERT ≥6 pts (p<0.05).
