# Validity Notes

Labels: **PROVISIONAL_LLM_GOLD**. Semantic audits: **PROVISIONAL_LLM_AUDIT**. Research synthesis: **PROVISIONAL_LLM_RESEARCH_SYNTHESIS**.
## Five material threats

1. Provisional annotation: two LLM judges plus one LLM adjudicator are not independent human or clinical ground truth. Generator, both judges, adjudicator and semantic auditor use separate fresh contexts of the same Qwen model alias and therefore share weights. Their errors can be correlated. Agreement is reliability, not correctness; gold-driven retention audits inherit label errors.

2. Corpus/source identification: 96 atomic items derive from clustered authority sources and include many context-dependent educational items. Unsupported RHR/HRV conjunctions are absent. Some matched differences can concern generic or device-context relevance rather than the intended axis. Never infer that a matched score difference proves the planned distinction.

3. Synthetic small sample: 24 cases, 19 construction units and three repeated generations do not represent a natural wearable population. Numerical estimates, idealized timing and deterministic noise limit external validity. No real intervention or clinical effect is measured.

4. Resource and truncation confounds: B3 uses five retrieval operations; B1/B2/B4 use one. B1-B3 final text is capped at 256 cl100k tokens; hard post-generation truncation can remove information. B4 is a much longer deterministic reference and is subject to identical 512 lexical-token and 512 dense-subword truncation. Qwen API parameters temperature=0, enable_thinking=false and max_tokens=16384 are fixed for all roles. Provider sampling seed support is not assumed. The fixed model alias does not pin immutable provider weights; repeat generation can still differ despite temperature 0.

5. Retrieval and audit dependence: English regex BM25 and pinned BGE-M3 each impose format preferences. Low top-k recall does not prove information loss. Semantic audits use one LLM, are incompletely blinded to writing style, and cover selected positive-label facts. No proposed Personal Evidence representation is evaluated; additional information might still add noise.

## Recorded controls

All baseline inputs use the same raw/derived-statistics whitelist. No corpus, labels, categories or designer notes were visible during generation. Judges saw source-supported items and raw data only, with randomized opaque references. Corpus corrections occurred before annotation and retrieval; post-result changes are prohibited. API calls do not expose tools and reject tool-use responses. Missing values are not zero. All five matched constraints and statistics were independently recomputed.

Execution revision: `execution-qwen-v1`. Authorized Qwen API endpoint: `https://dashscope.aliyuncs.com/compatible-mode/v1`. Provider request IDs, returned model names and actual usage are preserved; no aborted archived Codex output contributes to this run.

Final representation truncation counts: {'B1': 0, 'B2': 0, 'B3': 0, 'B4': 0} out of 72 records per baseline (B4 has no generation budget).

Corpus source counts: {'CDC': 25, 'NIH / NHLBI': 27, 'NHS': 14, 'NIH / MedlinePlus': 3, 'Google Health / Fitbit': 21, 'NHS / MyHealth London': 5, 'CDC / NIOSH': 1}. Corpus verification means fetched sources, anchors, schema checks and independent fresh context LLM source review; no human expert review.

Cumulative recorded Qwen response budget: {'successful_call_metadata_count': 191, 'prompt_tokens': 16446810, 'completion_tokens': 831385, 'total_tokens': 17278195}. Cumulative recorded Qwen response budget, including superseded annotation and rejected cached-response attempts; archived runs and non-Qwen providers are excluded. Current-stage totals are separated and missing usage or billing cost is not inferred. If the API adapter's usage only covers the successful attempt, earlier billed failed/repair attempts are not included

## Scope of conclusion

No Personal Evidence method was implemented or tested, so its potential information-retention advantage cannot be evaluated. Among the executed baselines, retrievers disagree on the strongest condition: under BM25, Insight (B2) leads with nDCG@10 0.403 and Recall@10 0.209; under dense retrieval, deterministic numeric facts (B4) lead with nDCG@10 0.477 and Recall@10 0.320, while B2 achieves nDCG@10 0.475. QueryGen (B3) uses five RRF-fused retrieval operations per case, a resource advantage that prevents direct format comparison. The five automatically selected failure candidates (C008, C014, C020, C012, C018), chosen by largest mean Summary/Insight strong false-negative fraction, show high miss rates but do not isolate representation deficiency: semantic audits reveal retained facts alongside missed items, indicating ranking failures rather than wholesale information loss. Matched-pair analysis exposes conditional-versus-ranking limitations: for example, C003/C005 have 12 gold-different items, yet BM25 B1 retrieves none of the differing items at rank 10 in any repeat, while dense B1 retrieves some shared items (K011, K033, K078) identically for both cases, failing to discriminate. B4 produces identical candidate sets (Jaccard 1.0) for all matched pairs under BM25, confirming it cannot support conditional identification. PROVISIONAL_LLM_GOLD labels carry a nonzero-union disagreement rate of 0.271, limiting confidence in fine-grained relevance distinctions. Corpus source clustering (76 behavior/context items among 96 total) and provisional label error provide alternative explanations for recall ceilings below 1.0. Repeats at temperature=0 are not independent samples.

A negative result is allowed. No benchmark, prompt, corpus condition, threshold or hypothesis interpretation was changed to rescue C1 after retrieval results. Improvements to code address runtime/correctness defects; any new experimental comparison must be a separately declared run.

## Runtime history

See `EXECUTION_HISTORY.md` and the hash-recorded amendments in `data/input_freeze.json` for the public endpoint correction, short-reference annotation restart, and discarded generation batch. The frozen protocol's historical workspace/opaque-hash wording is not a description of the final transport. Empty representation slots are rejected and may be retried within two attempts, unlike design-v1's empty-candidates rule; no such empty response was observed in retained generation records. Four-case generation batching and large provider-native contexts also limit independence and cost comparability.

B4 matched-pair candidate identity is a result of this fixed representation/retriever setup, not proof that every factual representation is intrinsically unable to discriminate. Its long ledger is truncated at retrieval input; paired baseline histories are equal, so the early query portion can conceal later window differences. B4's dense mean nDCG is only slightly above Insight-style; inspect the saved paired intervals rather than calling this a reliable format advantage.
