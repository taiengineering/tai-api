-- KECO Reference Foundation Migration
-- Target DB: leg-prod (wrfcedzgdrfupenzqhur)
-- Schema: msds_ref
-- Applied: manually via Supabase MCP or CLI
-- WO: CHEM-WO-DATA-KECO-002

-- Ensure msds_ref schema exists (idempotent)
CREATE SCHEMA IF NOT EXISTS msds_ref;

-- A. Ingestion runs
CREATE TABLE IF NOT EXISTS msds_ref.keco_ingestion_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id text NOT NULL DEFAULT 'KECO_15149420',
  run_type text NOT NULL,
  status text NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED', 'PARTIAL')),
  search_gubun text,
  search_nm text,
  request_count integer NOT NULL DEFAULT 0,
  record_count integer NOT NULL DEFAULT 0,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  source_contract_version text NOT NULL,
  error_code text,
  error_message text,
  metrics_json jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE msds_ref.keco_ingestion_runs IS 'KECO 15149420 ingestion run metadata. No serviceKey stored.';
CREATE INDEX IF NOT EXISTS idx_keco_ingestion_runs_status ON msds_ref.keco_ingestion_runs(status);
CREATE INDEX IF NOT EXISTS idx_keco_ingestion_runs_source ON msds_ref.keco_ingestion_runs(source_id);

-- B. Raw records
CREATE TABLE IF NOT EXISTS msds_ref.keco_raw_records (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_record_id text NOT NULL,
  raw_payload jsonb NOT NULL,
  payload_hash text NOT NULL,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  last_changed_at timestamptz NOT NULL DEFAULT now(),
  first_seen_run_id uuid REFERENCES msds_ref.keco_ingestion_runs(id),
  last_seen_run_id uuid REFERENCES msds_ref.keco_ingestion_runs(id),
  UNIQUE (source_record_id, payload_hash)
);
COMMENT ON TABLE msds_ref.keco_raw_records IS 'KECO source item JSON lossless preservation. source_record_id=sbstnId.';
CREATE INDEX IF NOT EXISTS idx_keco_raw_records_source_record ON msds_ref.keco_raw_records(source_record_id);
CREATE INDEX IF NOT EXISTS idx_keco_raw_records_hash ON msds_ref.keco_raw_records(payload_hash);

-- C. Chemicals
CREATE TABLE IF NOT EXISTS msds_ref.keco_chemicals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_record_id text NOT NULL UNIQUE,
  cas_no text,
  korexst_raw text,
  chemical_name_ko text,
  chemical_name_en text,
  alias_name_ko text,
  alias_name_en text,
  molecular_formula text,
  molecular_weight_raw text,
  source_content_hash text NOT NULL,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  last_changed_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE msds_ref.keco_chemicals IS 'KECO normalized chemical identity. source_record_id=sbstnId. korexst_raw preserved as-is.';
COMMENT ON COLUMN msds_ref.keco_chemicals.korexst_raw IS '기존화학물질번호 원문. KE번호 확정 이전에는 변환하지 않음.';
CREATE INDEX IF NOT EXISTS idx_keco_chemicals_cas ON msds_ref.keco_chemicals(cas_no);
CREATE INDEX IF NOT EXISTS idx_keco_chemicals_korexst ON msds_ref.keco_chemicals(korexst_raw);
CREATE INDEX IF NOT EXISTS idx_keco_chemicals_name_ko ON msds_ref.keco_chemicals(chemical_name_ko);
CREATE INDEX IF NOT EXISTS idx_keco_chemicals_name_en ON msds_ref.keco_chemicals(chemical_name_en);

-- D. Regulatory facts
CREATE TABLE IF NOT EXISTS msds_ref.keco_regulatory_facts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  keco_chemical_id uuid NOT NULL REFERENCES msds_ref.keco_chemicals(id) ON DELETE RESTRICT,
  classification_type text,
  unique_no text,
  content_info text,
  exception_info text,
  notice_date_raw text,
  notice_info text,
  fact_hash text NOT NULL,
  source_ordinal integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (keco_chemical_id, fact_hash)
);
COMMENT ON TABLE msds_ref.keco_regulatory_facts IS 'KECO typeList[] normalized. 1 chemical : N facts.';
CREATE INDEX IF NOT EXISTS idx_keco_facts_chemical ON msds_ref.keco_regulatory_facts(keco_chemical_id);
CREATE INDEX IF NOT EXISTS idx_keco_facts_unique_no ON msds_ref.keco_regulatory_facts(unique_no);

-- RLS
ALTER TABLE msds_ref.keco_ingestion_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE msds_ref.keco_raw_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE msds_ref.keco_chemicals ENABLE ROW LEVEL SECURITY;
ALTER TABLE msds_ref.keco_regulatory_facts ENABLE ROW LEVEL SECURITY;
-- No public/anon policies — internal server access only
