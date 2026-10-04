# C1 Pilot Results

Label status: **PROVISIONAL_LLM_GOLD**. All observations are synthetic; no human ground truth, official PHIA or Personal Evidence method was run.

Research category: **E**. C1 status: **inconclusive**.

No Personal Evidence method was implemented or tested, so its potential information-retention advantage cannot be evaluated. Among the executed baselines, retrievers disagree on the strongest condition: under BM25, Insight (B2) leads with nDCG@10 0.403 and Recall@10 0.209; under dense retrieval, deterministic numeric facts (B4) lead with nDCG@10 0.477 and Recall@10 0.320, while B2 achieves nDCG@10 0.475. QueryGen (B3) uses five RRF-fused retrieval operations per case, a resource advantage that prevents direct format comparison. The five automatically selected failure candidates (C008, C014, C020, C012, C018), chosen by largest mean Summary/Insight strong false-negative fraction, show high miss rates but do not isolate representation deficiency: semantic audits reveal retained facts alongside missed items, indicating ranking failures rather than wholesale information loss. Matched-pair analysis exposes conditional-versus-ranking limitations: for example, C003/C005 have 12 gold-different items, yet BM25 B1 retrieves none of the differing items at rank 10 in any repeat, while dense B1 retrieves some shared items (K011, K033, K078) identically for both cases, failing to discriminate. B4 produces identical candidate sets (Jaccard 1.0) for all matched pairs under BM25, confirming it cannot support conditional identification. PROVISIONAL_LLM_GOLD labels carry a nonzero-union disagreement rate of 0.271, limiting confidence in fine-grained relevance distinctions. Corpus source clustering (76 behavior/context items among 96 total) and provisional label error provide alternative explanations for recall ceilings below 1.0. Repeats at temperature=0 are not independent samples.

## Execution coverage

24 cases (1008 day rows), 96 source-grounded items, two 2304-pair fresh-context Qwen judge matrices and 2304 adjudications, 288 representations (three repeats), and 576 retrieval runs across BM25 and dense. Semantic audits cover all 24 cases.

Model calls use the authorized Qwen API endpoint `https://dashscope.aliyuncs.com/compatible-mode/v1` and fixed alias `qwen3.8-max`. Fixed parameters: temperature=0, enable_thinking=False, max_tokens=16384; no provider sampling seed is assumed. Generator, both judges, adjudicator and semantic auditor share the same model alias. Separate contexts and shuffled inputs do not establish independent model families.

## Overall metrics

Case-level means after averaging three repeats; N/A denominators excluded, not scored as zero. Higher is better except Irrelevant@10.

| Retriever | Baseline | R@5 | R@10 | R@20 | Strong R@10 | nDCG@10 | Irrelevant@10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bm25 | Summary | 0.087 | 0.159 | 0.284 | 0.264 | 0.298 | 0.617 |
| bm25 | Insight-style | 0.121 | 0.209 | 0.359 | 0.328 | 0.403 | 0.508 |
| bm25 | QueryGen (5 queries) | 0.092 | 0.184 | 0.355 | 0.272 | 0.324 | 0.557 |
| bm25 | Raw statistical facts | 0.041 | 0.126 | 0.365 | 0.114 | 0.146 | 0.704 |
| dense | Summary | 0.140 | 0.223 | 0.416 | 0.373 | 0.426 | 0.469 |
| dense | Insight-style | 0.155 | 0.260 | 0.445 | 0.387 | 0.475 | 0.382 |
| dense | QueryGen (5 queries) | 0.117 | 0.206 | 0.370 | 0.368 | 0.387 | 0.507 |
| dense | Raw statistical facts | 0.163 | 0.320 | 0.461 | 0.372 | 0.477 | 0.242 |


## Judge reliability

Exact agreement: 0.879; linear weighted Cohen kappa: 0.748; non-zero disagreement rate: 0.084. Resolved comparison pairs: 2304; pairs pending either judge: 0; pending Judge A: 0; pending Judge B: 0.

| Judge A / Judge B | 0 | 1 | 2 |
| --- | --- | --- | --- |
| 0 | 1592 | 103 | 0 |
| 1 | 88 | 365 | 31 |
| 2 | 2 | 55 | 68 |


Matrix rows are Judge A, columns Judge B. Both judges use fresh contexts of the same Qwen model; shared weights and related prompts can induce correlated errors. Adjudication reviewed agreements as well as disputes.

All-zero cases: []; cases without grade 2: [].

## A/B/C and four case types

| Retriever | Baseline | Grouping | Group | R@5 | R@10 | R@20 | Strong R@10 | nDCG@10 | Irrelevant@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bm25 | B1 | case_type | multivariable | 0.068 | 0.134 | 0.254 | 0.196 | 0.231 | 0.639 |
| bm25 | B1 | case_type | personal_baseline | 0.112 | 0.192 | 0.329 | 0.277 | 0.355 | 0.550 |
| bm25 | B1 | case_type | single_variable | 0.068 | 0.142 | 0.269 | 0.338 | 0.282 | 0.689 |
| bm25 | B1 | case_type | temporal_pattern | 0.100 | 0.166 | 0.283 | 0.248 | 0.325 | 0.589 |
| bm25 | B1 | stratum | A | 0.096 | 0.185 | 0.307 | 0.327 | 0.341 | 0.575 |
| bm25 | B1 | stratum | B | 0.089 | 0.154 | 0.286 | 0.227 | 0.274 | 0.621 |
| bm25 | B1 | stratum | C | 0.076 | 0.137 | 0.258 | 0.240 | 0.279 | 0.654 |
| bm25 | B2 | case_type | multivariable | 0.113 | 0.188 | 0.333 | 0.325 | 0.415 | 0.506 |
| bm25 | B2 | case_type | personal_baseline | 0.123 | 0.201 | 0.370 | 0.298 | 0.375 | 0.544 |
| bm25 | B2 | case_type | single_variable | 0.125 | 0.239 | 0.366 | 0.447 | 0.438 | 0.483 |
| bm25 | B2 | case_type | temporal_pattern | 0.124 | 0.208 | 0.369 | 0.244 | 0.384 | 0.500 |
| bm25 | B2 | stratum | A | 0.132 | 0.228 | 0.369 | 0.322 | 0.419 | 0.487 |
| bm25 | B2 | stratum | B | 0.128 | 0.210 | 0.372 | 0.357 | 0.419 | 0.508 |
| bm25 | B2 | stratum | C | 0.104 | 0.189 | 0.337 | 0.307 | 0.371 | 0.529 |
| bm25 | B3 | case_type | multivariable | 0.089 | 0.190 | 0.341 | 0.261 | 0.322 | 0.489 |
| bm25 | B3 | case_type | personal_baseline | 0.096 | 0.181 | 0.363 | 0.325 | 0.339 | 0.578 |
| bm25 | B3 | case_type | single_variable | 0.097 | 0.202 | 0.386 | 0.371 | 0.371 | 0.561 |
| bm25 | B3 | case_type | temporal_pattern | 0.086 | 0.165 | 0.329 | 0.129 | 0.266 | 0.600 |
| bm25 | B3 | stratum | A | 0.089 | 0.173 | 0.356 | 0.248 | 0.293 | 0.604 |
| bm25 | B3 | stratum | B | 0.107 | 0.198 | 0.367 | 0.285 | 0.364 | 0.525 |
| bm25 | B3 | stratum | C | 0.080 | 0.182 | 0.343 | 0.282 | 0.317 | 0.542 |
| bm25 | B4 | case_type | multivariable | 0.038 | 0.115 | 0.349 | 0.099 | 0.129 | 0.700 |
| bm25 | B4 | case_type | personal_baseline | 0.045 | 0.134 | 0.379 | 0.186 | 0.182 | 0.700 |
| bm25 | B4 | case_type | single_variable | 0.038 | 0.130 | 0.366 | 0.085 | 0.133 | 0.717 |
| bm25 | B4 | case_type | temporal_pattern | 0.042 | 0.125 | 0.366 | 0.085 | 0.139 | 0.700 |
| bm25 | B4 | stratum | A | 0.045 | 0.134 | 0.376 | 0.085 | 0.145 | 0.700 |
| bm25 | B4 | stratum | B | 0.036 | 0.123 | 0.353 | 0.131 | 0.139 | 0.712 |
| bm25 | B4 | stratum | C | 0.040 | 0.121 | 0.366 | 0.125 | 0.152 | 0.700 |
| dense | B1 | case_type | multivariable | 0.117 | 0.208 | 0.391 | 0.309 | 0.398 | 0.444 |
| dense | B1 | case_type | personal_baseline | 0.159 | 0.246 | 0.437 | 0.442 | 0.461 | 0.433 |
| dense | B1 | case_type | single_variable | 0.155 | 0.232 | 0.427 | 0.369 | 0.442 | 0.506 |
| dense | B1 | case_type | temporal_pattern | 0.130 | 0.206 | 0.409 | 0.373 | 0.402 | 0.494 |
| dense | B1 | stratum | A | 0.146 | 0.220 | 0.415 | 0.410 | 0.415 | 0.504 |
| dense | B1 | stratum | B | 0.147 | 0.251 | 0.421 | 0.382 | 0.448 | 0.404 |
| dense | B1 | stratum | C | 0.128 | 0.198 | 0.412 | 0.328 | 0.415 | 0.500 |
| dense | B2 | case_type | multivariable | 0.141 | 0.250 | 0.425 | 0.359 | 0.464 | 0.333 |
| dense | B2 | case_type | personal_baseline | 0.159 | 0.266 | 0.443 | 0.418 | 0.478 | 0.394 |
| dense | B2 | case_type | single_variable | 0.165 | 0.270 | 0.445 | 0.476 | 0.497 | 0.422 |
| dense | B2 | case_type | temporal_pattern | 0.153 | 0.255 | 0.468 | 0.296 | 0.460 | 0.378 |
| dense | B2 | stratum | A | 0.149 | 0.258 | 0.456 | 0.427 | 0.462 | 0.417 |
| dense | B2 | stratum | B | 0.164 | 0.287 | 0.452 | 0.376 | 0.493 | 0.321 |
| dense | B2 | stratum | C | 0.150 | 0.236 | 0.428 | 0.359 | 0.469 | 0.408 |
| dense | B3 | case_type | multivariable | 0.113 | 0.210 | 0.352 | 0.336 | 0.410 | 0.439 |
| dense | B3 | case_type | personal_baseline | 0.117 | 0.190 | 0.339 | 0.300 | 0.343 | 0.567 |
| dense | B3 | case_type | single_variable | 0.128 | 0.231 | 0.422 | 0.554 | 0.438 | 0.506 |
| dense | B3 | case_type | temporal_pattern | 0.109 | 0.194 | 0.368 | 0.281 | 0.355 | 0.517 |
| dense | B3 | stratum | A | 0.109 | 0.198 | 0.363 | 0.345 | 0.331 | 0.554 |
| dense | B3 | stratum | B | 0.121 | 0.218 | 0.384 | 0.419 | 0.451 | 0.479 |
| dense | B3 | stratum | C | 0.120 | 0.202 | 0.363 | 0.339 | 0.378 | 0.487 |
| dense | B4 | case_type | multivariable | 0.151 | 0.298 | 0.439 | 0.342 | 0.455 | 0.217 |
| dense | B4 | case_type | personal_baseline | 0.166 | 0.344 | 0.468 | 0.564 | 0.575 | 0.217 |
| dense | B4 | case_type | single_variable | 0.170 | 0.324 | 0.452 | 0.267 | 0.417 | 0.300 |
| dense | B4 | case_type | temporal_pattern | 0.163 | 0.315 | 0.484 | 0.317 | 0.463 | 0.233 |
| dense | B4 | stratum | A | 0.158 | 0.327 | 0.465 | 0.370 | 0.462 | 0.263 |
| dense | B4 | stratum | B | 0.169 | 0.328 | 0.453 | 0.347 | 0.462 | 0.225 |
| dense | B4 | stratum | C | 0.161 | 0.306 | 0.464 | 0.400 | 0.508 | 0.238 |


## Matched pairs

Gold differences below are provisional labels, not proof of a medically meaningful temporal distinction. Full conditional-item results and all repeat rankings are in `outputs/metrics/matched_pairs.json`.

| Pair | Gold differences | Retriever | Baseline | Top10 Jaccard | Left nDCG | Right nDCG |
| --- | --- | --- | --- | --- | --- | --- |
| C003/C005 | 12 | bm25 | B1 | 0.278 | 0.219 | 0.367 |
| C003/C005 | 12 | bm25 | B2 | 0.300 | 0.271 | 0.355 |
| C003/C005 | 12 | bm25 | B3 | 0.281 | 0.212 | 0.287 |
| C003/C005 | 12 | bm25 | B4 | 1.000 | 0.072 | 0.106 |
| C003/C005 | 12 | dense | B1 | 0.667 | 0.503 | 0.424 |
| C003/C005 | 12 | dense | B2 | 0.495 | 0.350 | 0.487 |
| C003/C005 | 12 | dense | B3 | 0.448 | 0.451 | 0.628 |
| C003/C005 | 12 | dense | B4 | 1.000 | 0.304 | 0.235 |
| C009/C011 | 9 | bm25 | B1 | 0.285 | 0.370 | 0.220 |
| C009/C011 | 9 | bm25 | B2 | 0.231 | 0.437 | 0.433 |
| C009/C011 | 9 | bm25 | B3 | 0.113 | 0.669 | 0.202 |
| C009/C011 | 9 | bm25 | B4 | 1.000 | 0.213 | 0.170 |
| C009/C011 | 9 | dense | B1 | 0.470 | 0.657 | 0.379 |
| C009/C011 | 9 | dense | B2 | 0.470 | 0.667 | 0.526 |
| C009/C011 | 9 | dense | B3 | 0.337 | 0.664 | 0.196 |
| C009/C011 | 9 | dense | B4 | 1.000 | 0.525 | 0.775 |
| C016/C018 | 13 | bm25 | B1 | 0.272 | 0.192 | 0.443 |
| C016/C018 | 13 | bm25 | B2 | 0.433 | 0.314 | 0.254 |
| C016/C018 | 13 | bm25 | B3 | 0.461 | 0.252 | 0.134 |
| C016/C018 | 13 | bm25 | B4 | 1.000 | 0.150 | 0.114 |
| C016/C018 | 13 | dense | B1 | 0.581 | 0.396 | 0.334 |
| C016/C018 | 13 | dense | B2 | 0.735 | 0.451 | 0.323 |
| C016/C018 | 13 | dense | B3 | 0.508 | 0.195 | 0.221 |
| C016/C018 | 13 | dense | B4 | 1.000 | 0.562 | 0.474 |
| C021/C023 | 12 | bm25 | B1 | 0.166 | 0.099 | 0.311 |
| C021/C023 | 12 | bm25 | B2 | 0.340 | 0.481 | 0.506 |
| C021/C023 | 12 | bm25 | B3 | 0.225 | 0.268 | 0.178 |
| C021/C023 | 12 | bm25 | B4 | 1.000 | 0.136 | 0.104 |
| C021/C023 | 12 | dense | B1 | 0.674 | 0.264 | 0.391 |
| C021/C023 | 12 | dense | B2 | 0.595 | 0.344 | 0.460 |
| C021/C023 | 12 | dense | B3 | 0.281 | 0.398 | 0.408 |
| C021/C023 | 12 | dense | B4 | 1.000 | 0.364 | 0.394 |
| C022/C024 | 8 | bm25 | B1 | 0.322 | 0.290 | 0.222 |
| C022/C024 | 8 | bm25 | B2 | 0.310 | 0.358 | 0.336 |
| C022/C024 | 8 | bm25 | B3 | 0.418 | 0.523 | 0.541 |
| C022/C024 | 8 | bm25 | B4 | 1.000 | 0.137 | 0.130 |
| C022/C024 | 8 | dense | B1 | 0.397 | 0.447 | 0.509 |
| C022/C024 | 8 | dense | B2 | 0.632 | 0.541 | 0.522 |
| C022/C024 | 8 | dense | B3 | 0.439 | 0.479 | 0.585 |
| C022/C024 | 8 | dense | B4 | 1.000 | 0.438 | 0.497 |


## Knowledge group diagnostics

These counts use the same global top10 list, with no subgroup reranking or extra indexed fields. Device measurement-quality knowledge is separated from personal monitoring and behavior/context knowledge. Within-group irrelevant fraction is N/A when that group returns no candidate.

| Retriever | Baseline | Knowledge group | Items | R@10 | Strong R@10 | Top10 share | Within-group irrelevant@10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bm25 | B1 | behavior_and_context | 76 | 0.139 | 0.182 | 0.669 | 0.764 |
| bm25 | B1 | measurement_quality | 8 | 0.236 | 0.600 | 0.164 | 0.442 |
| bm25 | B1 | personal_monitoring | 12 | 0.147 | 0.285 | 0.167 | 0.193 |
| bm25 | B2 | behavior_and_context | 76 | 0.097 | 0.213 | 0.519 | 0.797 |
| bm25 | B2 | measurement_quality | 8 | 0.284 | 0.667 | 0.129 | 0.418 |
| bm25 | B2 | personal_monitoring | 12 | 0.314 | 0.274 | 0.351 | 0.159 |
| bm25 | B3 | behavior_and_context | 76 | 0.105 | 0.164 | 0.582 | 0.793 |
| bm25 | B3 | measurement_quality | 8 | 0.321 | 0.533 | 0.126 | 0.259 |
| bm25 | B3 | personal_monitoring | 12 | 0.242 | 0.274 | 0.292 | 0.249 |
| bm25 | B4 | behavior_and_context | 76 | 0.000 | 0.000 | 0.600 | 1.000 |
| bm25 | B4 | measurement_quality | 8 | 0.358 | 0.200 | 0.200 | 0.500 |
| bm25 | B4 | personal_monitoring | 12 | 0.208 | 0.232 | 0.200 | 0.021 |
| dense | B1 | behavior_and_context | 76 | 0.229 | 0.525 | 0.558 | 0.544 |
| dense | B1 | measurement_quality | 8 | 0.067 | 0.000 | 0.094 | 0.767 |
| dense | B1 | personal_monitoring | 12 | 0.273 | 0.225 | 0.347 | 0.292 |
| dense | B2 | behavior_and_context | 76 | 0.224 | 0.417 | 0.464 | 0.457 |
| dense | B2 | measurement_quality | 8 | 0.129 | 0.267 | 0.103 | 0.634 |
| dense | B2 | personal_monitoring | 12 | 0.348 | 0.283 | 0.433 | 0.258 |
| dense | B3 | behavior_and_context | 76 | 0.269 | 0.474 | 0.714 | 0.587 |
| dense | B3 | measurement_quality | 8 | 0.058 | 0.067 | 0.062 | 0.726 |
| dense | B3 | personal_monitoring | 12 | 0.180 | 0.146 | 0.224 | 0.282 |
| dense | B4 | behavior_and_context | 76 | 0.173 | 0.418 | 0.304 | 0.424 |
| dense | B4 | measurement_quality | 8 | 0.033 | 0.000 | 0.100 | 0.833 |
| dense | B4 | personal_monitoring | 12 | 0.599 | 0.367 | 0.596 | 0.050 |


## Paired uncertainty

19 construction clusters (five matched pairs plus fourteen single cases), 10000 bootstrap draws. Intervals describe this synthetic pilot; repeats and labels are not independent participants. All comparisons are exploratory because the planned Evidence comparison is intentionally absent.

| Retriever | A | B | Metric | B-A | 95% lower | 95% upper |
| --- | --- | --- | --- | --- | --- | --- |
| bm25 | B1 | B2 | strong_recall_at_10 | 0.064 | -0.000 | 0.123 |
| bm25 | B1 | B2 | ndcg_at_10 | 0.105 | 0.036 | 0.174 |
| bm25 | B1 | B3 | strong_recall_at_10 | 0.007 | -0.082 | 0.094 |
| bm25 | B1 | B3 | ndcg_at_10 | 0.026 | -0.047 | 0.097 |
| bm25 | B1 | B4 | strong_recall_at_10 | -0.151 | -0.238 | -0.064 |
| bm25 | B1 | B4 | ndcg_at_10 | -0.153 | -0.203 | -0.106 |
| bm25 | B2 | B3 | strong_recall_at_10 | -0.057 | -0.122 | 0.016 |
| bm25 | B2 | B3 | ndcg_at_10 | -0.079 | -0.151 | -0.008 |
| bm25 | B2 | B4 | strong_recall_at_10 | -0.215 | -0.294 | -0.141 |
| bm25 | B2 | B4 | ndcg_at_10 | -0.258 | -0.304 | -0.212 |
| bm25 | B3 | B4 | strong_recall_at_10 | -0.158 | -0.226 | -0.090 |
| bm25 | B3 | B4 | ndcg_at_10 | -0.179 | -0.235 | -0.126 |
| dense | B1 | B2 | strong_recall_at_10 | 0.014 | -0.059 | 0.090 |
| dense | B1 | B2 | ndcg_at_10 | 0.049 | 0.019 | 0.079 |
| dense | B1 | B3 | strong_recall_at_10 | -0.006 | -0.120 | 0.106 |
| dense | B1 | B3 | ndcg_at_10 | -0.039 | -0.093 | 0.012 |
| dense | B1 | B4 | strong_recall_at_10 | -0.001 | -0.113 | 0.093 |
| dense | B1 | B4 | ndcg_at_10 | 0.052 | -0.004 | 0.103 |
| dense | B2 | B3 | strong_recall_at_10 | -0.020 | -0.102 | 0.070 |
| dense | B2 | B3 | ndcg_at_10 | -0.088 | -0.149 | -0.028 |
| dense | B2 | B4 | strong_recall_at_10 | -0.015 | -0.119 | 0.082 |
| dense | B2 | B4 | ndcg_at_10 | 0.003 | -0.043 | 0.052 |
| dense | B3 | B4 | strong_recall_at_10 | 0.005 | -0.176 | 0.169 |
| dense | B3 | B4 | ndcg_at_10 | 0.091 | -0.006 | 0.186 |


## Qwen API usage

| Stage | Recorded response metadata | Prompt tokens | Completion tokens | Total tokens |
| --- | --- | --- | --- | --- |
| adjudication | 24 | 1528306 | 184134 | 1712440 |
| calibration | 12 | 151234 | 6963 | 158197 |
| judges | 62 | 3521258 | 445404 | 3966662 |
| other | 14 | 857802 | 13339 | 871141 |
| representations | 55 | 9123101 | 38532 | 9161633 |
| semantic_audit | 24 | 1265109 | 143013 | 1408122 |


Cumulative recorded Qwen response budget: {'successful_call_metadata_count': 191, 'prompt_tokens': 16446810, 'completion_tokens': 831385, 'total_tokens': 17278195}. Calls with incomplete provider usage: 0. Superseded annotations and rejected cached responses remain in the cumulative budget but do not contribute to experiment labels or metrics. Archived and non-Qwen calls are excluded. If the API adapter's usage only covers the successful attempt, earlier billed failed/repair attempts are not included Request IDs, returned model aliases and per-call details are retained in `outputs/metrics/qwen_api_usage.json`; this is token accounting, not a billing-cost estimate.

| Budget scope | Recorded response metadata | Prompt tokens | Completion tokens | Total tokens |
| --- | --- | --- | --- | --- |
| current_stage_calls | 170 | 15378337 | 723233 | 16101570 |
| rejected_model_attempt | 1 | 203381 | 401 | 203782 |
| superseded_annotation | 20 | 865092 | 107751 | 972843 |


## Recall denominators

When a case has more than ten positive items, Recall@10 cannot reach 1 even with an ideal ranking: its ceiling is 10 divided by the number of positives. Strong Recall@10 has the same ceiling for grade 2 items. Scores remain unchanged; below-one recall alone is not evidence of representation loss. nDCG@10 still compares against the ideal ten ranked gains.

| Case | Relevant items | Strong items | R@10 ceiling | Strong R@10 ceiling |
| --- | --- | --- | --- | --- |
| C001 | 23 | 4 | 0.435 | 1.000 |
| C002 | 23 | 3 | 0.435 | 1.000 |
| C003 | 19 | 3 | 0.526 | 1.000 |
| C004 | 18 | 7 | 0.556 | 1.000 |
| C005 | 24 | 4 | 0.417 | 1.000 |
| C006 | 24 | 9 | 0.417 | 1.000 |
| C007 | 17 | 1 | 0.588 | 1.000 |
| C008 | 23 | 4 | 0.435 | 1.000 |
| C009 | 24 | 6 | 0.417 | 1.000 |
| C010 | 22 | 6 | 0.455 | 1.000 |
| C011 | 22 | 5 | 0.455 | 1.000 |
| C012 | 31 | 12 | 0.323 | 0.833 |
| C013 | 21 | 6 | 0.476 | 1.000 |
| C014 | 26 | 2 | 0.385 | 1.000 |
| C015 | 35 | 6 | 0.286 | 1.000 |
| C016 | 24 | 7 | 0.417 | 1.000 |
| C017 | 22 | 10 | 0.455 | 1.000 |
| C018 | 21 | 3 | 0.476 | 1.000 |
| C019 | 24 | 6 | 0.417 | 1.000 |
| C020 | 26 | 11 | 0.385 | 0.909 |
| C021 | 21 | 7 | 0.476 | 1.000 |
| C022 | 30 | 7 | 0.333 | 1.000 |
| C023 | 30 | 4 | 0.333 | 1.000 |
| C024 | 28 | 8 | 0.357 | 1.000 |


## Current decision

Establish more reliable relevance identification before designing Personal Evidence. This requires reducing PROVISIONAL_LLM_GOLD disagreement through human audit of contested items, resolving corpus source-clustering effects on retrieval, and validating that matched-pair gold differences are consistently discriminable by at least one retriever. Only after these identification prerequisites are met can a retrieval-oriented Personal Evidence representation be meaningfully designed and compared.

The Qwen all-baseline comparison is BM25: Insight (B2), nDCG@10 0.403, Recall@10 0.209. Dense: B4, nDCG@10 0.477, Recall@10 0.320; B2 close at nDCG@10 0.475. Retrivers disagree; no single composite winner exists.. See `FAILURE_ANALYSIS.md` for mechanisms and `VALIDITY_NOTES.md` for limits.

## Text baseline comparison

Restricting to Summary, Insight-style and QueryGen, the highest observed mean nDCG@10 condition per retriever is shown below. This is a descriptive winner, not a significance claim. The separate Qwen synthesis also considers the B4 raw-statistics control; B4 is not one of these three text-generation baselines.

| Retriever | Best text baseline | nDCG@10 | R@10 |
| --- | --- | --- | --- |
| bm25 | Insight-style | 0.403 | 0.209 |
| dense | Insight-style | 0.475 | 0.260 |


## Agreement definitions

Non-zero disagreement means disagreement after binarizing labels to relevance > 0; grade 1 versus grade 2 is not counted in that binary rate. The reported rate uses all resolved pairs. Among the union of positive judgments, the same binary disagreement rate is 0.271. Exact agreement and weighted kappa retain the three ordinal grades.
