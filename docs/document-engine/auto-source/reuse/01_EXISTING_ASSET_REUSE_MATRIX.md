---
title: AUTO-REUSE-01 Existing Asset Reuse Matrix
wo: WO-DOC-AUTO-REUSE-01-EXISTING-ASSET-DISCOVERY-LIBRARY
status: IMPLEMENTATION_COMPLETE
date: 2026-10-08
---

# AUTO-REUSE-01 Existing Asset Reuse Matrix

## Reused Assets — Zero New Document Engine Components

| Source | Fetcher | Template | render_html | render_pdf | Ownership Guard |
|--------|---------|----------|-------------|------------|-----------------|
| INSPECTION | InspectionFetcher (existing) | DOC-INSP.html (existing) | `generator.render_html("INSP", {...})` | `generator.render_pdf("INSP", {...})` | `_ensure_inspection_own()` from `routers/inspection_checklist.py` |
| TBM | TbmFetcher (existing) | DOC-OSH-056.html (existing) | `generator.render_html("TBM", {...})` | `generator.render_pdf("TBM", {...})` | `_ensure_tbm_own()` from `routers/tbm.py` |

## Explicitly Forbidden (per WO mandate)

- New DB tables: FORBIDDEN
- New migrations: FORBIDDEN
- New classifier: FORBIDDEN
- New fetcher: FORBIDDEN
- New document engine: FORBIDDEN
- New selector (02B pattern): FORBIDDEN

## Branch: feat/doc-auto-src-02b-projection-selector — ABANDONED

Migration `20261007182044_doc_auto_src_02b_projection_selector.sql` = PRODUCTION APPLY ABSOLUTELY FORBIDDEN.

## New Files Added (thin adapters only)

| File | Role |
|------|------|
| `services/document_engine/auto_source_readmodel.py` | Read-only list query — INSPECTION + TBM terminal records |
| `routers/document_engine_api.py` (3 endpoints added) | Thin secure render adapter |
| `tests/test_auto_reuse_01_discovery.py` | 38 contract tests |
