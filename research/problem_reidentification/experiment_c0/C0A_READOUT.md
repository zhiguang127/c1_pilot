# C0-A original-machine readout — 2026-10-18

Status: **PREPARED_NOT_ANNOTATED**. Human raters recorded: **0**. Independent human Gold: **0**. The explanation-chain failure hypothesis remains **unestablished**. This preparation supplies no positive or negative accuracy/fidelity result, and supports no proposal for chain-level training.

## Provenance and unchanged inputs

Fetched live upstream branches and inspected draft PR #3 before creating `research/experiment-c0-chain-audit` on B0. The local, remote and PR heads all matched the requested reference `b15a4583c44760ca7ce966d153e17e351cb116d4`. PR #3 was open, draft and unmerged; no changed-head conflict was found. C0 targets `research/experiment-b0-sota` and remains draft/unmerged.

- Upstream main: `17943de366f15b38b8255e5978d67f2dc8b3960a`.
- Upstream Experiment A: `18e2fa2e59e14fd69ef4400bd9d38831128bf0f7`.
- B0 source `results/comparison.json` Git blob: `4d28ec893cd5cc25c7ef859e248177e7eac8783f`.
- B0 freeze ID: `df9d7c385ee56d0c0521ed79e8bdfdd689e7dcd25ceb042ce6b748c533941791`.
- P1 release ID: `872d04eb05394b3f3ac37c05dcefe320181e9375a674ba7c4fb57c8853742604`.

Copied the supplied C0 bundle into a previously absent C0 directory, then hardened C0's freeze/run verification, private ID seed and steward separation. No B0/Experiment A predictions, sources or protocols were changed. The execution Git HEAD was the B0 parent because C0 was then uncommitted; the exact C0 Python byte hashes are in `results/local_execution_summary.json`, and the C0 commit is recorded by the draft PR. This avoids claiming the parent commit contains C0.

## Exact denominators and failed-run accounting

All **16/16** frozen payload hashes match. Each case is a different participant's earliest **42-day** window with **five original candidates**, yielding 672 daily rows and 80 case-candidate combinations. Main B0 storage contains 160 method-window records across ten arms; C0 selects exactly six arms and **96/96 planned slots**. There are **0 missing records**, **75 valid outputs**, **12 recorded failures**, and **9 invalid outputs**. No failed/invalid case was dropped or retried.

| Diagnostic arm | Planned windows | Valid outputs | Failed | Invalid | Explanation pair cards |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct | 16 | 15 | 1 | 0 | 33 |
| RE2-style prompting | 16 | 12 | 2 | 2 | 19 |
| Self-Refine-adapted | 16 | 15 | 1 | 0 | 26 |
| CRITIC-adapted | 16 | 11 | 3 | 2 | 21 |
| Budget-matched CRITIC | 16 | 13 | 1 | 2 | 23 |
| S4 candidate-relative prompting | 16 | 9 | 4 | 3 | 18 |
| **Total** | **96** | **75** | **12** | **9** | **140** |

The 140 cards cover strict top-tier versus immediately next-tier comparisons from 75 accepted outputs; they are clustered within 16 participants. No accepted output is fully tied. Structural acceptance, failure counts and card counts are engineering measurements, not correctness or explanation-fidelity measurements. Original failure/error details are in ignored steward storage only.

The full public B0 aggregate still reports **200/200 planned records**, including its other arms and previously executed candidate-order interventions. This C0 run executed **zero** such interventions. As secondary analysis only, B0's existing Direct reversal comparison has identical complete ordering in **0/4** paired windows and matching pair relations in **23/40** pairs. These pairs belong to only four participant windows. They establish neither explanation fidelity nor ranking correctness, and no inference is made from the ambiguous self-reported identifiability field.

## Executed checks

All four required commands exited **0**. Stdout, stderr and JSON exit/timestamp/argument records are under ignored `local/execution-20261018/`. The supplied bundle's **8** tests passed initially; after C0 hardening, **17/17** engineering tests passed. The supplied readout's historical claim of seven tests was not reused.

`public-audit` on the actual B0 summary exactly matches replay from the supplied minimal public subset. `experiment_b0.run verify` passed, including 77 legacy frozen hashes and the P1/A1 release verification. C0 additionally verified the B0 manifest self-hash, all frozen code/protocol hashes, upstream pins, P1 identity, 16 participant/window/candidate identities and payload hashes, all 96 diagnostic input hashes and status slots, and all 75 accepted-output schemas.

The private audit replayed all 16 case cards, all 140 explanation cards, the 156-row crosswalk and 21 failure slots with network/model calls blocked. All ten output artifacts' hashes/sizes/counts and all 160 source main-run file hashes matched. All **312 template rows** remain blank. Generated cards have zero scanned method identifiers, zero canonical participant/case identifiers and no stage-1 prediction metadata. Original daily/source evidence and stage-2 output content are preserved except removal of source identity fields from stage 1 and shuffled candidate/card presentation. Masking checks do not establish empirical rater blinding or behavioral faithfulness.

## Private handoff and stopping status

Local root: `research/problem_reidentification/experiment_c0/local/c0a-v1/`. It contains `manifest.json`, stage-specific packets under `review_packets/stage1/` and `review_packets/stage2/`, and separate `steward/` files. The [README manifest and human instructions](README.md#private-layout-and-distribution-boundary) give exact relative filenames, row counts, release order and freeze steps. The private manifest supplies exact bytes and SHA-256 values without putting those artifacts in the public PR.

No human annotation was conducted, simulated or inferred from Qwen/Silver labels. Two independent humans must first review stage 1 and freeze their submissions before receiving stage 2. Methods stay hidden through independent stage-2 review and third-party adjudication. Missing goals/policies require **UNDETERMINED**; unresolved source scope remains uncertain, not a model error by assumption.

`verified_chain_failures`, `decision_accuracy`, `explanation_fidelity`, `behavioral_faithfulness`, `decision_improvement` and `annotator_agreement` are all **null**. Model requests: **0**. Training runs: **0**. New counterfactual interventions: **0**. Paid API spend incurred by C0-A: **0**. Preparation ends here pending real humans. If no repeatable failure is independently established or strong baselines already resolve it, stop proposing new chain-level training and report the negative finding. C0-B has not been authorized or started.
