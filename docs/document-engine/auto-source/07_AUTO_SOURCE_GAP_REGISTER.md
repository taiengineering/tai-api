---
title: AUTO_SOURCE Gap Register
status: FROZEN
version: 1
governed_by: WO-DOC-AUTO-SRC-01
date: 2026-10-08
---

# AUTO_SOURCE Gap Register

## GAP-01: Inspection → projection_type Canonical Selector Missing

| Attribute | Value |
|-----------|-------|
| Status | OPEN |
| Source field | inspection_sets.inspection_category |
| Production evidence | NULL = 312/396 (78%); inspection_category_code = ALL NULL |
| Impact | Cannot deterministically assign INSP/CHK/EQUIP/PPE to an inspection without additional selector |
| Blocking | AUTO-SRC-02 (Inspection Document Discovery) |
| Resolution path | GPT판정 — define deterministic mapping from inspection_category → projection_type/detail; handle NULL majority |

---

## GAP-02: EQUIP equipment_type_code → doc_detail Canonical Resolver Missing

| Attribute | Value |
|-----------|-------|
| Status | OPEN |
| Source field | equipment_assets.equipment_type_code |
| Production evidence | Dual schema: numeric codes (001-040, 4,000+ rows) + named codes (CRANE/PRESS/CONVEYOR/PRESSURE_VESSEL, ~1,200 rows); no mapping table to EQUIP doc_detail exists |
| Impact | Cannot map equipment asset to EQUIP detail (FIRE/ELEC/CRANE/GAS/etc.) without canonical resolver table |
| Blocking | AUTO-SRC-02 EQUIP sub-path |
| Resolution path | Separate deterministic mapping WO — numeric code → doc_detail + named code → doc_detail |

---

## GAP-03: Catalog doc_id Duplicates / Ambiguity

| Attribute | Value |
|-----------|-------|
| Status | OPEN |
| Scope | 14/24 doc_ids in AUTO catalog are AMBIGUOUS |
| Details | INSP=4(same null detail), CHK=2(same null detail), TBM=2(null detail, construction vs general), EQUIP HAZMAT=2, MACHINE=2, SCAFFOLD=2 |
| Impact | Cannot assign a single catalog_doc_id to many AUTO_SOURCE projections |
| Blocking | catalog_binding_status = AMBIGUOUS for these cases |
| Resolution path | GPT판정 — define tie-breaking rule per ambiguous group (e.g. construction_site_id for TBM, sector/사업장 for INSP/CHK) |

---

## GAP-04: AUTO_SOURCE Document Library Read Model Missing

| Attribute | Value |
|-----------|-------|
| Status | OPEN |
| Evidence | No view, RPC, or table implementing AUTO document listing from source records |
| Impact | Users cannot see auto documents in document library |
| Blocking | AUTO-SRC-04 (Unified Document Library Integration) |
| Resolution path | Implement Read Model (DB view or RPC) computing document_key + projection from source records — AUTO-SRC-02/03 first |

---

## GAP-05: AUTO_SOURCE Direct Confirm Path Missing

| Attribute | Value |
|-----------|-------|
| Status | OPEN |
| Evidence | Current confirm path: runtime_document_data → runtime_document_archive; requires materialized working-state row |
| Impact | AUTO_SOURCE documents cannot be confirmed without materialization or path redesign |
| Blocking | AUTO-SRC-06 (Confirm → Immutable Snapshot Integration) |
| Resolution path | GPT판정 on Option A/B/C (see 06_CONFIRM_BOUNDARY_ANALYSIS.md) |

---

## GAP-06: Inspection Effective Bulk Read Path Unclear

| Attribute | Value |
|-----------|-------|
| Status | PARTIAL |
| Evidence | fn_resolve_inspection_record(inspection_id) = single-row resolver (N+1); fn_list_effective_inspection_records_by_inspector(inspector_id) = inspector-scoped bulk path exists |
| Impact | Factory-wide or company-wide AUTO document library listing cannot use N+1 resolution efficiently |
| Blocking | AUTO-SRC-02 bulk listing performance |
| Resolution path | Verify fn_list_effective_inspection_records_by_inspector scope/signature; determine if factory-wide bulk path is needed or can be added |

---

## GAP-07: Inspection Source Change Token Contract Undefined

| Attribute | Value |
|-----------|-------|
| Status | OPEN |
| Source field | safety_inspections — NO updated_at column; fn_resolve_inspection_record returns revision field |
| Production evidence | safety_inspections schema confirmed: no updated_at; tbm_meetings has updated_at; revision semantics for inspection not contractually defined for change detection |
| Impact | Read Model source_version_token and source_changed_at semantics cannot be implemented uniformly across INSPECTION and TBM source domains |
| Blocking | Read Model source change detection (05_AUTO_DOCUMENT_READMODEL_CONTRACT.md Section 2 — source_version_token / source_changed_at) |
| Resolution path | Define per-domain contract: INSPECTION = resolver revision as version token (REVIEW_REQUIRED — confirm monotonic); TBM = updated_at as source_changed_at. Requires DB schema verification. |

---

## Summary

| GAP | Status | Blocks |
|-----|--------|--------|
| GAP-01 | OPEN | AUTO-SRC-02 |
| GAP-02 | OPEN | AUTO-SRC-02 EQUIP |
| GAP-03 | OPEN | catalog_binding AMBIGUOUS (14/24) |
| GAP-04 | OPEN | AUTO-SRC-04 |
| GAP-05 | OPEN | AUTO-SRC-06 |
| GAP-06 | PARTIAL | AUTO-SRC-02 performance |
| GAP-07 | OPEN | Read Model source_version_token / source_changed_at |
