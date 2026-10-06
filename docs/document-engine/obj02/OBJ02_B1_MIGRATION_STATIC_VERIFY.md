---
title: OBJ02-B1 Migration Static Verification
description: Static verification of migration logic without live DB execution
type: evidence
wo: WO-DOC-OBJ02-B1-CATALOG-SCHEMA-BINDING-001
status: VERIFIED_STATIC_ONLY
---

# OBJ02-B1 Migration Static Verification

## Migration File

`supabase/migrations/20261006193021_catalog_schema_binding_b1.sql`

## Structure (§21 Order Compliance)

| Step | Content | Present |
|------|---------|---------|
| 1 | PRE-CONDITION ASSERTIONS (DO $check_pre$) | YES |
| 2 | ADD COLUMN | YES |
| 3 | BACKFILL | YES |
| 4 | POST-BACKFILL ASSERTIONS (DO $check_post$) | YES |
| 5 | FOREIGN KEY | YES |
| 6 | CHECK CONSTRAINT | YES |
| 7 | INDEXES + UNIQUE CONSTRAINTS | YES |
| 8 | FINAL ASSERTION | YES |

## PRE-CONDITION ASSERTIONS

| Assertion | Expected | Notes |
|-----------|----------|-------|
| document_forms COUNT = 260 | 260 | Verified in OBJ02-A evidence |
| runtime_form_schema WHERE source_table=document_forms COUNT = 260 | 260 | Verified in OBJ02-A census |
| dual-condition JOIN (source_id AND doc_id) COUNT = 260 | 260 | Both columns must match |
| duplicate doc_id in sourced schemas = 0 | 0 | No doc_id appears in >1 schema |
| catalog_document_id column NOT EXISTS | NOT EXISTS | New column — must not pre-exist |

## BACKFILL LOGIC

```sql
UPDATE runtime_form_schema rfs SET catalog_document_id = df.id
FROM document_forms df
WHERE rfs.source_trace->>'source_table' = 'document_forms'
  AND rfs.source_trace->>'source_id'    = df.id::text
  AND rfs.source_trace->>'doc_id'       = df.doc_id;
```

Dual-condition design: Both `source_id = df.id` AND `doc_id = df.doc_id` must match.
No row is updated if either key mismatches. Fail-closed.

## POST-BACKFILL ASSERTIONS

| Assertion | Expected |
|-----------|----------|
| NOT NULL count = 260 | 260 document_forms-sourced schemas backfilled |
| NULL count = 64 | 64 document_form_master-sourced schemas untouched |
| All non-NULL reference valid document_forms.id | No dangling FK |
| Only source_table=document_forms may have non-NULL | Kind constraint |

## CONSTRAINTS

| Constraint | Type | Definition |
|------------|------|------------|
| fk_rfs_catalog_document | FK | catalog_document_id → document_forms(id) ON DELETE RESTRICT |
| chk_rfs_catalog_source_kind | CHECK | NULL OR source_table='document_forms' |
| uq_rfs_catalog_active_approved | UNIQUE INDEX | (catalog_document_id) WHERE APPROVED_FOR_RUNTIME_USE |
| uq_rfs_catalog_version | UNIQUE INDEX | (catalog_document_id, version) WHERE NOT NULL |
| idx_rfs_catalog_document_id | INDEX | (catalog_document_id) WHERE NOT NULL |

## Static Verification (Tests B1~B7)

All 7 migration static tests PASS. Test file: `tests/test_doc_obj02b1_binding.py`.

## Production DB Apply Status

NOT APPLIED. Authorized by Owner only.
