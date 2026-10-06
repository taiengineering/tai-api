---
title: OBJ02-B1 Migration Static + Disposable DB Verification
description: Migration guards verified statically and on disposable PostgreSQL 16
type: evidence
wo: WO-DOC-OBJ02-B1-CORRECTION-002
status: DISPOSABLE_DB_VERIFIED
db_version: PostgreSQL 16.15 (aarch64-unknown-linux-musl)
---

# OBJ02-B1 Migration Static + Disposable DB Verification

## Migration File

`supabase/migrations/20261006193021_catalog_schema_binding_b1.sql`

## Guard Mechanism (Post CORR-06)

All guards use `RAISE EXCEPTION` — NOT `ASSERT`.

Reason: PostgreSQL `ASSERT` is disabled by `plpgsql.check_asserts=off` (off by default in many environments). Guards must never be skippable.

Migration is wrapped in `BEGIN/COMMIT` so any guard failure causes full ROLLBACK.

## Structure (§21 Order Compliance)

| Step | Content | Mechanism |
|------|---------|-----------|
| 1 | PRE-CONDITION GUARDS | `DO ... RAISE EXCEPTION IF` |
| 2 | ADD COLUMN | `ALTER TABLE ADD COLUMN` |
| 3 | BACKFILL | `UPDATE ... FROM` |
| 4 | POST-BACKFILL GUARDS | `DO ... RAISE EXCEPTION IF` |
| 5 | FOREIGN KEY | `ADD CONSTRAINT ... REFERENCES ... ON DELETE RESTRICT` |
| 6 | CHECK CONSTRAINT | `ADD CONSTRAINT ... CHECK` |
| 7 | INDEXES + UNIQUE | `CREATE INDEX` × 3 |
| 8 | FINAL GUARD | `DO ... RAISE EXCEPTION IF` |

## Disposable DB — Positive Test (Production-like Fixture)

Environment: PostgreSQL 16 Docker container (`postgres:16-alpine`)

Fixture:
- `document_forms`: 260 rows
- `runtime_form_schema`: 324 rows (260 document_forms-sourced + 64 document_form_master-sourced)

Result:

| Check | Value | Status |
|-------|-------|--------|
| NOT NULL count | 260 | PASS |
| NULL count | 64 | PASS |
| Dangling FK | 0 | PASS |
| Kind conflict | 0 | PASS |

## Disposable DB — Negative Tests

| ID | Scenario | Expected | Result |
|----|----------|----------|--------|
| M1 | document_forms count = 1 (not 260) | PRE guard fires, full ROLLBACK | PASS |
| M2 | 1 dual-key mismatch (source_id match, doc_id wrong) | PRE guard fires at count=259, full ROLLBACK | PASS |
| M4 | catalog_document_id column pre-exists | PRE guard fires | PASS |
| M5 | source-kind CHECK: set catalog_document_id on master-sourced schema | `check_violation` raised | PASS |
| ACTIVE_UNIQUE | Second APPROVED schema for same catalog doc | `unique_violation` raised | PASS |
| VER_UNIQUE | Duplicate (catalog_document_id, version) | `unique_violation` raised | PASS |
| DELETE_RESTRICT | Delete document_forms row referenced by schema | `foreign_key_violation` raised | PASS |

## CORR-07: information_schema Qualification

```sql
WHERE table_schema = 'public'
  AND table_name   = 'runtime_form_schema'
  AND column_name  = 'catalog_document_id'
```

Prevents false-positives from same-named tables in non-public schemas.

## Production DB Apply Status

NOT APPLIED. Authorized by Owner only.
