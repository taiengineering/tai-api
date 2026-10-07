---
title: AUTO_SOURCE Canonical Document Identity Contract
status: FROZEN
version: 1
governed_by: WO-DOC-AUTO-SRC-01
date: 2026-10-08
---

# AUTO_SOURCE Canonical Document Identity Contract

## 1. Core Principle

Business execution is the document source.
A completed inspection or TBM is a document — it does not need to be stored separately.

## 2. Canonical Identity Tuple

| Field | Definition |
|-------|------------|
| channel | AUTO_SOURCE (fixed) |
| source_type | INSPECTION \| TBM |
| source_id | Immutable PK UUID of the source record |
| projection_type | document_type_registry.doc_type (INSP \| CHK \| EQUIP \| PPE \| TBM) |
| projection_detail | document_type_mapping.doc_detail — nullable, default "-" for null |

## 3. Canonical document_key Format

```
auto:v1:{SOURCE_TYPE}:{SOURCE_ID}:{PROJECTION_TYPE}:{DETAIL_OR_DASH}
```

All components uppercase except source_id (lowercase UUID).

Examples:
```
auto:v1:TBM:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee:TBM:-
auto:v1:INSPECTION:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee:EQUIP:FIRE
auto:v1:INSPECTION:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee:INSP:-
```

## 4. NOT Included in Identity

The following values are NOT part of the canonical identity:

| Excluded | Reason |
|---------|---------|
| company_id | Derivable from factory; changes if factory moves |
| factory_id | Derivable from source record; not identity anchor |
| user_id / inspector_id | Operational metadata |
| inspection_date / work_date | Mutable metadata |
| document_title | Derived display metadata |
| asset_name / asset_code | Operational metadata |
| status | Changes over time |
| PDF filename | Generated artifact |
| runtime_document_id | MANUAL channel concept |
| catalog_doc_id | Post-binding result, not identity anchor |
| issue_code | Display/export code, separate from identity |

## 5. catalog_doc_id Is NOT Identity

`document_forms.doc_id` serves as:
- Catalog metadata reference
- Form / manual-document identifier
- Guide linking candidate
- Official form reference

It is NOT included in the canonical AUTO_SOURCE identity.

In the Read Model, catalog_doc_id appears as a nullable resolved field:

```
catalog_doc_id: nullable
catalog_binding_status: RESOLVED | AMBIGUOUS | UNRESOLVED
```

Deterministic assignment (catalog_binding_status = RESOLVED) requires exactly 1 matching doc_id for the (projection_type, projection_detail) combination.

## 6. issue_code Is NOT Identity

The document issue code:
```
{TYPE}-{사업장}-{YYYYMMDD}[-{DETAIL}]
```
is a display/export identifier. It is generated from identity fields but does not define the identity.

## 7. Source Correction Preserves Identity

If the source record (safety_inspections / tbm_meetings) is corrected:
- The source_id does NOT change
- The document_key does NOT change
- The document content reflects the latest source state on next fetch

Source revision/correction is NOT part of the identity tuple.

## 8. One Source → Multiple Projections (Architecture-Allowed)

A single source_id may produce multiple logical documents if multiple deterministic projections apply. Each (source_id, projection_type, projection_detail) tuple produces a distinct document_key.

Whether this occurs in practice depends on the Projection Selector. Current evidence: no deterministic multi-projection rule exists for the current 24 AUTO_SOURCE documents.

## 9. Identity Collision Rules

| Same | Same | Same | Same | → Same document_key |
| Same source_type | Different source_id | Any | Any | → Different document_key |
| Same source_type | Same source_id | Different projection_type | Any | → Different document_key |
| Same source_type | Same source_id | Same projection_type | Different projection_detail | → Different document_key |

Metadata changes (title, status, date, inspector) never change the document_key.

## 10. Selector Status

The Projection Selector assigns a status to each potential projection:

| Status | Meaning |
|--------|---------|
| READY | Projection deterministically resolved; document can be listed |
| UNRESOLVED_TYPE | projection_type cannot be determined |
| UNRESOLVED_DETAIL | projection_type known but detail not deterministic |
| AMBIGUOUS | Multiple candidates; cannot select without additional rule |

AUTO Document Library shows only READY projections to users.
Other statuses are retained as internal QA evidence.

## 11. Governance

- CODE CHANGE = 0
- DB MUTATION = 0
- Read Model existence = NOT IMPLEMENTED (GAP-04)
- This document = design contract only
