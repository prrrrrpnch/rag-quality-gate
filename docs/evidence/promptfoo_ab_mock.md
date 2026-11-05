# promptfoo A/B (real output, mock mode)

Command: `make promptfoo-ab` (promptfoo 0.125.1, `promptfoo/promptfooconfig.yaml`, 8 tests x 2 prompts x 2 models), run 2026-11-05.

In mock mode both "models" route to the same deterministic mock, so only the prompt axis is meaningful here.

| Prompt | Model label | Passed | Failed tests |
|---|---|---|---|
| prompt-v1 | claude-haiku-5-5 | 7/8 | out of scope -> refuse |
| prompt-v1 | claude-sonnet-5-5 | 7/8 | out of scope -> refuse |
| prompt-v2 | claude-haiku-5-5 | 6/8 | out of scope -> refuse, comparison across docs |
| prompt-v2 | claude-sonnet-5-5 | 6/8 | out of scope -> refuse, comparison across docs |

Finding: prompt v2 ("answer in ONE sentence") breaks comparison questions (only one product is quoted), so v1 stays the production prompt. The out-of-scope failure is a known mock weakness that also appears in the golden baseline (`oos-002`).
