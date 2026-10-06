---
title: Wave 1 Quality Report — CHK×2 + INSP×4 + PPE×1 + TBM×2
description: Field, checklist, evidence quality findings for Wave 1 (9 docs)
type: evidence
wo: WO-DOC-OBJ02-C1-P0-CANDIDATE-QUALITY-AUDIT-001
status: COLLECTED
---

# Wave 1 Quality Report

## Scope

9 documents: CHK×2, INSP×4, PPE×1, TBM×2

| doc_id | doc_type | fields | checklists | evidence |
|--------|----------|--------|------------|----------|
| DOC-OSH-017 | CHK | 5 | 5 | 1 (DATE) |
| DOC-OSH-055 | CHK | 5 | 5 | 1 (DATE) |
| DOC-CON-007 | INSP | 5 | 5 | 1 (DATE) |
| DOC-CON-LAW-014 | INSP | 5 | 5 | 1 (DATE) |
| DOC-OSH-007 | INSP | 5 | 5 | 1 (DATE) |
| DOC-OSH-038 | INSP | 5 | 5 | 1 (DATE) |
| DOC-OSH-046 | PPE | 4 | 4 | 0 |
| DOC-CON-012 | TBM | 4 | 4 | 1 (SIGNATURE) |
| DOC-OSH-056 | TBM | 4 | 4 | 1 (SIGNATURE) |
| **Total** | | **42** | **42** | **8** |

## G2 Field Fidelity

All 42 fields: `status=CANDIDATE`, `required_status=CANDIDATE_ONLY`.
No `required_status=REQUIRED` or `OPTIONAL` found. All are pre-production candidates.

## G3 Checklist Fidelity

All 42 checklist items: `input_type=PASS_FAIL`, `status=APPROVED_BY_HUMAN`.
No input_type variation. All have human approval.

## G4 Field↔Checklist Cross-Layer Duplication (CRITICAL FINDING)

**Pattern confirmed: 100% duplication across all 42 Wave 1 items.**

Every checklist item `raw_text` = corresponding `field_label` (exact string match, positional correspondence).

### CHK/INSP Schema (6 docs — identical field set)

All 6 CHK/INSP docs have the same 5-field schema:

| field_order | field_key | field_label | field_input_type | checklist_raw_text | checklist_input_type | type_mismatch |
|-------------|-----------|-------------|------------------|-------------------|---------------------|---------------|
| 1 | inspection_done | 점검 실시 여부 | text | 점검 실시 여부 | PASS_FAIL | NO |
| 2 | inspection_datetime | 점검일시 | date | 점검일시 | PASS_FAIL | **HIGH** |
| 3 | inspector | 점검자 | text | 점검자 | PASS_FAIL | NO |
| 4 | risk | 위험요인 | text | 위험요인 | PASS_FAIL | NO |
| 5 | action | 조치사항 | textarea | 조치사항 | PASS_FAIL | NO |

CHK-INSP finding: `inspection_datetime` is a `date` field captured as PASS_FAIL — the checklist cannot record the actual datetime value, only a boolean pass/fail.

### PPE Schema (1 doc)

| field_order | field_label | field_input_type | type_mismatch |
|-------------|-------------|------------------|---------------|
| 1 | 보호구 착용 여부 | text | NO |
| 2 | 작업자 | text | NO |
| 3 | 미착용자 | text | NO |
| 4 | 조치사항 | textarea | NO |

No critical type mismatch.

### TBM Schema (2 docs — identical)

| field_order | field_label | field_input_type | type_mismatch |
|-------------|-------------|------------------|---------------|
| 1 | 작업내용 | textarea | NO |
| 2 | 위험요인 공유 | text | NO |
| 3 | 참석자 | text | NO |
| 4 | 서명 | signature | **CRITICAL** |

TBM finding: `서명` is a `signature` field (actual image capture) but checklist item is `PASS_FAIL`. A boolean cannot represent a handwritten signature. This conflicts with the evidence model which correctly records SIGNATURE via `evidence_vault_link`.

## G0 Identity

Wave 1: 9/9 PASS (catalog_id_match, source_id_match, doc_id_match).

## CHK = INSP Field Schema Identity Finding

CHK and INSP are distinct doc_types in both `document_type_registry` and `document_type_mapping`. However, their runtime schemas are **structurally identical** (same 5 field_keys, same labels, same input_types). Per registry note: "INSP와 동일 소스, 렌더 형식만 상이". This is intentional — CHK uses DOC-CHK.html, INSP uses DOC-INSP.html. Schema identity at field layer is by design.

**OBSERVED**: Not a finding requiring remediation. Consistent with documented registry intent.

## Evidence Quality

- CHK/INSP (6 docs): DATE evidence (timestamp_auto) present. Evidence label = 점검일시. This correctly captures the inspection datetime separately from the PASS_FAIL checklist item — an evidence layer workaround for the type mismatch.
- PPE (1 doc): 0 evidence. No date or signature capture. Date of PPE inspection cannot be recorded.
- TBM (2 docs): SIGNATURE evidence present. Correctly routes signature capture through evidence vault rather than boolean checklist.

## Severity Summary

| Finding | Severity | Affected docs | Affected items |
|---------|----------|---------------|----------------|
| PASS_FAIL date field (inspection_datetime) | HIGH | 6 (CHK×2+INSP×4) | 6 items |
| PASS_FAIL signature field (서명) | CRITICAL | 2 (TBM×2) | 2 items |
| PPE no evidence capture | MEDIUM | 1 | 0 evidence rows |
| Full field↔checklist duplication | HIGH | 9 | 42 items |
