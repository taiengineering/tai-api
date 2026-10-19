# REF-01 — frozen 189-record independent provenance audit 31
Date: 2026-10-08. User instruction: no new sources/forms; assess already collected records; save checkpoints in DB.

## 1. Provenance title audit (read-only comparison)
Retrieved all 8 original report files 13,14,15,17,18,19,21,22 from frozen Git branch. Reconstructed exact document-title column per original table (18/19 title is column 3, unlike other reports).
Built exact 189-ID expected-title matrix and SQL compared against public.ref_form_research_items in project vwlahtguyggrhvslabax.
SQL result: expected=189, missing=0, title_mismatch=0. Previous practitioner title-mapping issue is repaired in DB. The historical consolidated ledger 24 still contains incorrect names for 18/19; current source is the original report + DB correction.

## 2. Internal candidate relationship audit (NO MERGE)
Recorded twenty tentative document-purpose or method groups, tagging 51 existing study IDs in payload:
- risk assessment method variants, safety training planning versus execution, accidents versus near misses
- contractor prequalification, permits vs confined-space variants, emergency preparation
- forklift planning and inspection
- machine preventive maintenance, repair
- chemical inbound/outbound/count/quarantine and MSDS version management
- facility contractor signoff and laboratory inspection
Relation linkage is an **analyst hypothesis from source title & workflow event**. Each marked merge_decision=NOT_MERGED_UNVERIFIED and stores related_source_ids, leaving 189 rows intact. One facility-diary singleton group is merely a topical bucket, not an overlap. Cross-group relationships not exhaustively discovered; 51 is not number of duplicate forms.
SQL readback: total=189; relation_tagged=51; relation_groups=20.

## 3. Hard blockers
Original source file actual field contents are UNVERIFIED (189/189).
Reuse-rights remain UNVERIFIED (189/189).
Legal scope and mandatory fields remain pending per LEG.
All review statuses IN_PROGRESS (as previously loaded), none fully REVIEWED.
No final unique canonical template count can be claimed from 189 research records. No finished forms.

## 4. Decision
Corpus completeness and exact title alignment: PASS for the 189 rows included in frozen research universe.
Document field-level / rights / LEG legal applicability QA: BLOCKED / incomplete.
Internal link hypotheses: recorded, not approved for merge.
REF-01 remains OPEN. REF-02 remains blocked.
No new source discovery, existing TAI DB comparison, TAI AUTO copying, production app code or deployment.
