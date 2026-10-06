---
title: OBJ02-B1 Runtime Guard Verification (CORR-05 applied)
description: Fail-close guard for create_document() — post-correction test with correct enum values
type: evidence
wo: WO-DOC-OBJ02-B1-CORRECTION-002
status: VERIFIED_8_PASS
---

# OBJ02-B1 Runtime Guard Verification

## Change Location

File: `services/document_engine_svc.py`
Function: `create_document()`
Inserted after: `if not schema.data: raise ValueError("schema not found")`

## Guard Code

```python
if schema.data["status"] != "APPROVED_FOR_RUNTIME_USE":
    raise ValueError(
        f"schema not approved for runtime use: {form_schema_id} "
        f"(status={schema.data['status']})"
    )
```

## Behavior Contract

| Schema Status | create_document() Result |
|---------------|--------------------------|
| APPROVED_FOR_RUNTIME_USE | Allowed — DRAFT document created |
| CANDIDATE | Denied — ValueError raised |
| NEEDS_HUMAN_REVIEW | Denied — ValueError raised |
| APPROVED_BY_HUMAN | Denied — ValueError raised |
| REJECTED_BY_HUMAN | Denied — ValueError raised |
| ARCHIVED | Denied — ValueError raised |
| (not found) | Denied — ValueError "schema not found" |

## CORR-05: Enum Fix

Pre-correction tests used `REJECTED` — not a valid status in the DB enum.
Post-correction tests use `REJECTED_BY_HUMAN` (the actual DB status value).

## Test Results (8/8)

File: `tests/test_doc_obj02b1_runtime_guard.py`

| Test | Scenario | Result |
|------|----------|--------|
| G1 | APPROVED_FOR_RUNTIME_USE → allowed, DRAFT created | PASS |
| G2 | CANDIDATE → denied, 0 inserts | PASS |
| G3 | NEEDS_HUMAN_REVIEW → denied, 0 inserts | PASS |
| G4 | APPROVED_BY_HUMAN → denied, 0 inserts | PASS |
| G5 | REJECTED_BY_HUMAN → denied, 0 inserts (CORR-05) | PASS |
| G6 | ARCHIVED → denied, 0 inserts | PASS |
| G7 | Not found → denied | PASS |
| G8 | All non-APPROVED statuses → 0 inserts (comprehensive) | PASS |
