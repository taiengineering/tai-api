---
wo: WO-DOC-OBJ02-C2A-RUNTIME-STATE-CONTRACT-001
contract: CONTRACT_D_EXPORT
status: IMPLEMENTED
---

# Transient Export Contract (CONTRACT D)

## Endpoint

`POST /document-engine/documents/{doc_id}/generate`

Body: `{"export_type": "HTML" | "PDF"}`

## Behavior

| export_type | Response |
|-------------|----------|
| `"HTML"` | `HTMLResponse` with canonical HTML |
| `"PDF"` | `Response(media_type="application/pdf")` via Gotenberg |

## Transient Export Rules

- generated_document INSERT = 0 — no PENDING row, no COMPLETE row. Export is purely transient.
- The `generate_document()` service function that inserted PENDING rows has been REMOVED (CORR-13)
- Render calls `render_document_html(doc_id)` which uses only `runtime_document_data`
- No `InspectionFetcher` or `TbmFetcher` calls
- Format validation: only HTML and PDF accepted (422 for others)

## PDF Generation

HTML is sent to Gotenberg at `GOTENBERG_URL/forms/chromium/convert/html` with A4 paper settings. If Gotenberg is unavailable, returns HTTP 500.

## Previous Behavior (Broken)

The old `generate_document()` only created a `generated_document` row with `status=PENDING` and returned that — no actual HTML or PDF was produced.

## Tests

P2–P4 in `tests/test_doc_obj02c2a_runtime_state_contract.py`
