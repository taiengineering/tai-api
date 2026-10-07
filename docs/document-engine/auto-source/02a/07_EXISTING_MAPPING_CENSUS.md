---
title: Existing Mapping Table Census
status: FROZEN
version: 3
governed_by: WO-DOC-AUTO-SRC-02A
date: 2026-10-08
corr: CORR-002 — canonicalizer + registry + historical SQL sections added; equipment_type_inspection_map production status recorded
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
| Relevant to projection_type | PARTIAL — provides numeric code → Korean name mapping; code → EQUIP doc_detail mapping NOT FOUND (GAP-02C) |

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

Note: 2,935 equipment_assets rows have numeric type_code values joinable to system_codes. Named uppercase codes (CRANE/PRESS/PRESSURE_VESSEL/CONVEYOR) and lowercase/free-text legacy or alternate-origin codes are NOT in system_codes.

### 2e. Other Equipment-Related Structures (inventory — not searched as projection selectors)

| Table | Note |
|-------|------|
| equipment_model_master | Equipment model registry; not queried as projection selector |
| master_legal_inspection_target | Legal inspection target master; not confirmed as projection selector |
| inspection_master | Inspection template master; not confirmed as projection selector |
| site_equipment_sets | Site-level equipment sets; not confirmed as projection selector; linked to inspection_sets.equipment_set_id = 0/396 |

These tables were identified during search scope but not confirmed to contain equipment_type → doc_detail mapping. Querying them for this mapping is reserved for GPT판정 scope.

### 2f. Equipment Uppercase Alias Canonicalizer (Code Contract — CORR-002)

| Attribute | Value |
|-----------|-------|
| File | services/equipment_source/canonicalizer.py |
| Status | ACTIVE CODE CONTRACT |
| Contract | normalize_equipment_type_code() |
| Dictionary | `_ALIAS_TO_NUMERIC` |

Explicit alias mappings:
```
CRANE            → 021  (크레인)
CONVEYOR         → 024  (컨베이어)
PRESS            → 023  (프레스)
PRESSURE_VESSEL  → 038  (압력용기)
```

Pass-through behavior:
```
None                 → None (no-op)
Valid numeric 001-040 → returned as-is
Unknown / lowercase  → returned as-is (downstream authority validation rejects)
```

Relevant to projection_type: NO (canonical equipment code → AUTO doc_detail mapping is a separate gap — GAP-02C)

### 2g. Equipment Source Validation Authority (Code Contract — CORR-002)

| Attribute | Value |
|-----------|-------|
| File | services/equipment_source/store.py |
| Function | validate_equipment_source_row() |
| Status | ACTIVE CODE CONTRACT |

`EQUIPMENT_AUTHORITY_CODES` accepts:
```
numeric 001–040 (zero-padded)  = valid
CRANE, CONVEYOR, PRESS, PRESSURE_VESSEL = valid (aliases, normalized to numeric before storage)
unknown / lowercase / free-text = EquipmentSourceValidationError → 422 HTTP
```

Relevant to projection_type: NO (validates equipment_type_code; does not determine doc_detail)

### 2h. Equipment Source Registry (Code Contract — CORR-002)

| Attribute | Value |
|-----------|-------|
| File | services/equipment_source/registry.py |
| Object | EQUIPMENT_CODE_MAP |
| Status | ACTIVE CODE CONTRACT |

Registered code → canonical boolean fact mappings:
```
010 → has_emergency_gen  (비상발전기)
014 → has_boiler         (보일러)
023 → has_press          (프레스)
024 → has_conveyor       (컨베이어)
038 → has_pressure_vessel (압력용기)
```

Note from registry (code_condition_resolver discrepancy):
```
"010" code_condition_resolver uses "has_generator"; canonical LEG fact is "has_emergency_gen"
"038" string "PRESSURE_VESSEL" → has_pressure_vessel in resolver; numeric "038" authority = equipment_type_inspection_map only
```

Relevant to projection_type: NO — maps code → canonical boolean fact for LEG diagnosis input; does NOT map code → AUTO EQUIP doc_detail

AUTHORITY_BLOCKED codes (not in numeric system):
```
has_construction_machine  — 건설기계: no numeric code
has_high_speed_rotor      — 고속회전체: no numeric code
```

### 2i. Historical Equipment Type Inspection Map SQL (Design Artifact — CORR-002)

| Attribute | Value |
|-----------|-------|
| File 1 | docs/sql/20260331_equipment_type_inspection_map.sql |
| File 2 | docs/sql/20260401_equipment_type_inspection_map_all_exact.sql |
| Intent | Create equipment_type_inspection_map table: type_code → inspection_master.equipment_std |
| Production status | Table does NOT exist in production (public schema) |

The SQL artifact creates `equipment_type_inspection_map` with mappings of the form:
```
011 → 'pump'
012 → 'compressor'
014 → 'boiler'
021 → 'crane'
023 → 'press'
024 → 'conveyor'
025 → 'elevator'
038 → 'pressure_vessel'
040 → NULL (기타 — 표준 미정)
...
```

This is NOT a doc_detail mapping — it maps type_code → inspection_master.equipment_std (an intermediate inspection standard string). The table was never applied to production.

Relevant to projection_type: NO (maps type_code → inspection_master.equipment_std, not → AUTO EQUIP doc_detail)

### 2j. company_form_mapping

| Attribute | Value |
|-----------|-------|
| Table | company_form_mapping |
| Columns | (not queried) |
| Relevant | NO — company-scoped form mapping, not inspection→projection |

### 2k. form_mapping_candidate

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
  = Does NOT provide code → EQUIP doc_detail mapping (GAP-02C)

canonicalizer (services/equipment_source/canonicalizer.py)
  = ACTIVE CODE CONTRACT
  = CRANE→021 / CONVEYOR→024 / PRESS→023 / PRESSURE_VESSEL→038 (EXPLICIT_LEGACY_ALIAS)
  = lowercase/free-text → pass-through → authority rejected (LEGACY_OR_ALTERNATE_ORIGIN_UNRESOLVED)
  = NOT a doc_detail mapping

equipment_source registry (services/equipment_source/registry.py)
  = ACTIVE CODE CONTRACT (5 codes → boolean facts)
  = 010→has_emergency_gen / 014→has_boiler / 023→has_press / 024→has_conveyor / 038→has_pressure_vessel
  = Maps code → LEG diagnosis boolean fact; NOT → AUTO EQUIP doc_detail

historical equipment_type_inspection_map SQL
  = Design artifact (docs/sql/20260331_..., 20260401_...)
  = Maps type_code → inspection_master.equipment_std (NOT doc_detail)
  = Production table does NOT exist

MISSING (GAP-02C)
  = canonical equipment code → AUTO EQUIP doc_detail
  = NO EXISTING MAPPING
```
