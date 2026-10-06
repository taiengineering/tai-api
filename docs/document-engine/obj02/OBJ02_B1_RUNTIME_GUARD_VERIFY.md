---
title: OBJ02-B1 Runtime Guard Verification
description: Fail-close guard for create_document() — CANDIDATE schemas denied
type: evidence
wo: WO-DOC-OBJ02-B1-CATALOG-SCHEMA-BINDING-001
status: VERIFIED_29_PASS
---

# OBJ02-B1 Runtime Guard Verification

## Change Location

File: `services/document_engine_svc.py`
Function: `create_document()`
Lines: inserted after `if not schema.data: raise ValueError("schema not found")`

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
| REJECTED | Denied — ValueError raised |
| ARCHIVED | Denied — ValueError raised |
| (not found) | Denied — ValueError "schema not found" |

## Pre-Guard State (OBJ02-A Finding)

Before this WO: `create_document()` checked only `if not schema.data` (existence).
Status was fetched (`select("id,status")`) but never evaluated.
CANDIDATE schemas could silently produce DRAFT runtime documents.

## Post-Guard State

Status is evaluated immediately after existence check.
All non-APPROVED statuses raise ValueError before any DB INSERT is attempted.
No insert call occurs for denied schemas (verified: G2~G8, G8 comprehensive).

## Test Results

File: `tests/test_doc_obj02b1_runtime_guard.py`

| Test | Scenario | Result |
|------|----------|--------|
| G1 | APPROVED_FOR_RUNTIME_USE → allowed | PASS |
| G2 | CANDIDATE → denied | PASS |
| G3 | NEEDS_HUMAN_REVIEW → denied | PASS |
| G4 | APPROVED_BY_HUMAN → denied | PASS |
| G5 | REJECTED → denied | PASS |
| G6 | ARCHIVED → denied | PASS |
| G7 | Not found → denied | PASS |
| G8 | All non-APPROVED → zero inserts (comprehensive) | PASS |
