---
title: AUTO-REUSE-01 Final Evidence (CORR-002)
wo: WO-DOC-AUTO-REUSE-01-CORR-002-FINAL-READMODEL-ALIGNMENT
status: CORR_002_COMPLETE
date: 2026-10-08
branch_api: feat/doc-auto-reuse-discovery
branch_admin: feat/doc-auto-reuse-library
---

# AUTO-REUSE-01 CORR-002 RESULT

## A. API GIT

| Field | Value |
|-------|-------|
| before HEAD (CORR-001) | `ba82afca` |
| after HEAD | `13953ff1` |
| origin/main | `ca03bf5f` |
| origin/main ancestor | YES |
| behind_by | 0 |
| ahead_by | 4 |
| branch | `feat/doc-auto-reuse-discovery` |
| remote verified | `13953ff1` ✓ |

Changed files (CORR-002):
- `services/document_engine/auto_source_readmodel.py`
- `tests/test_auto_reuse_01_discovery.py`

## B. ADMIN GIT

| Field | Value |
|-------|-------|
| before HEAD (CORR-001) | `bf80cb91` |
| after HEAD | `196013ba` |
| origin/main | `23dbf0e6` |
| origin/main ancestor | YES |
| behind_by | 0 |
| branch | `feat/doc-auto-reuse-library` |
| remote verified | `196013ba` ✓ |

Changed files (CORR-002):
- `vue3/src/pages/engine-document/__tests__/autoDocumentTab.test.ts`

## C. EFFECTIVE READ MODEL

| Field | Value |
|-------|-------|
| raw IN_PROGRESS + effective COMPLETED included | YES |
| source_status returned | `effective.inspection_status` |
| inspection_date authority | effective first, fallback to raw |
| factory_id authority | effective first, fallback to raw |
| company_id authority | effective first, fallback to raw |

Root cause fixed: `_insp_item(row, effective)` — source_status and other item fields
now use effective resolved record values, not raw candidate row. Before this fix,
production case `raw=IN_PROGRESS / effective=COMPLETED` would show `source_status=IN_PROGRESS`
in the UI despite the document being effectively complete.

## D. RESOLVER

| Field | Value |
|-------|-------|
| existing resolver reused | YES (`resolve_inspection_record`) |
| new folding logic | NO |
| known InspectionRecordError behavior | fail-close exclude (continue) |
| unexpected exception behavior | propagate (no bare except Exception) |

Error handling before: `except (InspectionRecordError, Exception): pass` — swallowed all errors silently.
Error handling after: `except InspectionRecordError: continue` — unexpected errors propagate so that
infrastructure failures don't silently empty the document list.

## E. TENANT SCOPE

| Test | Result |
|------|--------|
| SC1 — safety_inspections.company_id not referenced | PASS |
| SC2 — empty work_schedules → no inspections | PASS |
| SC3 — company A/B isolation | PASS |
| SC4 — factory A/B isolation | PASS |

`safety_inspections.company_id` referenced: NO

SC3/SC4 use realistic `_FakeQuery` with actual `eq()` / `in_()` filtering to prove
Company A cannot see Company B's inspections, and Factory A cannot see Factory B's inspections.

## F. RENDER

| Case | Result |
|------|--------|
| IN_PROGRESS inspection preview/pdf | BLOCKED (404 AUTO_DOCUMENT_NOT_READY) |
| DRAFT TBM preview/pdf | BLOCKED (404 AUTO_DOCUMENT_NOT_READY) |
| COMPLETED inspection | existing INSP generator |
| COMPLETED TBM | existing TBM generator |

## G. TESTS

| Suite | Count |
|-------|-------|
| backend I1-I4 + L1-L10 + R1-R4 + M1-M3 + S1-S2 + E1-E5 + SC1-SC4 + RR1-RR4 | **36/36 PASS** |
| frontend AT-01~AT-09 | **9/9 PASS** |
| frontend regression | **217/217 PASS** |
| **Total** | **262 PASS / 0 FAIL** |

New tests added in CORR-002: E5, SC3, SC4, AT-09

## H. REUSE

| Asset | Count |
|-------|-------|
| new fetcher | 0 |
| new renderer | 0 |
| new classifier | 0 |
| new mapping | 0 |
| new table | 0 |
| new migration | 0 |

## I. PRODUCTION

| Guard | Status |
|-------|--------|
| DB write | 0 |
| deploy | NO |
| abandoned 02B migration applied | NO |
| `inspection_set_projection_binding` production | 0 |
| `document_equipment_projection_map` production | 0 |
| `20261007182044` migration applied | NO |

## J. FINAL

```
AUTO-REUSE-01 CORR-002 = COMPLETE

tai-api  feat/doc-auto-reuse-discovery  HEAD=13953ff1  remote=VERIFIED  behind=0
         tests=36/36 PASS

tai-admin feat/doc-auto-reuse-library   HEAD=196013ba  remote=VERIFIED  behind=0
          tests=226/226 PASS (9 new + 217 regression)

GPT INDEPENDENT VERIFY = REQUIRED
AUTO-REUSE-01 CLOSED = NO
PRODUCTION APPLY = BLOCKED
```
