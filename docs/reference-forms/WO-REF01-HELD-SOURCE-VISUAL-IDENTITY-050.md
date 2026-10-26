# WO-REF01-HELD-SOURCE-VISUAL-IDENTITY-050
Date: 2026-10-08 | READY FOR CLAUDE CODE EXECUTION | NOT YET EXECUTED

## Authority and baseline
GPT = analysis/design/work order/independent verification; Claude Code = technical investigation, extraction, evidence collection; Owner = approvals.
PRJ development governance. LEG sole legal SoT. Existing Supabase reference-forms research SoT public.ref_form_research_items (project vwlahtguyggrhvslabax) must remain unchanged.
Baseline: 189 research rows, 14 with nonempty observed_fields. WO-049 CLOSED FINAL; REF-C006 and REF-C010 on HOLD; REF-C008 source_title typo '전문이력' vs original '전문인력' deferred.
Current branch: docs/tai-reference-forms-charter-obj-20261008, repository taiengineering/tai-api.
Primary documents: OBJ-REF-01-THREE-LEVEL-IDENTITY-CONTRACT-046.md, evidence/REF01-SOURCE-SECTION-MANIFEST-047.md, evidence/REF01-SOURCE-SECTION-ERRATA-048.md, evidence/REF01-OBSERVED-FIELDS-APPLY-049.md.

## Strict prohibitions
No new form/source discovery; no new research rows or IDs; no DB writes or schema changes; no silent source_title correction; no canonical merge; no service implementation/deploy/merge; no public source file redistribution; no legacy TAI DB or AUTO form comparison; no claim of statutory requiredness or reuse license.
Source bytes must be Owner-provided files locally available to Claude Code; never assume ChatGPT attachments reside in Claude local environment. Verify exact SHA256 and STOP on mismatch.
2022 MOEL HWP SHA256 e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe
MOEL guide PDF SHA256 a73ce4c67dfcb4a1b27f647ad346496f1bc7421666653da516c9ca92a46c60ff
2023 risk assessment HWPX SHA256 c624ea2e72c4e79b8daa011375d2105f3f917e069b47dfd95c9850b193d21d46

## S0 — Read-only preflight
Read governance and evidence 046–049. Verify Git HEAD/branch, hashes of sources actually used, SQL count of SoT 189 and observed_fields nonempty 14; verify both HOLD rows observed_fields=[] and no checksum. Record parser/viewer versions and any limitations. Do not infer sources from filenames.

## S1 — REF-C010 visual extraction
HWP-10a HWP paragraph ordinal 1462–1463, title '협착사고 발생 시 대응 시나리오(처리 흐름도)', diagram embedded BinData/BIN0001.tif; PDF guide physical p106 cross-check. Examine image visually with actual rendering/viewer; extract literally visible diagram boxes/arrows/actors/events and ordered transitions. Use OCR only if visually unreadable and document OCR provenance, don't hallucinate labels. Track every field as one of DIAGRAM_NODE / DECISION / ACTION / ACTOR / ARROW / FORM_INPUT_FIELD / UNRESOLVED. Distinguish process text from user-fillable form fields; image workflow diagram is NOT automatically a blank form.
HWP-10b fall scenario (para 1464–1541, PDF p107), HWP-10c asphyxiation/electrical scenario (para 1542–1596, PDF p108): report each independently with row/table headings and purpose, without merging them into C010 observed_fields. Define relationship between C010 research title and each source as EXACT/VARIANT/RELATED/UNRESOLVED with factual reasons, but reserve canonical identity for GPT.
Document whether TIF / PDF rendering was readable and cross-validate actual diagram, not just a heading.

## S2 — REF-C006 source identity comparison
HWP-06 'KRAS 시스템 위험성평가표 작성 예시', para 1026–1232, PDF physical p93. Compare its actual column hierarchy including 가능성(빈도), 중대성(강도), 위험성(빈도×강도), process/approval fields to SoT research title '위험성평가표(빈도강도법)' and any existing original source evidence of same research row only. Explain difference between *same risk assessment method* and *identical original form*, with traceable field-by-field comparison, document/edition provenance. Do not use TAI legacy/AUTO.
Output proposed relationship (METHOD_COMPATIBLE / IDENTICAL_VERIFIED / UNDETERMINED), with evidence and why identity is or is not conclusively established. Do not overwrite source_title or observed_fields.

## S3 — REF-C008 typo recommendation (evidence only)
Compare exactly existing SoT source_title '안전보건 전문이력 평가 기준 및 평가표' against original HWP-08/PDF original '안전보건 전문인력 평가 기준 및 평가표 예시'. Propose non-destructive canonical_title/source_observation_note correction path (preserve raw recorded title); do not write DB.

## S4 — Git evidence receipt and STOP
Create docs/reference-forms/evidence/REF01-HELD-VISUAL-IDENTITY-MANIFEST-050.md containing:
- source hashes, PDF physical page vs printed page locator;
- C010 actual visual flow chart node/arrow text with exact reference and an explicit classification of diagram vs editable form;
- 10b/10c independent variants;
- C006 evidence comparison and limited conclusion;
- C008 typo recommendation;
- read-only database preflight/postflight results (189 rows, observed 14, holds empty);
- residual unknowns / parser limitations; no original copyrighted file bytes or full image committed.
Return branch+commit, READY_FOR_GPT_INDEPENDENT_REVIEW / PARTIAL / BLOCKED. No further batch, no migration or deploy.
