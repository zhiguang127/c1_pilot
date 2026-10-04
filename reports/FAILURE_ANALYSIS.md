# Representation Failure Analysis

Observed retrieval errors are relative to **PROVISIONAL_LLM_GOLD**. Semantic retention is **PROVISIONAL_LLM_AUDIT**, independently checked against dates, paths and exact output excerpts. These are not medical truth or causal proof.

## Information retention

| Baseline | Cases | Retained | Omitted | Contradicted | Uncertain | Unsupported excerpts | Potential noise excerpts |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B1 | 24 | 0.422 | 0.127 | 0.009 | 0.443 | 7 | 25 |
| B2 | 24 | 0.472 | 0.182 | 0.005 | 0.340 | 35 | 29 |
| B3 | 24 | 0.545 | 0.210 | 0.017 | 0.227 | 35 | 49 |


Rates are case-weighted over correlated fact/repeat opportunities; up to eight relevant facts are selected per case. Accurate paraphrases are accepted. A missing exact number is not automatically information loss.

| Compared condition | Missing/contradicted opportunities | Recovered by QueryGen | Recovery fraction |
| --- | --- | --- | --- |
| B1 | 78 | 26 | 0.333 |
| B2 | 108 | 44 | 0.407 |


Semantic noise flags were generated without retrieval output. Check the saved false positives before attributing noise to them; longer outputs or five queries alone do not establish a causal effect.

## Five key failure cases

### C008

Design type: personal_baseline; stratum B. Mean Summary/Insight strong miss fraction across retrievers: 0.833.

| Retriever | Baseline | R@5 | R@10 | R@20 | Strong R@10 | nDCG@10 | Irrelevant@10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bm25 | B1 | 0.101 | 0.217 | 0.406 | 0.250 | 0.332 | 0.500 |
| bm25 | B2 | 0.159 | 0.246 | 0.406 | 0.167 | 0.349 | 0.433 |
| bm25 | B3 | 0.072 | 0.145 | 0.319 | 0.167 | 0.205 | 0.667 |
| bm25 | B4 | 0.043 | 0.130 | 0.348 | 0.000 | 0.106 | 0.700 |
| dense | B1 | 0.188 | 0.261 | 0.435 | 0.083 | 0.354 | 0.400 |
| dense | B2 | 0.174 | 0.304 | 0.449 | 0.167 | 0.417 | 0.300 |
| dense | B3 | 0.072 | 0.174 | 0.275 | 0.417 | 0.318 | 0.600 |
| dense | B4 | 0.217 | 0.391 | 0.478 | 0.250 | 0.499 | 0.100 |


Frequently missed grade-2 items across B1/B2/B3: K085 (Fitbit reports HRV using RMSSD): 17 runs; K001 (Adult sleep duration recommendations): 14 runs; K096 (Step counts depend on movement sensing and arm motion): 14 runs; K050 (Step count can miss non-step exercise intensity): 12 runs.

Audit facts with at least one omission or contradiction: Evening activity intervals consistently started at 21:00 local time in both baseline and window periods, with intensity recorded as unknown. [K071, K073]; Activity duration showed a small decrease from a baseline mean of 55.1 minutes to a window mean of 53.5 minutes, while low movement minutes increased slightly from 447.8 to 450.6 minutes. [K050, K065, K068]; Nighttime coverage remained sufficient for sleep metrics throughout the window, including on 2026-04-07 when daytime wear was insufficient, allowing sleep, RHR, and HRV to be recorded. [K090, K091, K095].

Complete raw data, every baseline output, top20, full gold, false positives and negatives: `outputs/case_analysis/C008.json`.

### C014

Design type: temporal_pattern; stratum A. Mean Summary/Insight strong miss fraction across retrievers: 0.792.

| Retriever | Baseline | R@5 | R@10 | R@20 | Strong R@10 | nDCG@10 | Irrelevant@10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bm25 | B1 | 0.115 | 0.205 | 0.359 | 0.167 | 0.380 | 0.467 |
| bm25 | B2 | 0.115 | 0.167 | 0.346 | 0.000 | 0.284 | 0.567 |
| bm25 | B3 | 0.103 | 0.192 | 0.359 | 0.167 | 0.373 | 0.500 |
| bm25 | B4 | 0.038 | 0.115 | 0.346 | 0.000 | 0.133 | 0.700 |
| dense | B1 | 0.128 | 0.179 | 0.359 | 0.500 | 0.409 | 0.533 |
| dense | B2 | 0.128 | 0.244 | 0.462 | 0.167 | 0.427 | 0.367 |
| dense | B3 | 0.077 | 0.179 | 0.372 | 0.167 | 0.287 | 0.533 |
| dense | B4 | 0.154 | 0.269 | 0.462 | 0.000 | 0.426 | 0.300 |


Frequently missed grade-2 items across B1/B2/B3: K085 (Fitbit reports HRV using RMSSD): 17 runs; K001 (Adult sleep duration recommendations): 12 runs.

Audit facts with at least one omission or contradiction: Daytime wear minutes were exactly 720 for every observation in both the baseline and the window, meeting the quality policy requirement. [K096].

Complete raw data, every baseline output, top20, full gold, false positives and negatives: `outputs/case_analysis/C014.json`.

### C020

Design type: multivariable; stratum A. Mean Summary/Insight strong miss fraction across retrievers: 0.773.

| Retriever | Baseline | R@5 | R@10 | R@20 | Strong R@10 | nDCG@10 | Irrelevant@10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bm25 | B1 | 0.103 | 0.192 | 0.308 | 0.061 | 0.198 | 0.500 |
| bm25 | B2 | 0.103 | 0.167 | 0.321 | 0.212 | 0.313 | 0.567 |
| bm25 | B3 | 0.064 | 0.167 | 0.333 | 0.121 | 0.252 | 0.567 |
| bm25 | B4 | 0.038 | 0.115 | 0.385 | 0.182 | 0.171 | 0.700 |
| dense | B1 | 0.103 | 0.179 | 0.385 | 0.333 | 0.412 | 0.533 |
| dense | B2 | 0.141 | 0.231 | 0.423 | 0.303 | 0.543 | 0.400 |
| dense | B3 | 0.064 | 0.167 | 0.333 | 0.121 | 0.211 | 0.567 |
| dense | B4 | 0.154 | 0.308 | 0.462 | 0.545 | 0.692 | 0.200 |


Frequently missed grade-2 items across B1/B2/B3: K068 (Sedentary behaviour requires posture and context): 18 runs; K081 (HRV depends on personal and lifestyle context): 18 runs; K084 (HRV trends are wellness observations, not diagnoses): 18 runs; K085 (Fitbit reports HRV using RMSSD): 18 runs.

Audit facts with at least one omission or contradiction: Mean sleep duration was nearly unchanged: 469.8 minutes at baseline versus 470.6 minutes in the window, a difference of 0.8 minutes. Sleep end time was fixed at 07:00 (1140 minutes from noon) in all observations. [K001, K007, K015, K094]; Evening activity intervals shortened substantially: baseline intervals starting at 21:00 lasted approximately 50-60 minutes, while window intervals starting at 21:00 lasted approximately 8-12 minutes. [K048, K073]; Daytime low movement intervals lengthened from approximately 44-47 minute blocks in the baseline to approximately 60-61 minute blocks in the window, while maintaining 10 intervals per day. [K057, K068].

Complete raw data, every baseline output, top20, full gold, false positives and negatives: `outputs/case_analysis/C020.json`.

### C012

Design type: personal_baseline; stratum C. Mean Summary/Insight strong miss fraction across retrievers: 0.771.

| Retriever | Baseline | R@5 | R@10 | R@20 | Strong R@10 | nDCG@10 | Irrelevant@10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bm25 | B1 | 0.108 | 0.172 | 0.301 | 0.167 | 0.362 | 0.467 |
| bm25 | B2 | 0.043 | 0.129 | 0.290 | 0.167 | 0.223 | 0.600 |
| bm25 | B3 | 0.075 | 0.151 | 0.312 | 0.306 | 0.388 | 0.533 |
| bm25 | B4 | 0.032 | 0.097 | 0.323 | 0.250 | 0.228 | 0.700 |
| dense | B1 | 0.129 | 0.194 | 0.398 | 0.333 | 0.479 | 0.400 |
| dense | B2 | 0.097 | 0.161 | 0.355 | 0.250 | 0.402 | 0.500 |
| dense | B3 | 0.097 | 0.161 | 0.366 | 0.194 | 0.294 | 0.500 |
| dense | B4 | 0.129 | 0.258 | 0.387 | 0.500 | 0.704 | 0.200 |


Frequently missed grade-2 items across B1/B2/B3: K068 (Sedentary behaviour requires posture and context): 18 runs; K082 (Personal ranges provide recent-trend context): 18 runs; K084 (HRV trends are wellness observations, not diagnoses): 18 runs; K094 (Estimated time asleep is different from the full sleep period): 17 runs.

Audit facts with at least one omission or contradiction: Daily steps showed no meaningful change between baseline (mean 8039) and window (mean 8008), while activity duration increased by approximately 2.6 minutes (from 55.2 to 57.8 min). [K046, K050, K096]; Low movement minutes increased slightly from a baseline mean of 449.71 to a window mean of 452.36, with each day containing exactly 10 low-movement intervals during daytime hours. [K057, K068]; A single evening activity interval occurred daily starting at 21:00, with intensity recorded as unknown, ending between 21:50 and 22:00. [K071, K073].

Complete raw data, every baseline output, top20, full gold, false positives and negatives: `outputs/case_analysis/C012.json`.

### C018

Design type: temporal_pattern; stratum C. Mean Summary/Insight strong miss fraction across retrievers: 0.750.

| Retriever | Baseline | R@5 | R@10 | R@20 | Strong R@10 | nDCG@10 | Irrelevant@10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bm25 | B1 | 0.111 | 0.190 | 0.270 | 0.444 | 0.443 | 0.600 |
| bm25 | B2 | 0.111 | 0.190 | 0.349 | 0.111 | 0.254 | 0.600 |
| bm25 | B3 | 0.063 | 0.127 | 0.286 | 0.000 | 0.134 | 0.733 |
| bm25 | B4 | 0.048 | 0.143 | 0.381 | 0.000 | 0.114 | 0.700 |
| dense | B1 | 0.127 | 0.190 | 0.333 | 0.333 | 0.334 | 0.600 |
| dense | B2 | 0.175 | 0.222 | 0.460 | 0.111 | 0.323 | 0.533 |
| dense | B3 | 0.095 | 0.175 | 0.349 | 0.222 | 0.221 | 0.633 |
| dense | B4 | 0.190 | 0.381 | 0.476 | 0.333 | 0.474 | 0.200 |


Frequently missed grade-2 items across B1/B2/B3: K068 (Sedentary behaviour requires posture and context): 18 runs; K085 (Fitbit reports HRV using RMSSD): 15 runs; K001 (Adult sleep duration recommendations): 10 runs.

Audit facts with at least one omission or contradiction: In the window period, daytime activity intervals changed to brief 1-minute bouts approximately every 20 minutes from around 10:16 to 20:17, replacing the longer ~44-45 minute blocks seen during baseline daytime hours. [K048, K050]; Evening activity intervals shortened in the window period (e.g., 21:00-21:27 on 2026-03-30) compared to baseline evening blocks that typically lasted 50-60 minutes (e.g., 21:00-21:56 on 2026-03-02). [K071, K073]; Daily step counts remained stable between baseline (mean 8025.5) and window (mean 8038.3), a negligible difference of approximately 12.8 steps. [K050, K096].

Complete raw data, every baseline output, top20, full gold, false positives and negatives: `outputs/case_analysis/C018.json`.

## Matched-pair discrimination

| Pair | Different labels | Identifiable under provisional gold |
| --- | --- | --- |
| C003/C005 | 12 | True |
| C009/C011 | 9 | True |
| C016/C018 | 13 | True |
| C021/C023 | 12 | True |
| C022/C024 | 8 | True |


Candidate lists changing is not itself correct discrimination. Conditional item ranks and the raw observation axis must agree; inspect item-level records, particularly grade 0/1 uncertainty and unsupported conjunctions.

## Design-sensitive cases without a QueryGen penalty

Cases where QueryGen did not improve nDCG by at least 0.05 over the better of Summary/Insight in either retriever: ['C003', 'C004', 'C008', 'C016']. This is a retrieval diagnostic, not proof that all information was retained or that the case is intrinsically insensitive.

The five failure candidates exhibit high strong false-negative fractions across Summary, Insight, and QueryGen, but semantic audits confirm that many relevant facts are retained in representations while corresponding knowledge items remain unranked in top-10 results. Missed items coexist with retained facts, pointing to ranking limitations, corpus coverage gaps from source clustering, missing contextual conditions in knowledge applicability, and provisional label noise rather than systematic information destruction by compression. Identical B4 candidate sets across matched pairs and partial overlap in generative methods further indicate that current retrieval configurations lack the discrimination needed to attribute failures specifically to representation format.

## Research category

E: inconclusive. No Personal Evidence method was implemented or tested, so its potential information-retention advantage cannot be evaluated. Among the executed baselines, retrievers disagree on the strongest condition: under BM25, Insight (B2) leads with nDCG@10 0.403 and Recall@10 0.209; under dense retrieval, deterministic numeric facts (B4) lead with nDCG@10 0.477 and Recall@10 0.320, while B2 achieves nDCG@10 0.475. QueryGen (B3) uses five RRF-fused retrieval operations per case, a resource advantage that prevents direct format comparison. The five automatically selected failure candidates (C008, C014, C020, C012, C018), chosen by largest mean Summary/Insight strong false-negative fraction, show high miss rates but do not isolate representation deficiency: semantic audits reveal retained facts alongside missed items, indicating ranking failures rather than wholesale information loss. Matched-pair analysis exposes conditional-versus-ranking limitations: for example, C003/C005 have 12 gold-different items, yet BM25 B1 retrieves none of the differing items at rank 10 in any repeat, while dense B1 retrieves some shared items (K011, K033, K078) identically for both cases, failing to discriminate. B4 produces identical candidate sets (Jaccard 1.0) for all matched pairs under BM25, confirming it cannot support conditional identification. PROVISIONAL_LLM_GOLD labels carry a nonzero-union disagreement rate of 0.271, limiting confidence in fine-grained relevance distinctions. Corpus source clustering (76 behavior/context items among 96 total) and provisional label error provide alternative explanations for recall ceilings below 1.0. Repeats at temperature=0 are not independent samples.

## Audit verification limits

There were 755 date/path/excerpt verification notes. Invalid daily-observation paths and unverifiable retained/contradicted excerpts downgrade the affected checks to uncertain; these are auditor limitations, not evidence that a baseline omitted the fact. Model status, corrected status and original response remain available for review. No post-outcome quotation repair or semantic relabelling was used to improve the hypothesis result.
