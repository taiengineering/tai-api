---
title: Runtime Save Contract — Gates S1/S2/S3
description: Field / checklist / evidence save contracts for runtime document engine
type: evidence
wo: WO-DOC-OBJ02-C1-SUPPLEMENTAL-CONTRACT-VERIFY-002
status: COLLECTED
gates: S1 S2 S3
---

# Runtime Save Contract — Gates S1/S2/S3

## Gate S1: Field Save Contract

### Endpoint

`PATCH /document-engine/documents/{doc_id}` (`routers/document_engine_api.py:110`)

### Service

`services/document_engine_svc.py:update_document()` (line 175)

### Contract

```python
def update_document(
    doc_id: str,
    runtime_data_json: dict = None,
    evidence_links: list = None,
    updated_by: str = None,
) -> dict:
    ...
    if runtime_data_json is not None:
        _validate_field_keys(sb, schema_id, runtime_data_json)
        update["runtime_data_json"] = runtime_data_json  # FULL REPLACE
```

**SAVE TYPE: FULL_REPLACE** — `runtime_data_json` is replaced entirely on each PATCH. There is no merge/partial update. If the frontend sends only a subset of fields, the remaining fields are cleared.

### Guardrails

- `_validate_field_keys`: only field_keys registered in `runtime_field` for this schema are allowed. Unknown keys raise `ValueError`.
- Status guard: ARCHIVED documents cannot be modified.

### Impact on P0 Documents

Gate B1 finding: frontend cannot obtain `form_schema_id` from `GET /document-forms/{id}`, so `create_document()` fails before any save can occur. All 24 P0 documents: **S1 BLOCKED** (pre-condition: runtime document creation blocked).

---

## Gate S2: Checklist Save Contract

### Search Result

`PATCH /document-engine/documents/{doc_id}` accepts: `runtime_data_json`, `evidence_links`, `updated_by`.

`DocumentUpdateIn` schema (inferred from router):
- `runtime_data_json: dict`
- `evidence_links: list`
- `updated_by: str`

There is **no `checklist_results` or `checklist_data` parameter**.

There is **no dedicated checklist save endpoint** in `document_engine_api.py`.

### Contract

**NO_CHECKLIST_SAVE_CONTRACT**

Checklist results (`runtime_checklist_item` completions) cannot be saved via any current API endpoint. The checklist layer exists only as schema metadata (input_type, raw_text, status) — there is no runtime execution storage path.

### Impact

96 checklist items across 24 P0 documents: cannot be completed via the runtime document engine API.

---

## Gate S3: Evidence Save Contract

### Endpoint

`POST /document-engine/documents/{doc_id}/evidence` (`routers/document_engine_api.py:192`)

### Service

`services/document_engine_svc.py:link_evidence()` (line 328)

### Contract

APPEND_ONLY — each POST creates a new row in `evidence_vault_link`.

### Validation

`_validate_evidence_links`: `linked_field_id` must exist in `runtime_evidence_field` for this schema.

### Impact on P0 Documents

Gate B1 finding: all 24 P0 docs are **S3 BLOCKED** because runtime document creation itself is blocked (same pre-condition as S1).

---

## Save Contract Summary

| Gate | Contract | Status for P0 docs |
|------|----------|-------------------|
| S1 Field save | FULL_REPLACE via PATCH runtime_data_json | BLOCKED (create_document fails) |
| S2 Checklist save | NO_CONTRACT — endpoint does not exist | BLOCKED (no API) |
| S3 Evidence save | APPEND_ONLY via POST evidence | BLOCKED (create_document fails) |
