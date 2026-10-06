-- OBJ02-B1: Catalog Schema Binding
-- Adds catalog_document_id to runtime_form_schema as explicit relational binding.
-- Source_trace remains provenance/audit; this column is operational binding.
-- Production DB apply: NOT YET AUTHORIZED.

-- ============================================================
-- STEP 1: PRE-CONDITION ASSERTIONS
-- ============================================================
DO $check_pre$ BEGIN
  ASSERT (SELECT COUNT(*) FROM document_forms) = 260,
    'PRE: document_forms must have exactly 260 rows';

  ASSERT (SELECT COUNT(*) FROM runtime_form_schema
          WHERE source_trace->>'source_table' = 'document_forms') = 260,
    'PRE: runtime_form_schema must have 260 rows with source_table=document_forms';

  ASSERT (SELECT COUNT(*) FROM runtime_form_schema rfs
          JOIN document_forms df
            ON df.id::text = rfs.source_trace->>'source_id'
           AND df.doc_id   = rfs.source_trace->>'doc_id'
          WHERE rfs.source_trace->>'source_table' = 'document_forms') = 260,
    'PRE: all 260 document_forms-sourced schemas must have dual-condition exact match';

  ASSERT (SELECT COUNT(*) FROM (
    SELECT rfs.source_trace->>'doc_id' AS doc_id
    FROM runtime_form_schema rfs
    JOIN document_forms df
      ON df.id::text = rfs.source_trace->>'source_id'
     AND df.doc_id   = rfs.source_trace->>'doc_id'
    WHERE rfs.source_trace->>'source_table' = 'document_forms'
    GROUP BY rfs.source_trace->>'doc_id'
    HAVING COUNT(*) > 1
  ) dup) = 0,
    'PRE: no duplicate doc_id in document_forms-sourced schemas';

  ASSERT NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'runtime_form_schema'
      AND column_name = 'catalog_document_id'
  ), 'PRE: catalog_document_id must not already exist';
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
-- STEP 4: POST-BACKFILL ASSERTIONS
-- ============================================================
DO $check_post$ BEGIN
  ASSERT (SELECT COUNT(*) FROM runtime_form_schema
          WHERE catalog_document_id IS NOT NULL) = 260,
    'POST: exactly 260 rows must have catalog_document_id populated';

  ASSERT (SELECT COUNT(*) FROM runtime_form_schema
          WHERE catalog_document_id IS NULL) = 64,
    'POST: exactly 64 rows must have catalog_document_id NULL (document_form_master-derived)';

  ASSERT NOT EXISTS (
    SELECT 1 FROM runtime_form_schema rfs
    WHERE rfs.catalog_document_id IS NOT NULL
      AND NOT EXISTS (
        SELECT 1 FROM document_forms df WHERE df.id = rfs.catalog_document_id
      )
  ), 'POST: all non-NULL catalog_document_id must reference an existing document_forms row';

  ASSERT NOT EXISTS (
    SELECT 1 FROM runtime_form_schema
    WHERE catalog_document_id IS NOT NULL
      AND source_trace->>'source_table' != 'document_forms'
  ), 'POST: only document_forms-sourced schemas may have catalog_document_id set';
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
-- STEP 8: FINAL ASSERTION — no catalog doc has multiple active approved schemas
-- ============================================================
DO $check_final$ BEGIN
  ASSERT NOT EXISTS (
    SELECT catalog_document_id
    FROM runtime_form_schema
    WHERE status = 'APPROVED_FOR_RUNTIME_USE'
      AND catalog_document_id IS NOT NULL
    GROUP BY catalog_document_id
    HAVING COUNT(*) > 1
  ), 'FINAL: no catalog document may have more than one APPROVED_FOR_RUNTIME_USE schema';
END $check_final$;
