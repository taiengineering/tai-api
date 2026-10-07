---
wo: WO-DOC-OBJ02-C2A-RUNTIME-STATE-CONTRACT-001
contract: CONFIRM_REGRESSION_ANALYSIS
status: SAFE
---

# Confirm Regression Analysis

## Question

Is `render_document_html()` safe for APPROVED_BY_HUMAN documents?

## Evidence (CORR-06)

`render_document_html()` for `APPROVED_BY_HUMAN` status:
- Queries `runtime_document_archive` WHERE `(runtime_document_id = doc_id AND document_version = doc_version)`
- If no row found → ValueError raised (fail-close, no fallback to mutable state)
- If row found but `rendered_body` is None → ValueError raised

`runtime_document_archive` UNIQUE(runtime_document_id, document_version) = EXISTS (uq_rdarch_doc_version)

confirmed fresh render fallback = PROHIBITED (fail-close)

## Version Increment Removed (CORR-04)

The version increment in `update_document()` has been removed. Version is managed only by the confirmation flow.

## Archive Contract

The archive query uses exact match on `document_version` (not `order by confirmed_at desc`). This means:
- The archived body is pinned to the version that was confirmed
- If the document is re-edited after confirmation (via RETURNED_FOR_EDIT), a new version will be created upon re-confirm
