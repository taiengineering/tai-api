---
title: OBJ02-B1 Disposable DB Verification
description: Migration execution result on PostgreSQL 16 disposable container
type: evidence
wo: WO-DOC-OBJ02-B1-CORRECTION-002
status: VERIFIED_ALL_PASS
db_version: PostgreSQL 16.15 (aarch64-unknown-linux-musl, postgres:16-alpine)
---

# OBJ02-B1 Disposable DB Verification

## Environment

- Container: `docker run postgres:16-alpine` (isolated, destroyed after test)
- Port: 15432 (local only)
- DB: `tai_test` / `tai_test_neg` / `tai_test_m2`

## Fixture Design

Production-like schema:

```sql
document_forms (260 rows)
runtime_form_schema (324 rows total)
  - document_forms-sourced: 260 (source_trace.source_table = 'document_forms')
  - document_form_master-sourced: 64 (source_trace.source_table = 'document_form_master')
```

Source trace structure mirrors production:
`{"source_table":"...","source_id":"<uuid>","doc_id":"DOC-NNNN"}`

## Positive Migration Execution

Command: `psql ... -f supabase/migrations/20261006193021_catalog_schema_binding_b1.sql`

Output: `DO / ALTER TABLE / UPDATE 260 / DO / ALTER TABLE / ALTER TABLE / CREATE INDEX × 3 / DO`

Post-migration verification:

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| NOT NULL count | 260 | 260 | PASS |
| NULL count | 64 | 64 | PASS |
| Dangling FK | 0 | 0 | PASS |
| Kind conflict (source_table check) | 0 | 0 | PASS |

## Negative Tests (all on fresh DBs)

| ID | Scenario | Migration outcome | Result |
|----|----------|------------------|--------|
| M1 | document_forms = 1 row (not 260) | PRE FAIL message, full ROLLBACK | PASS |
| M2 | 1 source_trace doc_id mismatch (259 match, 1 wrong) | PRE FAIL dual-condition count=259, ROLLBACK | PASS |
| M4 | catalog_document_id column pre-exists | PRE guard fires as expected | PASS |
| M5 | Set catalog_document_id on master-sourced schema | `check_violation` raised (chk_rfs_catalog_source_kind) | PASS |
| ACTIVE_UNIQUE | Second APPROVED schema for same catalog_document_id | `unique_violation` raised (uq_rfs_catalog_active_approved) | PASS |
| VER_UNIQUE | Duplicate (catalog_document_id, version=1) | `unique_violation` raised (uq_rfs_catalog_version) | PASS |
| DELETE_RESTRICT | DELETE document_forms row referenced by schema | `foreign_key_violation` raised (fk_rfs_catalog_document) | PASS |

## Transaction Atomicity Verification

M1 test confirmed full ROLLBACK: after PRE guard fired, `catalog_document_id` column was NOT added to `runtime_form_schema` (count=0 in `information_schema.columns`). All DDL statements were aborted by the transaction rollback.
