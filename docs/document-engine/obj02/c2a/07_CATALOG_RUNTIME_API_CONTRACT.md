---
wo: WO-DOC-OBJ02-C2A-RUNTIME-STATE-CONTRACT-001
contract: CONTRACT_A_CATALOG_API
status: IMPLEMENTED
---

# Catalog Runtime API Contract (CONTRACT A)

## Endpoint

`GET /document-engine/catalog/{doc_id}`

Where `doc_id` is `document_forms.doc_id` string (e.g., `"DOC-BLD-002"`), NOT a UUID.

## Lookup Flow

1. Query `document_forms` by `doc_id` string to get the `document_forms.id` UUID
2. Call `catalog_resolver.resolve_catalog_runtime_schema(catalog_document_id=UUID)` 
3. Build response

## Response Shape

```json
{
  "status": "success",
  "data": {
    "catalog": {
      "id": "<UUID>",
      "doc_id": "DOC-BLD-002",
      "doc_name": "...",
      "sector": "...",
      "category": "..."
    },
    "runtime": {
      "schema_id": "<UUID or null>",
      "schema_status": "CANDIDATE | APPROVED_FOR_RUNTIME_USE | null",
      "availability": "PREPARING | READY_FOR_EDIT | NO_SCHEMA",
      "can_create": false
    },
    "fields": [...],
    "checklists": [...],
    "evidence_fields": [...],
    "supported_export_formats": ["HTML", "PDF"]
  }
}
```

## `can_create` Rule

`can_create = true` ONLY when `availability == "READY_FOR_EDIT"` (i.e., exactly one `APPROVED_FOR_RUNTIME_USE` schema exists for this catalog document).

## Error Responses

- 404: `doc_id` not found in `document_forms`
- 500: integrity violation (multiple approved schemas — should never happen due to DB constraint)

## Tests

A1–A3 in `tests/test_doc_obj02c2a_runtime_state_contract.py`
