---
title: OBJ02-B1 Read-Model Contract (CORR-01/02/04 applied)
description: Resolver and workspace readmodel contracts, post correction
type: evidence
wo: WO-DOC-OBJ02-B1-CORRECTION-002
status: VERIFIED_33_PASS
---

# OBJ02-B1 Read-Model Contract

## 1. resolve_catalog_runtime_schema()

File: `services/document_engine/catalog_resolver.py`

### Signature (CORR-04: parameter renamed)

```python
def resolve_catalog_runtime_schema(catalog_document_id: str) -> dict
```

- `catalog_document_id`: `document_forms.id` (UUID string).
  Named `catalog_document_id` to distinguish from `document_forms.doc_id`
  (business key, e.g. `DOC-CHK-001`).

### Return Shape

```python
{
  "availability": "READY_FOR_EDIT" | "PREPARING" | "NO_SCHEMA",
  "schema": <runtime_form_schema row> | None,
  "fields": [<runtime_field rows>],         # populated only when READY_FOR_EDIT
  "checklists": [<runtime_checklist_item rows>],
  "evidence_fields": [<runtime_evidence_field rows>],
}
```

### Availability Logic

| Condition | availability | schema |
|-----------|--------------|--------|
| 1 APPROVED_FOR_RUNTIME_USE schema bound | READY_FOR_EDIT | schema row |
| 0 APPROVED, ≥1 CANDIDATE schema bound | PREPARING | None |
| 0 schemas bound | NO_SCHEMA | None |
| >1 APPROVED (integrity violation) | RuntimeError raised | — |

### Precondition

Raises `ValueError` if `catalog_document_id` is not found in `document_forms`.

---

## 2. list_document_workspace()

File: `services/document_engine/workspace_readmodel.py`

### Signature (CORR-01/02)

```python
def list_document_workspace(
    page: int = 1,
    page_size: int = 50,
    availability: str = None,
    sector: str = None,       # replaces document_family (CORR-01)
    category: str = None,
) -> dict
```

### Return Shape

```python
{
  "items": [
    {
      # actual document_forms columns (CORR-01):
      # id, doc_id, doc_name, sector, category, is_active, priority
      "availability":    "READY_FOR_EDIT" | "PREPARING" | "NO_SCHEMA",
      "schema_id":       UUID | None,
      "schema_status":   "APPROVED_FOR_RUNTIME_USE" | None,
      "candidate_count": int,
    },
    ...
  ],
  "total":     int,    # filtered total (CORR-02): after availability + sector + category filters
  "page":      int,
  "page_size": int,
}
```

### Columns Used (CORR-01)

Production `document_forms` columns confirmed from OBJ02-A evidence:
`id, doc_id, doc_name, sector, category, law_ref, obligation, tai_grade, tai_difficulty, priority, has_legal_form, tai_auto, tai_method, doc_format, doc_owner, is_external_writer, is_active`

Workspace SELECT uses: `id, doc_id, doc_name, sector, category, is_active, priority`

**Removed**: `document_family` (does NOT exist in production `document_forms`).

### Pagination Order (CORR-02)

```
sector/category filter (DB)
     ↓
schema batch resolve (IN query)
     ↓
availability computed per row
     ↓
availability filter (in-memory)
     ↓
filtered total = len(all_items)
     ↓
pagination (Python slice)
```

This ensures that `total` reflects the post-filter count, and pages are consistent.

### Constraints

- `page_size` capped at 200
- Sorted by `sector`, then `doc_name`
- Batch schema lookup: one `IN(catalog_ids)` query per request — not N+1

---

## 3. Test Results (33/33)

File: `tests/test_doc_obj02b1_resolver.py`

| Test | Scenario | Result |
|------|----------|--------|
| C1 | `document_family` not in workspace items (CORR-01) | PASS |
| C2 | Catalog fixture has no `document_family` (CORR-01) | PASS |
| R1 | APPROVED doc → READY_FOR_EDIT + schema populated | PASS |
| R2 | Fields returned for approved schema | PASS |
| R3 | CANDIDATE doc → PREPARING, schema=None | PASS |
| R4 | No-schema doc → NO_SCHEMA | PASS |
| R5 | Missing catalog_id → ValueError | PASS |
| R6 | All 5 keys present in result | PASS |
| W1 | Workspace returns catalog rows | PASS |
| W2 | availability field present on all items | PASS |
| W3 | schema_id populated for READY_FOR_EDIT | PASS |
| W4 | schema_id=None, candidate_count≥1 for PREPARING | PASS |
| W5 | schema_id=None, candidate_count=0 for NO_SCHEMA | PASS |
| W6 | availability filter: only matching items | PASS |
| W7 | page/page_size echoed in result | PASS |
| W8 | page_size capped at 200 | PASS |
| W9 | Filter-before-pagination: total=4 READY across 2 pages (CORR-02) | PASS |
| W10 | Filtered total sum = unfiltered total (CORR-02) | PASS |
