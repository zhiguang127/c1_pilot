# C1 Pilot Benchmark

Design: `design-v1`. Active execution: `execution-qwen-v1`.

This project implements the requested pilot, not a new benchmark. Execution is complete: `outputs/metrics/pilot_validation.json` reports `valid=true`, `status=COMPLETE`, with all ten stages passing. All 87 offline tests pass. This certifies artifact integrity, not clinical validity or support for C1.

The research conclusion is **E / inconclusive**. Among Summary, Insight-style and QueryGen, Insight-style has the highest observed mean nDCG@10 for both BM25 (0.403) and dense (0.475). B4's dense mean is 0.477, a small descriptive difference with important length/truncation confounds. Low recall alone does not identify compression loss.

Read [PILOT_RESULTS.md](reports/PILOT_RESULTS.md), [FAILURE_ANALYSIS.md](reports/FAILURE_ANALYSIS.md) and [VALIDITY_NOTES.md](reports/VALIDITY_NOTES.md). All labels remain provisional, with shared-family Qwen judges and no human clinical review.

## Fixed Scope

- 24 deterministic synthetic wearable cases, with 28 baseline days and 14 current days each.
- 96 authority-source knowledge items with fetched snapshots, support anchors and applicability; no invented clinical triggers.
- All 2304 pairs independently judged twice and reviewed by an adjudicator. Labels are **PROVISIONAL_LLM_GOLD**, never human ground truth.
- B1 strong longitudinal Summary, B2 Insight-style (not official PHIA), B3 five-query generation, B4 deterministic statistical facts. No Personal Evidence method.
- Identical title/content corpus, fixed BM25 and immutable BGE-M3 retrieval configuration for every baseline.
- Overall, A/B/C, four case types, five matched-pair comparisons, and per-case failure records.

Original design documents and schemas remain under `docs/` and `schemas/`. Execution amendments and limitations are in [EXECUTION_PROTOCOL.md](docs/EXECUTION_PROTOCOL.md).

The pre-execution protocol remains frozen. Endpoint/anonymous-reference transport corrections and preserved earlier attempts are documented in [EXECUTION_HISTORY.md](reports/EXECUTION_HISTORY.md); no previous annotation revision contributes to active labels.

## Model And Credentials

All active model calls use `qwen3.8-max` through the user-authorized API in `config/experiment.json`. Temperature is 0, thinking is disabled, and API outputs are bounded. Two judge contexts and one adjudicator context share model weights, so their errors are not independent model-family errors. Three generation repeats may be identical.

`C1_PILOT_API_KEY` is read only from the process environment. On this Windows machine, `scripts/run_with_qwen.ps1` can provision that environment from user-bound DPAPI storage outside this project. Neither the key nor authorization headers are stored in code, prompts or experiment logs. The wrapper restores the previous environment when it exits.

The aborted Codex-based model run is preserved under `outputs/archive_codex_aborted/` and excluded from all active results. The current model boundary refuses Codex execution.

## Execution

The pinned virtual environment and embedding snapshot are already installed locally. For a clean installation:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
```

Run after setting the credential environment or configuring the local DPAPI credential:

```powershell
.\scripts\run_with_qwen.ps1 src/run_pilot.py --from-stage source_review --through-stage analysis
```

This validates cases and cached source snapshots, performs source-only review, freezes inputs, generates representations, calibrates and annotates, retrieves, evaluates, and audits information retention. It fails closed on unsupported source claims, malformed output, unresolved final labels, or changed frozen inputs. Successful model calls are cached by exact input/config hashes; unchanged reruns resume without paying for successful calls again.

After actual metrics and audits are complete, Qwen synthesizes the explicit A/B/C/D/E assessment in `reports/research_assessment.json`, then reports are rendered and validated. This is also provisional model interpretation, not clinical or human adjudication:

```powershell
.\scripts\run_with_qwen.ps1 src/run_pilot.py --from-stage assessment --through-stage validation
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Do not adjust cases, labels, corpus or prompts after inspecting retrieval outcomes to rescue the hypothesis. A negative or inconclusive result is valid.

## Artifacts

Authoritative datasets are `data/wearable_cases.jsonl`, `data/knowledge_items.jsonl` and `data/relevance_labels_provisional.csv`. Judge opinions, adjudication and practice records are in `annotations/`. Model prompts/results/usage are in `outputs/llm_calls/`; generated representations, retrieval rankings, metrics and full case records have separate `outputs/` subdirectories.

Final reports are `reports/PILOT_RESULTS.md`, `reports/FAILURE_ANALYSIS.md` and `reports/VALIDITY_NOTES.md`. The empty top-level data containers from design-v1 are retained for historical continuity and are not experimental input.

Source verification is fetched-source and machine/LLM review, not independent human clinical review. Cases are synthetic and results are research diagnostics, not medical advice.
