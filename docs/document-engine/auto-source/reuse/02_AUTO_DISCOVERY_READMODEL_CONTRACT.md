---
title: AUTO-REUSE-01 Auto Discovery Read Model Contract
wo: WO-DOC-AUTO-REUSE-01-EXISTING-ASSET-DISCOVERY-LIBRARY
status: IMPLEMENTATION_COMPLETE
date: 2026-10-08
---

# Auto Discovery Read Model Contract

## Module

`services/document_engine/auto_source_readmodel.py`

## Public API

```python
list_auto_documents(
    sb: Any,
    scope_filter: ScopeFilter,
    *,
    source_type: str = "ALL",   # "ALL" | "INSPECTION" | "TBM"
    factory_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]
```

## Return Shape

```json
{
  "items": [AutoDocumentItem],
  "total": int,
  "page": int,
  "page_size": int,
  "total_pages": int
}
```

## AutoDocumentItem Shape

| Field | Type | Source |
|-------|------|--------|
| `document_key` | str | `auto:v1:{SOURCE_TYPE}:{SOURCE_ID}:{DOC_TYPE}:-` |
| `channel` | str | Always `"AUTO_SOURCE"` |
| `source_type` | str | `"INSPECTION"` or `"TBM"` |
| `source_id` | str | UUID of the source record |
| `doc_type` | str | `"INSP"` or `"TBM"` |
| `title` | str | INSP: `work_schedules.summary` or `"점검 기록"` fallback; TBM: `meeting_title` or `"TBM YYYY-MM-DD"` fallback |
| `occurred_at` | str | INSP: `inspection_date`; TBM: `completed_at` or `work_date` |
| `source_status` | str | `status_code` from source row |
| `factory_id` | str | From row or `work_schedules.factory_id` |
| `company_id` | str | From row or `work_schedules.company_id` |
| `can_preview` | bool | Always `True` |
| `can_pdf` | bool | Always `True` |

## Terminal Status Filters

- INSPECTION: `status_code IN ('COMPLETED', 'ISSUE', 'HOLD', 'completed')`
- TBM: `status_code = 'COMPLETED'`

## Guarantees

- Zero DB writes (read-only)
- `DENY` scope_filter → returns `{"items": [], "total": 0, ...}` immediately, no query
- Max 500 rows per source (server-side hard cap before pagination)
- Python-level pagination (offset/limit on unified sorted list)
- Sort: `occurred_at DESC` then `source_type`, `source_id` for stability
