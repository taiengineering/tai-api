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
| `services/document_engine_svc.py` | CORR-01~13: dedup, null preserve, strict validation, status whitelist, confirmed fail-close, generate_document removal |
| `services/document_engine/catalog_resolver.py` | CORR-01: candidate schema detail (fields/checklists/evidence_fields) returned, 4 new keys |
| `services/document_engine/renderer.py` | CORR-07: `html_to_pdf()` adapter function added |
| `routers/document_engine_api.py` | CORR-08~11: httpx removed, html_to_pdf wired, auth added, catalog keys updated |
| `tests/test_doc_obj02c2a_runtime_state_contract.py` | ES-1~8, C1~5, K7, P6, updated M3/A2 |

## Correction Notes

| ID | Description |
|----|-------------|
| CORR-01 | PREPARING availability: candidate schema detail (fields/checklists/evidence_fields) returned. 4 new keys: active_schema_id/active_schema_status/candidate_schema_id/candidate_schema_status |
| CORR-02 | `_validate_runtime_keys()`: empty schema (0 fields) rejects arbitrary keys (no bypass) |
| CORR-03 | null values preserved as-is in stored state (not deleted) |
| CORR-04 | version auto increment = REMOVED from update_document() |
| CORR-05 | ARCHIVED→strict whitelist: DRAFT/IN_PROGRESS/RETURNED_FOR_EDIT only |
| CORR-06 | APPROVED_BY_HUMAN archive: fail-close by (doc_id, version). No fallback to mutable state |
| CORR-12 | Duplicate resolve_runtime_document_state/render_document_html removed |
| CORR-13 | generate_document (INSERT PENDING row) = REMOVED. Export is purely transient |
| CORR-14 | Full runtime authorization: all document instance endpoints require auth + tenant scope |
| CORR-15 | ARCHIVED reprint: status in ("APPROVED_BY_HUMAN", "ARCHIVED") → archive only |
| CORR-16 | Single Gotenberg adapter: generate_document_pdf() delegates to html_to_pdf() |
| CORR-19 | create scope uses require_scope_ids — FACTORY tier factory bypass impossible. Client-supplied company_id/factory_id in POST body are ignored; server resolves from token. |
| CORR-20 | created_by/updated_by/uploaded_by/actor_id all server-bound to current_user.id. Body-supplied actor values are rejected if they mismatch the authenticated user. |

## generated_document INSERT = 0 (no row created)

The `generate_document()` service function that inserted a PENDING row has been removed. Export is transient only.

## Test Results

All tests PASS. B1 regression tests PASS (no regression).
