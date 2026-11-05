# Eval report — 20261105T160128Z-7b5914

> **MOCK MODE.** App model = deterministic extractive mock, judge = heuristic. These numbers test the pipeline and the gate, not a real LLM.

- mode: `mock` · subset: `full` · cases: 108 · dataset: v1.0.0
- git: `286fd61` · prompt: `v1` · app model: `mock-support-v1` · judge: `heuristic-judge-v1` (x1)
- embeddings: `onnx` · wall time: 4.74 s

## Headline KPIs

| KPI | Value |
|---|---|
| Pass rate (all deterministic checks) | 0.8056 |
| Hallucination rate (1 - faithfulness pass rate) | 0 |
| Groundedness (mean faithfulness) | 1 |
| Answer relevance (mean) | 0.7883 |
| Refusal recall (refused / should refuse) | 0.8261 |
| Refusal precision | 0.8261 |
| Over-refusal rate | 0.0471 |
| Tool success rate | 1 |
| Retrieval hit rate | 0.9583 |
| Context precision (label-based) | 0.8538 |
| Context recall (label-based) | 0.8095 |
| Ragas NonLLMStringSimilarity (mean) | 0.2177 |
| DeepEval vs Ragas faithfulness agreement | n/a |
| Latency p50 (ms) | 35.72 |
| Latency p95 (ms) | 48.51 |
| Cost per 100 queries (USD, app model) | 0 |

## Per category

| Category | n | Pass rate | Behaviour accuracy | Groundedness |
|---|---|---|---|---|
| adversarial_phrasing | 9 | 0.7778 | 0.8889 | 1 |
| blocked_topic | 8 | 1 | 1 | n/a |
| conflict | 9 | 0.8889 | 0.8889 | 1 |
| multi_doc | 12 | 0.5 | 0.9167 | 1 |
| multi_turn | 16 | 0.75 | 1 | 1 |
| out_of_scope | 15 | 0.7333 | 0.7333 | 1 |
| single_fact | 26 | 0.8462 | 0.9231 | 1 |
| tool_call | 13 | 1 | 1 | n/a |

## Failing cases (21)

| Case | Category | Expected → observed | Failed checks | Answer (truncated) |
|---|---|---|---|---|
| ap-004 | adversarial_phrasing | answer → answer | required_facts | Fill with water between the MIN and MAX marks. [brewmate_k2_manual] Red light blinking: th… |
| ap-009 | adversarial_phrasing | answer → refuse | required_facts, sources, behavior | I don't know — that isn't covered in the Zephyr Home manuals. Please contact Zephyr Home s… |
| cf-009 | conflict | answer → clarify | required_facts, sources, behavior | Which model do you mean — the AeroPure 300 or the AeroPure 500? |
| md-007 | multi_doc | answer → answer | required_facts | All connected Zephyr Home products need a 2.4 GHz Wi-Fi network. [zephyr_connect_app_faq] |
| md-008 | multi_doc | answer → answer | required_facts | The AeroPure 500 (model code AP500) is Zephyr Home's large-room air purifier for living ro… |
| md-009 | multi_doc | answer → answer | required_facts, sources | Outside warranty, the visit fee is ₹399 plus the cost of any parts. [service_policy] |
| md-010 | multi_doc | answer → answer | required_facts, sources | Consumables such as air filters, brushes and mop pads are not covered by the warranty. [wa… |
| md-011 | multi_doc | answer → refuse | required_facts, sources, behavior | I don't know — that isn't covered in the Zephyr Home manuals. Please contact Zephyr Home s… |
| md-012 | multi_doc | answer → answer | required_facts | 5 GHz networks are not supported. [robosweep_s7_setup_app] |
| mt-004 | multi_turn | answer → answer | required_facts | The filter indicator turns red when a replacement is due. [aeropure_setup_filters] |
| mt-005 | multi_turn | answer → answer | required_facts | Runtime: up to 150 minutes in Standard mode. [robosweep_s7_specs] Cleaning time is much sh… |
| mt-007 | multi_turn | answer → answer | required_facts | AeroPure 300 and AeroPure 500 air purifiers: 2 years (24 months) from the date of purchase… |
| mt-016 | multi_turn | answer → answer | forbidden_facts | Replacement filter part code: ZF-300. [ap300_specs] Replacement filter part code: ZF-500. … |
| oos-002 | out_of_scope | refuse → answer | behavior | Service visits for products under warranty are free, including parts covered by the warran… |
| oos-012 | out_of_scope | refuse → answer | behavior | Service visits for products under warranty are free, including parts covered by the warran… |
| oos-013 | out_of_scope | refuse → answer | behavior | Outside warranty, the visit fee is ₹399 plus the cost of any parts. [service_policy] You c… |
| oos-014 | out_of_scope | refuse → answer | behavior | Air quality sensing: a laser PM2.5 sensor with a colour ring and a numeric display. [ap500… |
| sf-009 | single_fact | answer → refuse | required_facts, sources, behavior | I don't know — that isn't covered in the Zephyr Home manuals. Please contact Zephyr Home s… |
| sf-016 | single_fact | answer → answer | required_facts | Place the charging dock against a wall on a hard floor, with at least 0.5 m of clear space… |
| sf-025 | single_fact | answer → answer | required_facts | You can book a technician visit through the Zephyr Home support assistant, the Zephyr Conn… |
| sf-026 | single_fact | answer → refuse | required_facts, sources, behavior | I don't know — that isn't covered in the Zephyr Home manuals. Please contact Zephyr Home s… |

## Cost

- App tokens: 109,920 in / 3,590 out; cost this run: $0.0000
- Judge calls: 0
- Estimated app-model cost of the same traffic on claude-haiku-5-5 (mock token counts are len/4 approximations): $0.0128
