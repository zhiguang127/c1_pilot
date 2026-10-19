# Experiment C0-A — explanation-chain audit preparation

Status: **PREPARED_NOT_ANNOTATED**. No independent human Gold, verified chain failure, or behavioral-faithfulness result exists. See [C0A_READOUT.md](C0A_READOUT.md) for the actual original-machine execution and aggregate denominators.

This offline diagnostic uses existing frozen B0 predictions. It makes no API/model requests, trains no model, and runs no new counterfactual intervention. It does not presume a chain-level failure or justify new training. Synthetic unit-test fixtures are engineering checks, never human judgments.

## Frozen scope

- Parent: draft, unmerged B0 PR #3, `research/experiment-b0-sota`, checked at `b15a4583c44760ca7ce966d153e17e351cb116d4`. The pushed C0 branch is stacked on B0. C0 draft-PR creation was blocked by GitHub integration permissions (HTTP 403); no C0 PR was created, and no alternate credential/channel was used. The intended base is B0; keep both PRs draft and unmerged when C0 can be created.
- All 16 participants' earliest 42-day windows; five original candidates each: K006, K017, K041, K083, K094. A1 alternative candidate panels are excluded.
- Six diagnostic arms: Direct, RE2-style prompting (not fine-tuned RE2), Self-Refine-adapted, CRITIC-adapted, budget-matched CRITIC, S4 candidate-relative prompting. These are existing B0 arms, not a new algorithm.
- B0 provides no explicit user goal or unique priority policy. Use **UNDETERMINED** for priority/contrastive judgments that require that missing information. Physiological observations do not supply a user's goal.

## Reproduction on the original research machine

From the project root with Python 3.11+ (standard library only):

```powershell
python -m unittest discover -s research/problem_reidentification/experiment_c0/tests -t . -v
python -m research.problem_reidentification.experiment_c0.pilot public-audit
python -m research.problem_reidentification.experiment_b0.run verify
python -m research.problem_reidentification.experiment_c0.pilot prepare-local --output research/problem_reidentification/experiment_c0/local/c0a-v1
```

The last destination now exists on this machine. Preparation refuses overwrites; a later authorized replay must use a new version. `public-audit --input research/problem_reidentification/experiment_c0/results/source_public_summary_subset.json` reproduces the same aggregate preflight without private B0 data. This subset was compared against the full local public summary.

`prepare-local` checks B0 code/protocol and upstream-pin hashes, manifest self-hash, P1 release, the 16 frozen payload hashes, participant/window/candidate identity, all 96 diagnostic run slots and their input hashes, accepted-output schemas, and agreement with public B0 status counts. Missing inputs/runs block with `BLOCKED_MISSING_PRIVATE_DATA`; inconsistent frozen inputs/outputs block with `BLOCKED_FREEZE_MISMATCH`. Neither condition triggers synthesis, repair, retries, or inference. Detailed stderr/errors remain in ignored local logs.

The real preparation uses a secret random seed stored only under `steward/`. Rerunning `make_cards` with that seed and unchanged source files reproduces the cards. Source-run hashes and output byte hashes are recorded privately. The public fixed seed is only a default for synthetic tests.

## Private layout and distribution boundary

All paths below are relative to `local/c0a-v1/`, which is Git-ignored:

| File | Rows | Access |
| --- | ---: | --- |
| `review_packets/stage1/stage1_cases.jsonl` | 16 | Raters at stage 1 |
| `review_packets/stage1/stage1_rater_A_TEMPLATE.jsonl` | 16 | Rater A's blank template |
| `review_packets/stage1/stage1_rater_B_TEMPLATE.jsonl` | 16 | Rater B's blank template |
| `review_packets/stage2/stage2_explanations.jsonl` | 140 | Withhold until both stage-1 submissions are frozen |
| `review_packets/stage2/stage2_rater_A_TEMPLATE.jsonl` | 140 | Rater A at stage 2 |
| `review_packets/stage2/stage2_rater_B_TEMPLATE.jsonl` | 140 | Rater B at stage 2 |
| `steward/STUDY_STEWARD_ONLY_crosswalk.jsonl` | 156 | Steward only; 16 case + 140 explanation mappings |
| `steward/all_slots.jsonl` | 96 | Steward only; every planned diagnostic slot |
| `steward/all_failure_slots.jsonl` | 21 | Steward only; original error/validation details |
| `steward/reproducibility.json` | JSON | Steward only; seed and 160 main-run file hashes |
| `manifest.json` | JSON | Steward; aggregate state plus ten artifact paths, bytes, hashes and row counts |

Do not give reviewers the entire preparation directory. Release only the appropriate stage packet and each rater's own template. Neither the steward directory, the other rater's labels, nor execution logs belong in a review packet. Keep all filled submissions, identities, attestations, adjudications and hashes local. The code creates both stages; the steward enforces their sequential release. No stage has actually been released or annotated here.

Stage 1 contains frozen daily data, quality/context, source excerpts and shuffled original candidates, without predictions or canonical case/subject identifiers. Stage 2 contains the original ranking and original item explanations/evidence for strict top-tier versus immediately next-tier pairs. Ties are not forced; fully tied outputs receive a null-pair card. Missing pairwise wording is recorded, not automatically scored as failure. Invalid/failed outputs keep their method-window denominator and never acquire invented explanations.

Exact method identifiers and source identities are scanned before writing. Explanations are not rewritten to hide self-identification: a detected identifier blocks preparation for steward review. Linguistic style may still suggest a method, so passing this scan does not establish empirical blinding or behavioral faithfulness.

## Next human steps — not yet executed

1. Recruit two independent human raters and a separate adjudicator. Privately record identities, independence, rubric version, and attestations that neither rater has viewed stage 2, method mappings, Silver/Qwen labels, or the other's judgments. Resolve rubric questions before outcome inspection; record any calibration separately from study labels.
2. Give each rater only stage 1. Independently label every case's `source_scope` as `VALID / ISSUE / UNCERTAIN` and `priority_determinable` as `YES / NO / UNDETERMINED`, with evidence-based notes. Use `UNDETERMINED` where a missing goal/policy prevents a priority judgment. Original source conditions are draft, not human confirmed; the frozen excerpts are not complete articles. Mark scope uncertainty rather than importing Qwen source judgments or silently changing sources.
3. Collect both completed stage-1 files independently. Validate completeness and allowed values, retain originals, compute SHA-256 hashes with `Get-FileHash`, and record a dated freeze manifest before either rater sees stage 2. Store the submissions separately from blank templates. Corrections require a versioned amendment, not replacement. The pipeline does not claim this freeze has happened.
4. Release stage 2 after both freezes. Independently score `evidence_grounding` (`PASS / FAIL / UNCERTAIN`), `local_support` (`SUPPORTED / UNSUPPORTED / UNCERTAIN`), and `contrastive_support` (`SUPPORTED / UNSUPPORTED / UNDETERMINED`). `UNDETERMINED` replaces the bundle's spelling `UNDERDETERMINED`. Record reference/value/time, source-scope, unsupported context, missing goal/policy and non-discriminative-reason issues in `error_tags` and notes. Do not infer internal causal dependence from explanation text.
5. Freeze both stage-2 submissions and measure pre-adjudication agreement only after real labels exist. A third reviewer independently resolves genuine disagreements using the evidence and rubric while method identity remains hidden. Preserve both original judgments, the resolution and its rationale. Do not force consensus, a total ranking, or a unique Top-1.
6. Keep all correctness, explanation-fidelity, behavioral-faithfulness, decision-improvement and agreement metrics **null** until the corresponding independent evidence exists. Text review alone cannot establish behavioral faithfulness. Any eventual public report must aggregate by method with all 16 planned windows in view, disclose invalid/failed/excluded cases and source-scope decisions, and account for clustering within 16 participants. The 140 pair cards are not independent participants or 140 valid method-window outputs.

If no independently confirmed, well-defined repeatable failure survives strong simple/feedback/tool baselines, stop the new-training track and report that negative finding. Do not rescue the hypothesis by changing B0 predictions, sources, protocols or policies. Any C0-B requires independently defined goals/policies, an appropriate held-out design and an explicitly authorized budget; it is outside C0-A.

## Public release boundary

Only C0 code, engineering test outcomes and aggregate results are committed. Raw 42-day data, canonical participant/case IDs, model explanations, Silver labels, credentials, seeds, private previews/crosswalks, detailed failure logs and rater-level judgments must remain ignored locally. `results/local_execution_summary.json` is an aggregate allowlist export; `manifest.json` and its private artifact hashes are not copied into the PR.
