# REF-01 Owner HWP native extraction, batch 2 / checkpoint 043

Date: 2026-10-08
Owner supplied existing HWP5 form bundle. SHA256 e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe. No new sources found or added.
This check used decompressed HWP BodyText/Section0 paragraph text extracted from original uploaded HWP5. Exact table geometry, merged cells, page positions, and legally requiredness were NOT established.

## Existing IDs and original internal sections observed
- REF-C004: '유해·위험물질 목록 작성 서식 예시': chemical/CAS, formula, explosion limits, exposure threshold, toxicity, flash/ignition points, vapour pressure, corrosivity, unusual reactions, daily usage, stock and notes.
- REF-C005: '작업별 위험관리 대장 활용 서식 예시': work location, activity, risk code, machinery ID, chemical name/CAS, likely injury, contractor, risk classification, notes. **Source heading differs** from research listing '작업별 위험과관리 대장'; retained old source_title verbatim and marked original heading explicitly.
- REF-C014: '재해 감소대책 수립 및 실행 계획서 작성 서식': risk identification, existing risk, controls, post-control risk, responsible person, action request/completion date, closure verification.
- REF-C015: '아차 사고 보고서 양식 예시': task, risk grade A/B/C, description, cause, corrective prevention, photographic/sketch evidence.
- REF-C016: '연간 교육계획 수립 서식': author/reviewer/approver, education category/course, schedule, population, teaching format and remarks.

## DB write / validation
Supabase project vwlahtguyggrhvslabax, table public.ref_form_research_items; five conditional updates (observed_fields previously empty), each with source section + HWP observed paragraph label + requiredness UNVERIFIED. Original proposed_fields untouched; source checksum saved and source_document_access = OWNER_UPLOADED_HWP_TEXT_PARSED_PARTIAL. No statutory mandatory field asserted; no licensing claim.
DB readback: 189 total, 10 with observed_fields nonempty cumulative (prior batch 5 plus this batch 5), OWNER-HWP-02 = 5, legally required verified fields = 0.

## Remaining
REF-C006–011 currently not verified by original form headings; source HWP contains a KRAS risk assessment example and scenario / contractor assessment content but exact semantic mapping and table segmentation require more examination. HWPX 2023 eight template titles are an independent original/version and must be separately cross-mapped to existing research titles. Original template bytes not committed to Git or published.
REF-01 remains OPEN, implementation and publication BLOCKED.
