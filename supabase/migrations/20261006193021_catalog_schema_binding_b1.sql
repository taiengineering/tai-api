-- OBJ02-B1: Catalog Schema Binding (CORR-06/07)
-- Adds catalog_document_id to runtime_form_schema as explicit relational binding.
-- Source_trace remains provenance/audit; this column is operational binding.
-- Production DB apply: NOT YET AUTHORIZED.
--
-- CORR-06: All guards use RAISE EXCEPTION (not ASSERT — ASSERT can be disabled
--          via plpgsql.check_asserts=off, making guards silently skip).
-- CORR-07: information_schema queries qualify table_schema = 'public' to avoid
--          false-positives from same-named tables in other schemas.
--
-- TRANSACTION WRAPPER: ensures any guard failure rolls back all DDL atomically.
BEGIN;

-- ============================================================
-- STEP 1: PRE-CONDITION GUARDS
-- ============================================================
DO $check_pre$ DECLARE
  v_count bigint;
  v_dup   bigint;
BEGIN
  SELECT COUNT(*) INTO v_count FROM document_forms;
  IF v_count != 260 THEN
    RAISE EXCEPTION 'PRE FAIL: document_forms count=% expected 260', v_count;
  END IF;

  SELECT COUNT(*) INTO v_count
  FROM runtime_form_schema
  WHERE source_trace->>'source_table' = 'document_forms';
  IF v_count != 260 THEN
    RAISE EXCEPTION 'PRE FAIL: runtime_form_schema document_forms-sourced count=% expected 260', v_count;
  END IF;

  SELECT COUNT(*) INTO v_count
  FROM runtime_form_schema rfs
  JOIN document_forms df
    ON df.id::text = rfs.source_trace->>'source_id'
   AND df.doc_id   = rfs.source_trace->>'doc_id'
  WHERE rfs.source_trace->>'source_table' = 'document_forms';
  IF v_count != 260 THEN
    RAISE EXCEPTION 'PRE FAIL: dual-condition match count=% expected 260', v_count;
  END IF;

  SELECT COUNT(*) INTO v_dup FROM (
    SELECT rfs.source_trace->>'doc_id' AS doc_id
    FROM runtime_form_schema rfs
    JOIN document_forms df
      ON df.id::text = rfs.source_trace->>'source_id'
     AND df.doc_id   = rfs.source_trace->>'doc_id'
    WHERE rfs.source_trace->>'source_table' = 'document_forms'
    GROUP BY rfs.source_trace->>'doc_id'
    HAVING COUNT(*) > 1
  ) dup;
  IF v_dup != 0 THEN
    RAISE EXCEPTION 'PRE FAIL: duplicate doc_id count=% expected 0', v_dup;
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name   = 'runtime_form_schema'
      AND column_name  = 'catalog_document_id'
  ) THEN
    RAISE EXCEPTION 'PRE FAIL: catalog_document_id already exists on runtime_form_schema';
  END IF;
END $check_pre$;

-- ============================================================
-- STEP 2: ADD COLUMN
-- ============================================================
ALTER TABLE runtime_form_schema
  ADD COLUMN catalog_document_id UUID NULL;

-- ============================================================
-- STEP 3: BACKFILL (dual-condition: source_id AND doc_id)
-- ============================================================
UPDATE runtime_form_schema rfs
SET catalog_document_id = df.id
FROM document_forms df
WHERE rfs.source_trace->>'source_table' = 'document_forms'
  AND rfs.source_trace->>'source_id'    = df.id::text
  AND rfs.source_trace->>'doc_id'       = df.doc_id;

-- ============================================================
-- STEP 4: POST-BACKFILL GUARDS
-- ============================================================
DO $check_post$ DECLARE
  v_count bigint;
BEGIN
  SELECT COUNT(*) INTO v_count
  FROM runtime_form_schema WHERE catalog_document_id IS NOT NULL;
  IF v_count != 260 THEN
    RAISE EXCEPTION 'POST FAIL: non-null catalog_document_id count=% expected 260', v_count;
  END IF;

  SELECT COUNT(*) INTO v_count
  FROM runtime_form_schema WHERE catalog_document_id IS NULL;
  IF v_count != 64 THEN
    RAISE EXCEPTION 'POST FAIL: null catalog_document_id count=% expected 64', v_count;
  END IF;

  IF EXISTS (
    SELECT 1 FROM runtime_form_schema rfs
    WHERE rfs.catalog_document_id IS NOT NULL
      AND NOT EXISTS (
        SELECT 1 FROM document_forms df WHERE df.id = rfs.catalog_document_id
      )
  ) THEN
    RAISE EXCEPTION 'POST FAIL: dangling catalog_document_id found (no matching document_forms row)';
  END IF;

  IF EXISTS (
    SELECT 1 FROM runtime_form_schema
    WHERE catalog_document_id IS NOT NULL
      AND source_trace->>'source_table' != 'document_forms'
  ) THEN
    RAISE EXCEPTION 'POST FAIL: catalog_document_id set on non-document_forms-sourced schema';
  END IF;
END $check_post$;

-- ============================================================
-- STEP 5: FOREIGN KEY
-- ============================================================
ALTER TABLE runtime_form_schema
  ADD CONSTRAINT fk_rfs_catalog_document
    FOREIGN KEY (catalog_document_id)
    REFERENCES document_forms(id)
    ON DELETE RESTRICT;

-- ============================================================
-- STEP 6: CHECK CONSTRAINT
-- ============================================================
ALTER TABLE runtime_form_schema
  ADD CONSTRAINT chk_rfs_catalog_source_kind
    CHECK (
      catalog_document_id IS NULL
      OR source_trace->>'source_table' = 'document_forms'
    );

-- ============================================================
-- STEP 7: INDEXES AND UNIQUE CONSTRAINTS
-- ============================================================

-- (a) Lookup index
CREATE INDEX idx_rfs_catalog_document_id
  ON runtime_form_schema (catalog_document_id)
  WHERE catalog_document_id IS NOT NULL;

-- (b) One approved schema per catalog doc (prevents duplicate active schemas)
CREATE UNIQUE INDEX uq_rfs_catalog_active_approved
  ON runtime_form_schema (catalog_document_id)
  WHERE status = 'APPROVED_FOR_RUNTIME_USE'
    AND catalog_document_id IS NOT NULL;

-- (c) Version uniqueness per catalog doc (allows history/versioning)
CREATE UNIQUE INDEX uq_rfs_catalog_version
  ON runtime_form_schema (catalog_document_id, version)
  WHERE catalog_document_id IS NOT NULL;

-- ============================================================
-- STEP 8: FINAL GUARD — no catalog doc has multiple active approved schemas
-- ============================================================
DO $check_final$ BEGIN
  IF EXISTS (
    SELECT catalog_document_id
    FROM runtime_form_schema
    WHERE status = 'APPROVED_FOR_RUNTIME_USE'
      AND catalog_document_id IS NOT NULL
    GROUP BY catalog_document_id
    HAVING COUNT(*) > 1
  ) THEN
    RAISE EXCEPTION 'FINAL FAIL: multiple APPROVED_FOR_RUNTIME_USE schemas share same catalog_document_id';
  END IF;
END $check_final$;

COMMIT;
