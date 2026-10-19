# WO-REF01-OBSERVED-FIELDS-CONTROLLED-APPLY-049
Date: 2026-10-08 | GPT independent review of WO-048 | APPROVED LIMITED EXECUTION

## Role / authority
GPT = analyze, design, work order, independent verification. Claude Code = inspection, precise data application, evidence. Owner approval remains separate. PRJ governance; LEG legal SoT. Supabase project vwlahtguyggrhvslabax, public.ref_form_research_items = frozen 189-row research SoT.
Basis: evidence/REF01-SOURCE-SECTION-ERRATA-048.md, evidence/REF01-SOURCE-SECTION-MANIFEST-047.md, three Owner-uploaded source files. HWP SHA256 e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe.

## GPT decisions
REF-C006 HOLD: WO-048 summary text confusingly calls HWP heading '위험성평가표(빈도·강도법)' but evidence gives exact original heading 'KRAS 시스템 위험성평가표 작성 예시'. Related domain does not prove template identity. NO observed_fields update or source_title update. Can preserve provenance mismatch in an evidence receipt only.
REF-C007 APPROVE: HWP-07 original '안전보건 예산 편성항목 예시'; source field entries are COLUMN_HEADER / CATEGORY_LABEL / ROW_LABEL, **not** all editable inputs. Use exact labels and para refs in WO-048, record heading discrepancy.
REF-C008 CONDITIONAL APPROVE: HWP-08 original '안전보건 전문인력 평가 기준 및 평가표 예시'. Separate rating criteria and the evaluation table components in field elements (subsection A/B). Source-title '전문이력' apparent typo: DO NOT UPDATE source_title; keep original correct heading and mismatch in notes. Duty list is reference content, not field inventory.
REF-C009 APPROVE: HWP-09 exact match; record COLUMN_HEADER and ROW_LABEL separately.
REF-C010 HOLD: HWP-10a crush accident image-only; HWP-10b falling accident table; HWP-10c suffocation/electric scenario. DO NOT flatten 10a/b/c into one REF-C010 observed_fields or equate templates, no field write until image source interpreted. No new research IDs.
REF-C011 APPROVE: HWP-11 exact family match, existing ID confirmed. Preserve scoring hierarchy (CATEGORY_LABEL, SUB_CATEGORY, ROW_LABEL, COLUMN_HEADER), numbers as source-example evidence rather than universal legal criteria. No duplicate ID.

## Scope of SQL update
ONLY REF-C007, REF-C008, REF-C009, REF-C011, only if observed_fields = [] at baseline, approved source SHA verified and current title matches expected row. For each, observed_fields JSONB must be precise array of objects {label, label_type, source_section, paragraph_ref, component, verification:'NATIVE_PARAGRAPH_ONLY', requiredness:'UNVERIFIED'}; use exact labels/refs in WO-048. For C008 component A (evaluation criteria) vs B (evaluation table).
Set source_document_checksum to exact HWP SHA; source_document_access = 'OWNER_UPLOADED_HWP_TEXT_PARSED_PARTIAL'; source_observation_note APPEND tagged WO-049 and explicit source heading and fidelity caution; payload merge owner_original_heading, evidence_manifest_ref, field_batch, relation status. Never replace nonempty field list.
Source_url: leave unchanged; specifically for C011 URL NULL must stay NULL, because owner-supplied file original downloadable URL not independently verified.
No modification of source_title, proposed_fields, legal_required_fields, legal_sot_reference, rights, license, review_status, owner_approval_status, publication_status, canonical_candidate_id, relation_group, approval times, schema, RLS, other rows.
Use transaction with concurrency predicates and RETURNING research_id, old status, new labels count. Roll back unless exactly four intended rows changed. Snapshot baseline and read-after-write verified full 189 count, prior 10 observed + new 4 = 14 (if no other concurrent writes); all four exact checksums; no changes to held C006/C010; Owner gates unchanged; no duplicate records.
If one row precondition does not match, STOP and return BLOCKED rather than overwrite. Do not fake success counts.

## Evidence and stop
Store only textual evidence (no uploaded original file bytes), e.g. docs/reference-forms/evidence/REF01-OBSERVED-FIELDS-APPLY-049.md: baseline SQL, exact applied field arrays/paragraphs, mutation receipt, post-check, redactions and unresolved. Commit to existing branch only; do not merge.
Return STOP for GPT independent verify.
No new source discovery, TAI legacy or AUTO comparison, service development, deployment, legal assertions or public dissemination.

## Residual work
C006 identity review; C010 image-based crush accident flowchart visual interpretation by proper viewer (avoid OCR until necessary); HWP table geometry. These are not grounds to expand this WO.
