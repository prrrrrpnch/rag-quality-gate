# Architecture

## Request path (system under test)

```mermaid
flowchart LR
    U[User turn] --> IG{Input guard<br/>injection heuristics<br/>blocked topics}
    IG -- blocked --> RF[Polite refusal<br/>no LLM call]
    IG -- ok --> CQ[Contextualise follow-up<br/>with session history]
    CQ --> R[Retriever<br/>MiniLM ONNX + Chroma<br/>+ lexical re-rank]
    R --> CS[Context sanitiser<br/>drops planted instructions]
    CS --> LLM[App LLM<br/>claude-haiku-5-5 / mock]
    LLM -- tool_use --> TA{Tool authz<br/>serial typed by user?<br/>owned by customer?}
    TA -- allowed --> T[check_warranty / book_service<br/>timeout + 1 retry]
    TA -- denied --> LLM
    T --> LLM
    LLM --> OG{Output guard<br/>canary / prompt leak<br/>PII redaction}
    OG --> A[AssistantResponse<br/>answer, citations, tools,<br/>latency, tokens, cost, flags]
    A --> L[(JSONL log<br/>dt=YYYY-MM-DD<br/>redacted)]
```

| Component | File | Notes |
|---|---|---|
| Config | `src/rqg/config.py` | pydantic-settings; mock mode is automatic when no key is set |
| LLM layer | `src/rqg/llm/` | provider-neutral messages; Anthropic + OpenAI-compatible clients; deterministic mock; sha256 disk cache |
| Retrieval | `src/rqg/rag/ingest.py`, `retriever.py`, `embeddings.py` | section chunking with title prefix; `0.75·dense + 0.25·lexical` fusion (helps error/part codes) |
| Assistant | `src/rqg/rag/assistant.py` | session history, tool loop (max 4 rounds), structured `AssistantResponse` |
| Prompts | `src/rqg/rag/prompts.py` | versioned; `GROUNDING_RULE` and the canary are separate constants |
| Tools | `src/rqg/tools/` | mock warranty + booking backends with planted failures (invalid serial, unavailable slot, timeouts) |
| Guardrails | `src/rqg/guardrails/` | regex/heuristic, deterministic, no LLM |

## Quality system

```mermaid
flowchart TB
    G[(golden_v1.jsonl<br/>108 cases)] --> RUN[EvalRunner]
    ATK[(attacks_v1.jsonl<br/>68 attacks)] --> SR[AttackRunner]
    RUN --> DC[Deterministic checks<br/>facts, sources, behaviour,<br/>tools, citations, latency]
    RUN --> J{Judge}
    J -- mock --> HJ[Heuristic judge]
    J -- real --> DE[DeepEval metrics<br/>x3 repeats, median]
    J -- real --> RG[Ragas collections<br/>second opinion]
    DC & HJ & DE & RG --> REP[KPI report<br/>reports/latest.json/.md]
    REP --> GATE{Gate vs<br/>baselines/baseline.json}
    SR --> DET[Deterministic detectors] --> SAFE{Must-never set<br/>held?}
    GATE & SAFE --> CI[GitHub Actions<br/>PR comment + status]
    L[(JSONL logs)] --> S3[(S3, KMS)] --> ATH[Athena SQL checks]
    L --> DUCK[DuckDB: same SQL] 
    L --> DRIFT[Drift: PSI / KS / z-test]
    L --> PROM[promote_failure.py] --> G
```

## Modes

| | Mock (`MOCK_LLM=1` or no key) | Real (`ANTHROPIC_API_KEY` set) |
|---|---|---|
| App model | `MockSupportLLM` (extractive, deterministic) | `claude-haiku-5-5` (`APP_MODEL`) |
| Judge | `HeuristicJudge` (lexical, deterministic) | `claude-sonnet-5-5` (`JUDGE_MODEL`) via `ClaudeJudge(DeepEvalBaseLLM)` |
| DeepEval | offline `BaseMetric` subclasses through `assert_test` / `deepeval test run` | Faithfulness, AnswerRelevancy, ContextualPrecision/Recall, Hallucination, GEval ×2, ToolCorrectness, KnowledgeRetention, ConversationCompleteness |
| Ragas | `NonLLMStringSimilarity` only | Faithfulness, AnswerRelevancy (local embeddings), ContextPrecision, ContextRecall |
| Baseline | `baselines/baseline.json` | `baselines/baseline.real.json` |
| Where | every PR (`ci.yml`) | nightly / manual (`evals-real.yml`) |

The gate refuses to compare runs across modes or embedding backends (exit code 2).
