# Corpus Source Audit

This is the source audit for the complete pilot corpus, prepared before relevance annotation and before any baseline or retrieval output was inspected by the corpus editor. The design-v1 case matrix and research question have not been changed.

## Current state

`data/knowledge_items.jsonl` contains 96 independently written, English educational items. The existing JSON Schema permits English. Domain counts remain exactly 16 / 16 / 8 / 16 / 12 / 8 / 12 / 8. Twenty-two distinct public authority or official device-documentation URLs support the items. Every item has a source URL, a section locator, a matched source anchor, an actual access date of 2026-10-03, applicability, and provenance.

Each item's `status=verified` means that the public source was actually fetched, a supporting passage was located, and an LLM editor reviewed the content and applicability against that source. It does **not** mean human verification, clinician review, clinical validity, or validation against a real wearable device. This is an explicit deviation from the original data dictionary's expectation of human checking. The user's execution request replaces human relevance labels with provisional LLM labels; neither step establishes human clinical approval.

An independent source-only LLM review is run separately by `src/review_corpus.py`. Its input has knowledge text, applicability, and source snapshots, without any cases, case types, strata, designer notes, method outputs, or retrieval results. The first completed review requested twelve corrections. Those corrections were applied before annotation, as listed below. Independent re-audit is pending; corpus freeze is not claimed here.

## Actual checks

- All 96 IDs are present exactly once, in K001-K096 order.
- All eight taxonomy allocations match the existing design.
- All 96 records pass the unchanged Draft 7 knowledge schema with date and URL format checking.
- All 96 primary supporting anchors, and three additional same-source support anchors, occur in their fetched source text. Anchor matching is an access check, not semantic proof.
- All content and titles are nonempty; no exact duplicate title/content pair exists.
- Word-set Jaccard screening checks all 4,560 item pairs with declared stop words. Four pairs reach 0.28; this is a review flag and not a semantic duplicate detector.
- No fabricated source, publication date, step target, HRV threshold, diagnosis, or RHR/HRV conjunction is introduced.
- `source_published_on` is null throughout. A page's displayed review or update date is not treated as its original publication date. Known displayed dates remain in the source manifest as review/update metadata.
- Only `title + content` may be indexed. Applicability, keywords, IDs, source anchors, source snapshots, and reviewer comments must not enter retrieval queries or the index.

`src/build_corpus.py --offline` reconstructs the corpus from frozen source snapshots and the editorial seed, checking source hashes and all item anchors before writing output. `--refresh` fetches sources again; it must not be used once experimental annotation and retrieval have been frozen without creating a new documented corpus revision.

## Independent review repairs

The independent reviewer requested twelve corrections; all were addressed using the same actually fetched authorities. No cases, baseline outputs, retrieval results, or labels were used. IDs, domain allocations, the design-v1 matrix, and the research question remain unchanged. The content revision is `source-grounded-pilot-v2`.

| Item | Repair |
| --- | --- |
| K007 | Added sleep-onset difficulty alongside awakenings and refreshment; removed an overly narrow quality-context gate. |
| K009 | Preserved the source's more-than-eight-hours **per night** condition. |
| K016 | Restricted the failed-habit-change and daily-life-impact advice to the NHS insomnia context. |
| K019 | Corrected the title from worknight to weeknight; calendar labels do not establish employment schedules. |
| K028 | Distinguished the general adult nap-duration recommendation from timing advice conditioned on sleep-onset difficulty. |
| K038 | Removed the unsupported title implying that insomnia necessarily lasts longer than a wearable window. |
| K039 | Included the source's alternative for trips of two to three days and required trip duration. |
| K046 | Included all major muscle groups in the strengthening recommendation; added the corresponding source anchor. |
| K074 | Restricted applicability to the documented emergency-responder context. |
| K084 | Removed the unsupported attribution about lifestyle responses; retained well-being use and non-diagnostic scope, with a separate anchor identifying HRV among vitals. |
| K094 | Narrowed the content to the source's stage-based estimate of minutes asleep; removed the unexposed signal-input attribution. |
| K096 | Added both actually located source passages for accelerometer step detection and arm-swing limitations. |

The extra anchors address short-excerpt limitations in independent review; they do not introduce new claims. `corpus_review_input.json` contains all associated source contexts. Root orchestration must verify the final repaired content independently before annotation.

The next full independent review supported 93 items and requested three additional scope corrections, all applied before annotation: K049 now explicitly limits the talk test to aerobic activity; K052 describes preferences and available times as helpful planning context rather than a universally necessary condition for an activity habit; K074 preserves the source's emergency-responder deployment context. Re-audit of those final repairs remains the orchestration owner's responsibility.

## Near-duplicate review

The flagged pairs are K002/K003, K001/K003, K002/K004, and K057/K059. The first three use different authority-supported age populations and sleep-duration recommendations, not paraphrases for the same population. K057 addresses uninterrupted periods without movement; K059 addresses total time sitting across the day. Both recommendations appear separately in actual NHS guidance. The corpus does not claim these distinctions must produce different relevance labels for any case.

An earlier K057 draft duplicated television-break advice already present in K063. Before annotation it was replaced by the actual NHS adult activity guidance on interrupting long periods without movement. K063 remains a specific television-context item. This was a source and duplicate repair; it did not use any method or retrieval output.

Other overlapping clusters deliberately retain source-supported differences: ordinary activity versus known moderate or vigorous aerobic activity; general pre-bed intense exercise versus the NHS advice specifically for people with insomnia; duration versus awakenings and refreshment; RMSSD definition versus overnight collection requirements. Applicability states the additional context explicitly. An unavailable required condition must not be silently inferred by a judge.

## Supported scope and unsupported distinctions

The sources support regular sleep schedules, age-specific duration guidance, repeated sleep restriction, activity timing records, daily movement, interrupting long periods without movement, personal vital trends, and measurement limitations. They do not establish all intended representation-sensitive distinctions as clinically different knowledge needs.

- No source supports a universal clinical interpretation of a simultaneous resting-heart-rate rise and HRV decline relative to the same changes occurring on different days. Separate trend and interpretation items are retained; no conjunction-specific action item was manufactured.
- A later but stable bedtime is not itself treated as unhealthy. Advice about irregular timing, actual shift work, travel, light, substances, or sleep difficulties preserves its own conditions.
- There is no universal threshold for an excessively long low-movement bout and no invented requirement to move every thirty minutes. Recorded intervals can support review of long uninterrupted movement-free periods; posture, mobility, and context remain unknown unless recorded.
- Steps and unspecified moving minutes are not converted to moderate-intensity guideline attainment.
- An observed activity/sleep temporal relationship is not declared causal. The NHLBI intense-exercise guidance and NHS insomnia guidance have different timing and population conditions and remain separate.
- No source-derived number of recovery days is assigned to a resolved short sleep episode. A return in device observations is not proof of full physiological recovery.
- Missing recordings are not physiological zeros. Device-specific requirements are not presented as universal wearable validity policies.

Consequently, two matched cases may receive equal relevance labels even if their raw patterns differ. This outcome would limit that pair's value for the research question; it must not trigger post-result case or knowledge rewriting.

## Source access and provenance

`data/source_manifest.json` records fetched URLs, resolved URLs, access times, hashes, paths, and unavailable attempts. `data/source_snapshots/` retains HTML plus extracted text for reproducibility. HTML hashes cover original response bytes; text hashes cover UTF-8 extracted text with normalised newline handling. `data/corpus_verification.json` connects each item to its source text hash and audit result. `data/corpus_review_input.json` is the source-only independent-review input.

The original CDC sleep endpoint sometimes returned HTTP 403 to the downloader. An alternate official CDC endpoint was actually fetched successfully; the resolved URL is recorded. The AHA heart-rate page was readable through the web tool but the snapshot download returned HTTP 403, so it is not used for any corpus item. Google's actual official heart-rate definitions and limitations support the retained items. The NHLBI diagnosis page was unavailable and is also unused.

The obsolete NHS sit-less URL redirected to the Benefits of exercise page. The redirected text is not used as evidence for missing sit-less claims. Actual NHS adult guidelines, NHS Benefits of exercise, and MyHealth London NHS pages support the relevant items. The source manifest preserves the attempted URL and resolution so the redirect can be checked.

The MedlinePlus medical encyclopedia's A.D.A.M. Physical activity article was considered during browsing but excluded from the corpus and local snapshots. MedlinePlus government-authored health-topic and fitness-definition pages are used instead. Source snapshots are audit evidence, not indexed knowledge. Item content consists of brief independent paraphrases; original source content is not copied wholesale into corpus records.

## Limitations for interpretation

Many items are conditional education whose conditions are not observed in these wearable cases, including symptoms, caffeine, medications, work schedules, travel, posture, perceived exertion, and activity preferences. This is an honest applicability limitation, not evidence that the relevant condition is absent. Provisional annotation must distinguish unknown context from an established condition.

The corpus contains generic guidance and device interpretation, with substantial source clustering, rather than 96 independent clinical mechanisms. Correlated or related items do not represent independent corroborating evidence. Measurement-quality results should be reported separately from the lifestyle-oriented corpus. English content keeps retriever language fixed but limits claims about Chinese retrieval or cross-language generalisation.

This pilot can examine candidate retrieval from this frozen corpus. It cannot establish medical decision quality, the benefit of real interventions, or the adequacy of the corpus for an individual patient.

## Final active Qwen review

The active execution-qwen-v1 source-only audit reviewed all 96 final items using qwen3.8-max, independently of cases, labels and representations. All 96 were assessed supported after the pre-freeze K066 clarification and explicit fetched-page provenance for K085. The verified Google page includes its HRV/RMSSD section; its URL was not replaced on the basis of an unverified reviewer suspicion.

The complete judgments and corpus fingerprint are in data/independent_corpus_review.json. Cases, corpus, source snapshots, prompts and retrieval settings were then hash-frozen before annotation/retrieval. The earlier aborted Codex judgments are archived and are not active source verification. This remains machine/LLM review, not human clinical certification.
