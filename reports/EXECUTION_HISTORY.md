# Execution History

The active experiment is `execution-qwen-v1` on the unchanged `design-v1` scope. All experimental model calls use `qwen3.8-max` over the user-confirmed public endpoint `https://dashscope.aliyuncs.com/compatible-mode/v1`. The earlier workspace endpoint denied access. Credentials remain outside this project in user-bound encrypted storage.

## Preserved Historical Runs

- The interrupted Codex model attempt is archived under `outputs/archive_codex_aborted/`. None of its model outputs contribute to the active corpus review, representations, labels, audits or metrics.
- The first Qwen annotation transport used longer opaque references. Invalid responses were rejected rather than repaired or assigned inferred labels. Its call records remain available for budget accounting, but all formal and practice annotations were restarted under `blinded-annotation-v2-shortrefs`.
- Short references are assigned after the same seeded shuffle. They do not expose corpus identifiers, domain order, case types, strata, designer notes or retrieval outputs. Separate judge contexts share Qwen weights; they are not independent model families.

## Pre-Outcome Runtime Corrections

Both corrections are recorded with old/new code hashes and original seals in `data/input_freeze.json`. The original seals are retained under `data/freezes/`.

1. `runtime-validation-001`: validate exact anonymous generation references and nonempty outputs before caching. This allows rejected malformed output to be retried. Generation prompts, input data, configuration and token budgets were unchanged.
2. `runtime-transport-002`: replace miscopied long item references with short opaque references and checkpoint every submitted annotation task. All annotation roles use the new revision; old judge outputs cannot be mixed. The relevance rubric checksum, source corpus, raw cases, blinding and judge perspectives were unchanged. No finalized gold or retrieval results existed when this correction was made.

## Reporting Corrections

Report-only code reads the nested representation shape emitted by failure analysis, states all three provisional artifact types explicitly, and accepts the API adapter's documented backend alias in completion validation. These do not change labels, rankings, metrics or frozen experimental code.

The completion validator was also corrected to verify the exact 24-case audit ID list instead of comparing that list with the integer 24. Distinct failure-case IDs remain mandatory. Reports separate the winner among B1/B2/B3 from comparisons including B4; no model assessment or numeric metric is rewritten.

The frozen protocol is retained as a pre-execution snapshot. Its historical phrases "workspace endpoint" and "opaque hashes" are superseded only by the public endpoint and short-reference transport recorded above. It is not silently rewritten after outcomes.

The current generation validator rejects empty text/query slots as malformed output and allows at most two API attempts. This differs from design-v1's instruction to score an empty output with empty candidates rather than retry it to success. Retained generation evidence contains no observed empty text/query response: all 54 successful batch metadata records have attempt=1 and no prior failures; the preserved rejected batch omitted two expected references while its two returned rows each contained five nonempty queries. This deviation was not triggered in those records, but the pipeline's policy is disclosed rather than described as identical to design-v1.

Generation runs batch four cases in a fresh request. Provider-native prompt counts differ from the budget tokenizer: recorded successful generation prompts span 152704-203754 native tokens. The large shared context and case batching are validity and cost considerations; neither token units nor repeated calls should be mistaken for independent participants.

Provider-reported token usage is a recorded lower bound, not a billing invoice: superseded successful calls and rejected cached attempts are distinguished from experiment-used calls; failed attempts without usage metadata cannot be reconstructed. No human or clinician review is claimed.
