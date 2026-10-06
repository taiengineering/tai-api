---
title: Wave 2 Quality Report — EQUIP×15
description: Field, checklist, evidence quality findings for Wave 2 (15 EQUIP docs)
type: evidence
wo: WO-DOC-OBJ02-C1-P0-CANDIDATE-QUALITY-AUDIT-001
status: COLLECTED
---

# Wave 2 Quality Report — EQUIP×15

## Scope

15 EQUIP documents

| doc_id | doc_detail | has_legal_form | fields | checklists | evidence |
|--------|------------|---------------|--------|------------|----------|
| DOC-BLD-002 | FIRE | true | 5 | 5 | 1 (SIGNATURE) |
| DOC-BLD-009 | ELEC | false | 3 | 3 | 1 (DATE) |
| DOC-BLD-011 | ELEV | true | 4 | 4 | 1 (DATE) |
| DOC-BLD-016 | ASBESTOS | true | 3 | 3 | 0 |
| DOC-CHEM-003 | HAZMAT | false | 4 | 4 | 0 |
| DOC-CON-013 | MACHINE | false | 3 | 3 | 0 |
| DOC-CON-014 | SCAFFOLD | false | 3 | 3 | 0 |
| DOC-CON-026 | SCAFFOLD | false | 3 | 3 | 0 |
| DOC-CON-032 | CRANE | false | 3 | 3 | 0 |
| DOC-CON-043 | GUARD | false | 3 | 3 | 0 |
| DOC-FAC-002 | GAS | false | 4 | 4 | 0 |
| DOC-FAC-008 | HAZMAT | true | 4 | 4 | 0 |
| DOC-FAC-013 | BOILER | true | 4 | 4 | 0 |
| DOC-FAC-016 | REFRIG | true | 3 | 3 | 0 |
| DOC-OSH-059 | MACHINE | false | 5 | 5 | 1 (DATE) |
| **Total** | | 6 legal | **54** | **54** | **4** |

## G2 Field Fidelity

All 54 fields: `status=CANDIDATE`, `required_status=CANDIDATE_ONLY`. No exceptions.

Field input_type distribution:
- text: 45
- textarea: 5
- date: 3 (DOC-BLD-009.inspection_datetime, DOC-BLD-011.inspection_date, DOC-OSH-059.inspection_datetime)
- signature: 1 (DOC-BLD-002.inspector_sign)

## G3 Checklist Fidelity

All 54 checklist items: `input_type=PASS_FAIL`, `status=APPROVED_BY_HUMAN`. No exceptions.

## G4 Field↔Checklist Cross-Layer Duplication (CRITICAL FINDING)

Pattern confirmed: 100% duplication across all 54 EQUIP items. Every checklist `raw_text` = corresponding `field_label` (exact match).

### Type Mismatch Instances (EQUIP Wave 2)

| doc_id | field_key | field_input_type | checklist_raw_text | severity |
|--------|-----------|------------------|-------------------|----------|
| DOC-BLD-002 | inspector_sign | signature | 점검자 서명 | CRITICAL |
| DOC-BLD-009 | inspection_datetime | date | 점검일시 | HIGH |
| DOC-BLD-011 | inspection_date | date | 점검일자 | HIGH |
| DOC-OSH-059 | inspection_datetime | date | 점검일시 | HIGH |

All other 50 EQUIP checklist items: text/textarea → PASS_FAIL (structural duplication but no capture type mismatch).

## Evidence Gaps by Legal Form Status

| doc_id | has_legal_form | evidence | gap |
|--------|---------------|----------|-----|
| DOC-BLD-002 | true | SIGNATURE | DATE missing (no timestamp proof) |
| DOC-BLD-011 | true | DATE | SIGNATURE missing (no signing proof) |
| DOC-BLD-016 | true | 0 | BOTH missing |
| DOC-FAC-008 | true | 0 | BOTH missing |
| DOC-FAC-013 | true | 0 | BOTH missing |
| DOC-FAC-016 | true | 0 | BOTH missing |

4 of 6 legal form docs have zero evidence. For documents with `has_legal_form=true`, evidence capture (at minimum a date timestamp) is expected to satisfy legal retention requirements.

## 11 Docs with Zero Evidence

DOC-BLD-016, DOC-CHEM-003, DOC-CON-013, DOC-CON-014, DOC-CON-026, DOC-CON-032, DOC-CON-043, DOC-FAC-002, DOC-FAC-008, DOC-FAC-013, DOC-FAC-016.

These docs have no date or signature evidence registered. The inspection record (asset, datetime, result) would be captured solely via `runtime_data_json` text fields with no separate temporal evidence anchor.

## Fetcher Compatibility (EQUIP)

All 15 EQUIP docs use `doc_type=EQUIP` → `fetcher_key=inspection` → `InspectionFetcher`. The fetcher resolves `safety_inspections` + `equipment_assets`. Template `DOC-EQUIP.html` exists. Compatibility: CONFIRMED for all 15.

## Severity Summary

| Finding | Severity | Affected docs | Affected items |
|---------|----------|---------------|----------------|
| PASS_FAIL on signature field (inspector_sign) | CRITICAL | 1 (DOC-BLD-002) | 1 item |
| PASS_FAIL on date fields (inspection_datetime/date) | HIGH | 3 (DOC-BLD-009, DOC-BLD-011, DOC-OSH-059) | 3 items |
| Legal form docs with 0 evidence | HIGH | 4 (DOC-BLD-016, DOC-FAC-008, DOC-FAC-013, DOC-FAC-016) | — |
| Full field↔checklist duplication | HIGH | 15 | 54 items |
| Non-legal docs with 0 evidence | MEDIUM | 7 | — |
