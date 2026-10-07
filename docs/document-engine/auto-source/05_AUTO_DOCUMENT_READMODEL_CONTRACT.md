---
title: AUTO_SOURCE Document Read Model Contract
status: FROZEN
version: 1
governed_by: WO-DOC-AUTO-SRC-01
date: 2026-10-08
---

# AUTO_SOURCE Document Read Model Contract

## 1. Principle

The AUTO_SOURCE Document Library is a READ MODEL computed from source tables.

It does NOT require:
- INSERT into runtime_document_data
- INSERT into generated_document
- PDF file generation
- Storage upload

The Read Model shows source records as if they were documents.

## 2. Read Model Row Fields

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| document_key | text | computed | auto:v1:{SOURCE_TYPE}:{SOURCE_ID}:{PROJECTION_TYPE}:{DETAIL_OR_DASH} |
| channel | text | constant | AUTO_SOURCE |
| source_type | text | constant per domain | INSPECTION \| TBM |
| source_id | uuid | source PK | safety_inspections.id \| tbm_meetings.id |
| projection_type | text | document_type_registry.doc_type | INSP \| CHK \| EQUIP \| PPE \| TBM |
| projection_detail | text (nullable) | document_type_mapping.doc_detail | FIRE \| ELEC \| CRANE \| ... \| null |
| catalog_doc_id | text (nullable) | resolved if binding = RESOLVED | document_forms.doc_id |
| catalog_binding_status | text | computed | RESOLVED \| AMBIGUOUS \| UNRESOLVED |
| document_title | text | derived from projection_type + detail | display only |
| company_id | uuid | factory → company | display only |
| factory_id | uuid | source record | display filter |
| source_date | date | inspection_date \| work_date | display only |
| source_status | text | normalized status | COMPLETED \| IN_PROGRESS |
| selector_status | text | Projection Selector result | READY \| UNRESOLVED_TYPE \| UNRESOLVED_DETAIL \| AMBIGUOUS |
| render_status | text | computed | READY (if COMPLETED + fetcher exists) \| NOT_READY |
| issue_code | text (nullable) | generated display code | {TYPE}-{사업장}-{YYYYMMDD}[-{DETAIL}] |
| confirmed | boolean | false until explicit user action | false by default |
| archive_id | uuid (nullable) | runtime_document_archive.id | null until confirmed |
| source_updated_at | timestamptz | source record updated_at | for change detection |

## 3. Selector Status → Library Visibility

| selector_status | Visible to user | Notes |
|-----------------|-----------------|-------|
| READY | YES | Document appears in library |
| UNRESOLVED_TYPE | NO | Internal QA only |
| UNRESOLVED_DETAIL | NO | Internal QA only |
| AMBIGUOUS | NO | Internal QA only |

Fail-closed: ambiguous or unresolved projections are not shown.

## 4. On-Demand Render

When user clicks on a READY document:
```
document_key
  → source_type, source_id, projection_type, projection_detail
  → Fetcher(source_id) → raw data
  → Template(projection_type, projection_detail) → HTML / PDF
```

No pre-render. No storage write on list display.

## 5. Physical Storage (NOT required for listing)

```
runtime_document_data    = NOT required for AUTO listing
generated_document       = NOT required for AUTO listing
PDF / Storage            = NOT required for AUTO listing
```

These are created only on explicit user action (preview/download/confirm).

## 6. runtime_document_data Separation Note

`runtime_document_data.source_inspection_id` column exists with:
```
UNIQUE (source_inspection_id, form_schema_id)
```

This column was designed for MANUAL/ASSISTED_MANUAL working state linkage to an inspection.
It is NOT the mechanism for AUTO_SOURCE library listing.
Reactivating this as the AUTO_SOURCE persistence path is explicitly deferred to AUTO-SRC-06.

## 7. Confirm Boundary

Current confirm contract:
```
runtime_document_data.id → runtime_document_archive
```

This path requires a materialized runtime_document_data row, which AUTO_SOURCE does not create by default.

Options (deferred to AUTO-SRC-06):
- A: Lazy materialization on explicit edit/confirm
- B: Source-direct confirmed snapshot path
- C: Common canonical intermediate state

Claude does not select between these options.

## 8. Governance

- Physical implementation = NOT IMPLEMENTED (separate WO)
- DB MUTATION = 0
- This document = design contract only
