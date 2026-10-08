---
title: AUTO-REUSE-01 Final Evidence (CORR-001)
wo: WO-DOC-AUTO-REUSE-01-CORR-001-EFFECTIVE-STATUS-AND-SCOPE
status: CORR_001_COMPLETE
date: 2026-10-08
branch_api: feat/doc-auto-reuse-discovery
branch_admin: feat/doc-auto-reuse-library
---

# AUTO-REUSE-01 CORR-001 Final Evidence

## A. API GIT

| Field | Value |
|-------|-------|
| before HEAD (pre-CORR-001, rebased) | `d5f1eae5` |
| after HEAD | `579e43f1` |
| origin/main | `5eb422ca` |
| origin/main ancestor | YES |
| branch | `feat/doc-auto-reuse-discovery` |
| remote verified | `579e43f1` ✓ |

Changed files:
- `routers/document_engine_api.py`
- `services/document_engine/auto_source_readmodel.py`
- `tests/test_auto_reuse_01_discovery.py`

## B. ADMIN GIT

| Field | Value |
|-------|-------|
| before HEAD (initial) | `b3898a0c` |
| after HEAD | `bf80cb91` |
| branch | `feat/doc-auto-reuse-library` |
| remote verified | `bf80cb91` ✓ |

Changed files:
- `vue3/src/pages/engine-document/useEngineDocumentList.ts`
- `vue3/src/pages/engine-document/__tests__/autoDocumentTab.test.ts` (NEW)

## C. Test Results

### Backend (tai-api) — 33/33 PASS

```
tests/test_auto_reuse_01_discovery.py — 33/33 PASS

I1-I4:  Identity / document_key format — 4/4 PASS
L1-L10: list_auto_documents unit tests — 10/10 PASS
R1-R4:  Render delegation (mock generator) — 4/4 PASS
M1-M3:  Mutation guard — 3/3 PASS
S1-S2:  Scope / cross-company guard — 2/2 PASS
E1-E4:  Effective status contract (resolver) — 4/4 PASS  [CORR-001 NEW]
SC1-SC2: Inspection scope via work_schedules — 2/2 PASS  [CORR-001 NEW]
RR1-RR4: Render readiness validators — 4/4 PASS          [CORR-001 NEW]
```

### Frontend (tai-admin) — 225/225 PASS (217 regression + 8 new)

```
vue3/src/pages/engine-document/__tests__/autoDocumentTab.test.ts — 8/8 PASS

AT-01: loadAutoDocuments success → items and total stored
AT-02: loadAutoDocuments API failure → error state, empty items
AT-03: loadAutoDocuments with source_type filter → URL includes source_type param
AT-04: previewAutoDocument → requestText called, dialog opens with HTML
AT-05: previewAutoDocument failure → error HTML in srcdoc
AT-06: closeAutoPreview → dialog closes and HTML cleared
AT-07: downloadAutoDocument → api.download called with correct endpoint and filename
AT-08: downloadAutoDocument failure → warning toast shown
```

## D. CORR-001 P0 Fixes

### P0-1: Inspection Effective Status via Resolver

- `_INSP_CANDIDATE_STATUSES` now includes `IN_PROGRESS` (raw status is candidate narrowing only)
- `_fetch_inspections` calls `resolve_inspection_record(row["id"], sb)` for each candidate
- Inclusion gate: `effective.get("is_active") AND effective.get("inspection_status") == "COMPLETED"`
- Resolver error → fail-closed (exclude silently)
- Covered by E1-E4

### P0-2: Inspection Scope via work_schedules

- `safety_inspections` has no `company_id` column — scope routes through `assignment_id → work_schedules.id → work_schedules.company_id/factory_id`
- `_fetch_inspection_assignment_ids(sb, scope_filter)` returns:
  - `None` → ALL tier (`scope_filter = {}`), no restriction
  - `[]` → scope has no matching work_schedules → caller returns empty immediately
  - `[ids]` → allowed assignment_ids; applied as `.in_("assignment_id", assignment_ids)`
- SC1: verifies `company_id` NOT passed directly to `safety_inspections` query
- SC2: empty work_schedules → empty result

### P0-3: Render Readiness Validators

- `_require_auto_inspection_ready(sb, inspection_id)`: calls resolver → 404 `AUTO_DOCUMENT_NOT_READY` if not `is_active=True AND inspection_status=COMPLETED`
- `_require_auto_tbm_ready(sb, tbm_id)`: queries `tbm_meetings.status_code` → 404 if not `COMPLETED`
- Both called in `auto_document_preview` and `auto_document_pdf` after ownership check
- Covered by RR1-RR4

## E. Zero Persistence Verification

- M1: `list_auto_documents` with INSERT-trapping mock sb — no INSERT called ✓
- M2: No `*auto_reuse*` migration files in `supabase/migrations/` ✓
- M3: `auto_source_projection_selector.py` and `equipment_projection_resolver.py` do NOT exist ✓
- CORR-001: Zero new DB objects, zero new migrations ✓

## F. ABANDONED Branch Guard

- Branch `feat/doc-auto-src-02b-projection-selector` (HEAD `07e866e5`) = ABANDONED
- Migration `20261007182044_doc_auto_src_02b_projection_selector.sql` = PRODUCTION APPLY ABSOLUTELY FORBIDDEN

## G. Scope Invariants

- DENY scope → empty result (L4, S1)
- Empty scope `{}` = ALL tier → no work_schedules lookup, no restriction (SC1 verifies)
- Tenant scope → assignment_ids from work_schedules → applied to safety_inspections query

## H. Document Key Format

- INSPECTION: `auto:v1:INSPECTION:{uuid}:INSP:-`
- TBM: `auto:v1:TBM:{uuid}:TBM:-`

## I. Title Fallbacks

- INSPECTION: `work_schedules.summary` → `"점검 기록"` if null/missing
- TBM: `meeting_title` → `"TBM YYYY-MM-DD"` if null

## J. Pagination

- Server cap: 500 rows per source before Python-level pagination
- `page=2, page_size=3` on 10 rows → 3 items, total=10, total_pages=4 (L9)

## K. RFC 5987 Filename Encoding

Korean filename encoded as `filename*=UTF-8''%EC%A0%90...` to satisfy HTTP latin-1 header constraint.

## L. Status

```
AUTO-REUSE-01 CORR-001

tai-api  feat/doc-auto-reuse-discovery  HEAD=579e43f1  remote=VERIFIED  tests=33/33 PASS
tai-admin feat/doc-auto-reuse-library   HEAD=bf80cb91  remote=VERIFIED  tests=225/225 PASS

GPT INDEPENDENT VERIFY = PENDING
```
