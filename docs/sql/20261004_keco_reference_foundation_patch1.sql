-- KECO Reference Foundation PATCH-001
-- Target DB: leg-prod (wrfcedzgdrfupenzqhur)
-- Schema: msds_ref
-- WO: CHEM-WO-DATA-KECO-002-PATCH-001
-- Applied: manually via Supabase MCP

-- P007: service_role minimum grants for msds_ref KECO tables
GRANT USAGE ON SCHEMA msds_ref TO service_role;

GRANT SELECT, INSERT, UPDATE
  ON msds_ref.keco_ingestion_runs
  TO service_role;

GRANT SELECT, INSERT, UPDATE
  ON msds_ref.keco_raw_records
  TO service_role;

GRANT SELECT, INSERT, UPDATE
  ON msds_ref.keco_chemicals
  TO service_role;

GRANT SELECT, INSERT, UPDATE
  ON msds_ref.keco_regulatory_facts
  TO service_role;

-- P009: source_record_id blank defense-in-depth constraints
ALTER TABLE msds_ref.keco_raw_records
  ADD CONSTRAINT keco_raw_records_source_record_id_nonempty
  CHECK (btrim(source_record_id) <> '');

ALTER TABLE msds_ref.keco_chemicals
  ADD CONSTRAINT keco_chemicals_source_record_id_nonempty
  CHECK (btrim(source_record_id) <> '');

-- P010: source_id constrained to KECO_15149420 only
ALTER TABLE msds_ref.keco_ingestion_runs
  ADD CONSTRAINT keco_ingestion_runs_source_id_check
  CHECK (source_id = 'KECO_15149420');
