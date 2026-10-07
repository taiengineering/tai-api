---
wo: WO-DOC-OBJ02-C2A-RUNTIME-STATE-CONTRACT-001
contract: CONTRACT_C_RENDER
status: IMPLEMENTED
---

# Canonical Render Contract (CONTRACT C)

## Functions

### `resolve_runtime_document_state(doc_id) -> dict`

Loads full document state without calling any source DB fetcher.

Returns:
```python
{
    "document": <runtime_document_data row>,
    "schema": <runtime_form_schema row>,
    "fields": [<runtime_field rows ordered by field_order>],
    "checklists": [<runtime_checklist_item rows ordered by item_order>],
    "evidence_fields": [<runtime_evidence_field rows>],
    "catalog": <document_forms row or None>,
}
```

Raises `ValueError` if document or schema not found.

### `render_document_html(doc_id) -> str`

Render pipeline (CORR-06):
1. Call `resolve_runtime_document_state(doc_id)`
2. If `status == "APPROVED_BY_HUMAN"`: load `rendered_body` from `runtime_document_archive` WHERE `(runtime_document_id, document_version)` exact match. APPROVED_BY_HUMAN: archive ONLY, exact by (runtime_document_id, document_version). No fallback to mutable state. Missing archive = EXPORT FAIL (ValueError raised).
3. Otherwise: call `document_schema_renderer.build_render_artifacts()` for a fresh deterministic render.

## Render Endpoint

`GET /document-engine/documents/{doc_id}/render` → `HTMLResponse`

- 404 if document not found
- 500 if render fails

## Prohibitions

- NO `InspectionFetcher` call
- NO `TbmFetcher` call
- NO `generated_document` INSERT
- NO auto-fill / inferred values
- NO hostname / timestamp injection

## Determinism

Same `runtime_document_data` + same schema → byte-for-byte identical HTML (guaranteed by `document_schema_renderer.build_render_artifacts()`).

## Tests

R1–R5, P2–P4 in `tests/test_doc_obj02c2a_runtime_state_contract.py`
