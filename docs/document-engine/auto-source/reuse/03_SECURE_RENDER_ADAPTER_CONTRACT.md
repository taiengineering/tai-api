---
title: AUTO-REUSE-01 Secure Render Adapter Contract
wo: WO-DOC-AUTO-REUSE-01-EXISTING-ASSET-DISCOVERY-LIBRARY
status: IMPLEMENTATION_COMPLETE
date: 2026-10-08
---

# Secure Render Adapter Contract

## Endpoints (added to `routers/document_engine_api.py`)

### List

```
GET /document-engine/auto-documents
```

Query params: `source_type` (ALL/INSPECTION/TBM), `factory_id`, `page`, `page_size` (1-50)

Auth: `get_current_user` → `scoped_filter()`

Response: `AutoDocumentListResponse` (items + pagination)

### Preview

```
GET /document-engine/auto-documents/{source_type}/{source_id}/preview
```

Auth chain: `get_current_user` → ownership guard → source readiness validation → `render_html(doc_type, params)`

| source_type | ownership guard | readiness validation | render call |
|-------------|----------------|----------------------|-------------|
| INSPECTION | `_ensure_inspection_own(sb, source_id, current)` | `_require_auto_inspection_ready()` — `resolve_inspection_record()` must return `is_active=true` + `inspection_status=COMPLETED`; `InspectionRecordError` → 404; unexpected errors propagate | `_render_html("INSP", {"inspection_id": source_id})` |
| TBM | `_ensure_tbm_own(sb, source_id, current)` | `_require_auto_tbm_ready()` — `tbm_meetings.status_code` must be `COMPLETED` | `_render_html("TBM", {"meeting_id": source_id})` |

Response: `HTMLResponse`

### PDF

```
GET /document-engine/auto-documents/{source_type}/{source_id}/pdf
```

Auth chain: `get_current_user` → ownership guard → source readiness validation → `render_pdf(doc_type, params)`

| source_type | ownership guard | readiness validation | render call | filename |
|-------------|----------------|----------------------|-------------|----------|
| INSPECTION | `_ensure_inspection_own(sb, source_id, current)` | `_require_auto_inspection_ready()` | `_render_pdf("INSP", {"inspection_id": source_id})` | `점검기록_{id[:8]}.pdf` |
| TBM | `_ensure_tbm_own(sb, source_id, current)` | `_require_auto_tbm_ready()` | `_render_pdf("TBM", {"meeting_id": source_id})` | `TBM_{id[:8]}.pdf` |

Response: `application/pdf` with RFC 5987 `Content-Disposition` header (`filename*=UTF-8''<url-encoded>`)

## Security Invariants

- `doc_type` is server-side fixed — client cannot override (INSPECTION→INSP, TBM→TBM)
- Ownership guard executes before any render call
- Cross-company access returns 403/404 via existing guard logic
- Zero persistence: no write to `runtime_document_data`, `generated_document`, or Storage
