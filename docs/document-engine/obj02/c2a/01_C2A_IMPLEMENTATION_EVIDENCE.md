---
wo: WO-DOC-OBJ02-C2A-RUNTIME-STATE-CONTRACT-001
branch: feat/doc-obj02c2a-runtime-state-contract
status: IMPLEMENTED
date: 2026-10-07
---

# C2A Implementation Evidence

## Overview

OBJ02-C2A fixes four runtime workflow breakages identified in the C1 audit:

| ID | Problem | Fix |
|----|---------|-----|
| B1 | `GET /document-forms/{id}` had no `form_schema_id` — frontend cannot create docs | New `GET /document-engine/catalog/{doc_id}` endpoint (CONTRACT A) |
| X1 | `POST /document-engine/documents/{id}/generate` created only a PENDING stub | Fixed to render canonical HTML and optionally produce PDF via Gotenberg |
| S2 | No checklist save endpoint — `runtime_data_json` only accepted `runtime_field.field_key` | `_validate_runtime_keys()` now allows checklist UUIDs as valid keys |
| Merge | `update_document()` did FULL_REPLACE destroying other fields | Changed to PATCH merge semantics |

## Files Changed

| File | Change |
|------|--------|
| `services/document_engine_svc.py` | CONTRACT B + C: `_validate_runtime_keys()`, PATCH merge, version increment, `resolve_runtime_document_state()`, `render_document_html()` |
| `routers/document_engine_api.py` | CONTRACT A + C + D: catalog endpoint, render endpoint, fixed generate endpoint |
| `tests/test_doc_obj02c2a_runtime_state_contract.py` | 26 tests: K1-K6, M1-M3, R1-R5, P2-P4, A1-A3 |

## Test Results

All 26 C2A tests PASS. All 26 existing B1 tests PASS (no regression).

```
26 passed in 0.08s  (C2A tests)
26 passed in 0.09s  (B1 regression tests)
```
