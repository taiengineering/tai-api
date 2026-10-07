---
title: Existing Mapping Table Census
status: FROZEN
version: 2
governed_by: WO-DOC-AUTO-SRC-02A
date: 2026-10-08
corr: CORR-001 — document_type_mapping count 29→30; system_codes section added; equipment structure inventory added
---

# Existing Mapping Table Census

## 1. Search Scope

Searched for tables with semantics of:
- equipment_type → document_detail
- inspection_type → document_type
- inspection_set → document_projection
- legal_obligation → document_projection

Tables searched in `taieng` production DB (public schema).

---

## 2. Tables Found

### 2a. obligation_form_mapping

| Attribute | Value |
|-----------|-------|
| Table | obligation_form_mapping |
| Columns | id, obligation_code, obligation_name, form_code, form_name, auto_generate, notes |
| Row count | 11 |
| Key | obligation_code (e.g., ELEC_MGR_APPOINT, FIRE_MGR_REPORT, OSH_MGR_REPORT) |
| Value | form_code (e.g., ELEC-FORM-001, FIRE-FORM-001, OSHACT-FORM-002) |
| Semantics | Maps appointment/report obligation codes to administrative form codes |
| Consumer | NOT confirmed — no active code reads this table |
| Writer | static seed data (created 2026-03-28) |
| Relevant to projection_type | NO — obligation_codes are appointment/reporting, not INSP/CHK/EQUIP/PPE; form_codes are ELEC-FORM/FIRE-FORM style, not doc_type projection codes |

Sample rows:
```
ELEC_MGR_APPOINT    → ELEC-FORM-001
FIRE_MGR_REPORT     → FIRE-FORM-001
OSH_MGR_REPORT      → OSHACT-FORM-002
OSH_ACCIDENT_REPORT → OSHACT-FORM-030
LPG_MGR_APPOINT     → GAS-FORM-001
```

### 2b. document_type_registry

| Attribute | Value |
|-----------|-------|
| Table | document_type_registry |
| Columns | doc_type, type_label, template_file, fetcher_key, evidence_source, fetcher_status, note |
| Row count | 8 (APPT, CHK, CONLOG, EDU, EQUIP, INSP, PPE, TBM) |
| Key | doc_type |
| Value | fetcher_key, template_file |
| Semantics | Registry of document projection types with fetcher bindings |
| Consumer | Document engine (renders document from source) |
| Writer | static seed data (created 2026-08-22) |
| Relevant to projection_type | PARTIAL — defines doc_types but does NOT map from source records to doc_type |

### 2c. document_type_mapping

| Attribute | Value |
|-----------|-------|
| Table | document_type_mapping |
| Columns | id, doc_id, doc_type, doc_detail, source_note |
| Row count | 30 |
| Key | doc_id (catalog document ID) |
| Value | doc_type, doc_detail |
| Semantics | Maps catalog doc_id → doc_type + doc_detail |
| Consumer | AUTO_SOURCE catalog binding (ARCH-REC-02 / AUTO-SRC-01) |
| Writer | static seed data |
| Relevant to projection_type | NO — maps doc_id to projection, not source_record to projection |

### 2d. system_codes (equipment_type category)

| Attribute | Value |
|-----------|-------|
| Table | system_codes |
| Filter | category = 'equipment_type' |
| Columns | code, category, name_ko, name_en (and others) |
| Row count | 40 |
| Key | code (numeric string: '001'–'040') |
| Value | name_ko (Korean canonical name) |
| Semantics | Canonical master list of equipment type codes with Korean names |
| Consumer | equipment_assets.equipment_type_code references this master |
| Writer | static seed / admin data |
| Relevant to projection_type | PARTIAL — provides numeric code → Korean name mapping; code → EQUIP doc_detail mapping NOT FOUND (GAP-02B) |

Sample rows:
```
001 = 변압기
008 = 전동기
011 = 펌프
013 = 열교환기
014 = 보일러
021 = 크레인
024 = 컨베이어
025 = 승강기
031 = 스프링클러
032 = 자동화재탐지
036 = 집진기
038 = 압력용기
040 = 기타
```

Note: 2,935 equipment_assets rows have numeric type_code values joinable to system_codes. Named uppercase codes (CRANE/PRESS/PRESSURE_VESSEL/CONVEYOR) and lowercase user-entered codes are NOT in system_codes.

### 2e. Other Equipment-Related Structures (inventory — not searched as projection selectors)

| Table | Note |
|-------|------|
| equipment_model_master | Equipment model registry; not queried as projection selector |
| master_legal_inspection_target | Legal inspection target master; not confirmed as projection selector |
| inspection_master | Inspection template master; not confirmed as projection selector |
| site_equipment_sets | Site-level equipment sets; not confirmed as projection selector; linked to inspection_sets.equipment_set_id = 0/396 |

These tables were identified during search scope but not confirmed to contain equipment_type → doc_detail mapping. Querying them for this mapping is reserved for GPT판정 scope.

### 2f. company_form_mapping

| Attribute | Value |
|-----------|-------|
| Table | company_form_mapping |
| Columns | (not queried) |
| Relevant | NO — company-scoped form mapping, not inspection→projection |

### 2g. form_mapping_candidate

| Attribute | Value |
|-----------|-------|
| Table | form_mapping_candidate |
| Columns | (not queried) |
| Relevant | NO — candidate table (not canonical) |

---

## 3. Conclusion

```
inspection → projection_type mapping table = NO EXISTING CANONICAL MAPPING
equipment_type → doc_detail mapping table  = NO EXISTING CANONICAL MAPPING

obligation_form_mapping
  = EXISTS but maps obligation_code → administrative form_code
  = NOT a projection_type selector
  = NOT connected to INSP/CHK/EQUIP/PPE

document_type_registry
  = EXISTS but defines doc_types (not a source→projection selector)

document_type_mapping
  = EXISTS but maps doc_id → projection (not source_record → projection)
  = 30 rows (CORR-001: previously stated 29)

system_codes(category=equipment_type)
  = EXISTS with 40 rows (CORR-001: previously stated MASTER_NOT_FOUND)
  = Provides numeric code → Korean name mapping
  = Does NOT provide code → EQUIP doc_detail mapping (GAP-02B)
```
