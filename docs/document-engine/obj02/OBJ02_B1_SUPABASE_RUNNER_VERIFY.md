---
title: OBJ02-B1 Supabase Runner Verification (CORR-003)
description: Migration applied via supabase migration up --db-url. Positive + negative runner verification.
type: evidence
wo: WO-DOC-OBJ02-B1-FINAL-MIGRATION-CORR-003
status: VERIFIED_ALL_PASS
runner: supabase CLI v2.107.0
db_version: PostgreSQL 16.15 (aarch64-unknown-linux-musl, postgres:16-alpine)
---

# OBJ02-B1 Supabase Runner Verification

## Why Separate from Disposable DB Verify

The Disposable DB evidence (`OBJ02_B1_DISPOSABLE_DB_VERIFY.md`) used direct `psql -f` execution.
This file verifies via the **Supabase CLI migration runner** (`supabase migration up --db-url`),
which is the actual production apply path.

Key difference: the Supabase runner wraps each migration file in its own transaction.
This validates that:
1. No nested `BEGIN/COMMIT` error occurs (CORR-08)
2. Guard failures trigger a full transaction rollback via the runner
3. Migration version is recorded in `supabase_migrations.schema_migrations`

## Environment

- Runner: `supabase migration up --db-url "postgresql://postgres:testpw@127.0.0.1:<port>/tai_supa?sslmode=disable"`
- Container image: `postgres:16-alpine`
- Positive port: 15433
- Negative port: 15434
- Migration history pre-populated: all 53 prior migrations marked applied (only B1 was pending)

## Positive Test — port 15433

Fixture: 260 `document_forms` rows, 324 `runtime_form_schema` rows (260 doc_forms-sourced + 64 master-sourced)

Command:
```
supabase migration up --db-url "postgresql://postgres:testpw@127.0.0.1:15433/tai_supa?sslmode=disable"
```

Output:
```
Applying migration 20261006193021_catalog_schema_binding_b1.sql...
Applied migration 20261006193021_catalog_schema_binding_b1.sql
```

No `WARNING: there is already a transaction in progress` — confirms no nested BEGIN/COMMIT.

Post-apply verification:

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| NOT NULL count | 260 | 260 | PASS |
| NULL count | 64 | 64 | PASS |
| Dangling FK | 0 | 0 | PASS |
| Migration in history | 20261006193021 | present | PASS |

## Negative Test — port 15434 (PRE Guard)

Fixture: 1 `document_forms` row (not 260), 1 `runtime_form_schema` row

Command:
```
supabase migration up --db-url "postgresql://postgres:testpw@127.0.0.1:15434/tai_supa_neg?sslmode=disable"
```

Output:
```
Applying migration 20261006193021_catalog_schema_binding_b1.sql...
ERROR: PRE FAIL: document_forms count=1 expected 260 (SQLSTATE P0001)
```

Post-failure rollback verification:
```sql
SELECT COUNT(*) FROM information_schema.columns
WHERE table_schema='public'
  AND table_name='runtime_form_schema'
  AND column_name='catalog_document_id';
-- col_count = 0  ← column was NOT added (full rollback)
```

Result: `col_count = 0` — full transaction rollback confirmed.

## Transaction Atomicity Confirmation

The Supabase runner wraps each migration file in a transaction. When the PRE guard fired:
- All DDL statements after the guard (ADD COLUMN, UPDATE, FK, CHECK, INDEX) were aborted
- The `catalog_document_id` column was NOT created
- The migration version was NOT recorded in `schema_migrations`

This confirms CORR-08 is correct: no explicit `BEGIN/COMMIT` needed inside the migration file.

## CORR-08 Compliance

Migration file contains no standalone `BEGIN;` or `COMMIT;` statements.

```
grep -n "^BEGIN;\|^COMMIT;" supabase/migrations/20261006193021_catalog_schema_binding_b1.sql
# (no output — CLEAN)
```
