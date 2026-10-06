---
title: OBJ02-B1 Read-Model Contract
description: Resolver and workspace readmodel contracts for catalog-runtime binding
type: evidence
wo: WO-DOC-OBJ02-B1-CATALOG-SCHEMA-BINDING-001
status: VERIFIED_29_PASS
---

# OBJ02-B1 Read-Model Contract

## 1. resolve_catalog_runtime_schema()

File: `services/document_engine/catalog_resolver.py`

### Signature

```python
def resolve_catalog_runtime_schema(doc_id: str) -> dict
```

- `doc_id`: `document_forms.id` (UUID string)

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

Raises `ValueError` if `doc_id` is not found in `document_forms`.

### Lookup Key

Uses `catalog_document_id` column (added by this migration).
Does NOT use source_trace for lookup (source_trace = provenance/audit only).

---

## 2. list_document_workspace()

File: `services/document_engine/workspace_readmodel.py`

### Signature

```python
def list_document_workspace(
    page: int = 1,
    page_size: int = 50,
    availability: str = None,       # optional filter
    document_family: str = None,    # optional filter
) -> dict
```

### Return Shape

```python
{
  "items": [
    {
      # all document_forms columns (id, doc_id, doc_name, document_family, ...)
      "availability":  "READY_FOR_EDIT" | "PREPARING" | "NO_SCHEMA",
      "schema_id":     UUID | None,
      "schema_status": "APPROVED_FOR_RUNTIME_USE" | None,
      "candidate_count": int,
    },
    ...
  ],
  "total":     int,
  "page":      int,
  "page_size": int,
}
```

### Constraints

- `page_size` capped at 200
- Sorted by `document_family`, then `doc_name`
- Batch schema lookup via `IN(catalog_ids)` — one query per page, not N+1

### Availability Assignment

| Condition | availability |
|-----------|--------------|
| approved_map has entry for catalog_id | READY_FOR_EDIT |
| candidate_count > 0, no approved | PREPARING |
| candidate_count = 0, no approved | NO_SCHEMA |

---

## 3. Test Results

File: `tests/test_doc_obj02b1_resolver.py`

| Test | Scenario | Result |
|------|----------|--------|
| R1 | APPROVED doc → READY_FOR_EDIT + schema populated | PASS |
| R2 | Fields returned for approved schema | PASS |
| R3 | CANDIDATE doc → PREPARING, schema=None | PASS |
| R4 | No-schema doc → NO_SCHEMA | PASS |
| R5 | Missing catalog_id → ValueError | PASS |
| R6 | All 5 keys present in result | PASS |
| W1 | workspace returns all catalog rows | PASS |
| W2 | availability field present on all items | PASS |
| W3 | schema_id populated for READY_FOR_EDIT | PASS |
| W4 | schema_id=None, candidate_count≥1 for PREPARING | PASS |
| W5 | schema_id=None, candidate_count=0 for NO_SCHEMA | PASS |
| W6 | availability filter applied | PASS |
| W7 | page/page_size echoed in result | PASS |
| W8 | page_size capped at 200 | PASS |
