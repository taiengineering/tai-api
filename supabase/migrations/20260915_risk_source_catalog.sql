-- OBJ-RISK-02 source catalog / snapshot / identity core.
-- Additive. Production apply = 0 in this WO. No Graph, Legal Engine, CHEM, or SaaS objects.
-- MODEL D frozen: A/B/C remain separate sources. No TAI canonical process/task tables.

CREATE TABLE IF NOT EXISTS public.risk_sources (
  source_id text PRIMARY KEY
    CHECK (source_id IN (
      'CIC_W',
      'KOSHA_CONSTRUCTION_PROCESS',
      'KALIS_RISK_PROFILE'
    )),
  source_name text NOT NULL,
  provider text NOT NULL,
  official_url text NOT NULL,
  source_role text NOT NULL
    CHECK (source_role IN (
      'REFERENCE_CLASSIFICATION',
      'USEFUL_BRIDGE',
      'RISK_CONTEXT_SOURCE'
    )),
  rights_status text NOT NULL,
  customer_display_status text NOT NULL,
  redistribution_status text NOT NULL,
  attribution_required boolean NOT NULL DEFAULT true,
  current_policy text,
  version_policy text,
  active boolean NOT NULL DEFAULT true,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE public.risk_sources IS
  'RISK-01 MODEL D source catalog. source_id is the catalog key, not a TAI canonical id.';
COMMENT ON COLUMN public.risk_sources.source_role IS
  'Frozen RISK-01 roles. Do not promote any source to TAI process/task master.';

CREATE TABLE IF NOT EXISTS public.risk_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id text NOT NULL REFERENCES public.risk_sources (source_id),
  source_version text,
  source_filename text NOT NULL,
  source_url text,
  source_sha256 text NOT NULL,
  raw_row_count integer NOT NULL,
  unique_record_count integer NOT NULL,
  published_or_modified_date date,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL
    CHECK (status IN ('STAGED', 'VALIDATED', 'ACCEPTED', 'REJECTED')),
  UNIQUE (source_id, source_sha256)
);

COMMENT ON TABLE public.risk_snapshots IS
  'Source file/version snapshots. id is internal PK only. No PUBLISHED state in RISK-02.';
COMMENT ON COLUMN public.risk_snapshots.id IS
  'Internal UUID. Not source identity.';
COMMENT ON COLUMN public.risk_snapshots.published_or_modified_date IS
  'Official source calendar date from evidence. Not a runtime clock.';
COMMENT ON COLUMN public.risk_snapshots.metadata IS
  'Portal drift and census extras. Do not overwrite 41239/55546/47559 into one field.';

CREATE INDEX IF NOT EXISTS risk_snapshots_source_status_idx
  ON public.risk_snapshots (source_id, status);

CREATE TABLE IF NOT EXISTS public.risk_source_nodes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id text NOT NULL REFERENCES public.risk_sources (source_id),
  source_key text NOT NULL,
  parent_source_key text,
  native_code text,
  node_type text NOT NULL,
  depth integer NOT NULL CHECK (depth >= 1),
  name_raw text NOT NULL,
  name_normalized text NOT NULL,
  path_raw text NOT NULL,
  path_normalized text NOT NULL,
  content_hash text NOT NULL,
  attrs jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (source_id, source_key)
);

COMMENT ON TABLE public.risk_source_nodes IS
  'Native A/B/C taxonomy nodes. Hierarchies are not merged across sources.';
COMMENT ON COLUMN public.risk_source_nodes.id IS
  'Internal UUID. Not source_key.';
COMMENT ON COLUMN public.risk_source_nodes.source_key IS
  'A = native W code. B/C = deterministic normalized path hash. Never a row number.';
COMMENT ON COLUMN public.risk_source_nodes.native_code IS
  'Present for CIC_W. NULL for KOSHA/KALIS name-path nodes.';

CREATE INDEX IF NOT EXISTS risk_source_nodes_parent_idx
  ON public.risk_source_nodes (source_id, parent_source_key);
CREATE INDEX IF NOT EXISTS risk_source_nodes_type_idx
  ON public.risk_source_nodes (source_id, node_type);

CREATE TABLE IF NOT EXISTS public.risk_records (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id text NOT NULL
    REFERENCES public.risk_sources (source_id)
    CHECK (source_id = 'KALIS_RISK_PROFILE'),
  content_key text NOT NULL,
  task_source_key text NOT NULL,
  raw_payload jsonb NOT NULL,
  facility_big text,
  facility_mid text,
  facility_small text,
  work_big text,
  work_mid text,
  task text,
  hazard_object_big text,
  hazard_object_mid text,
  hazard_location_big text,
  hazard_location_mid_code text,
  hazard_location_mid text,
  hazard_location_small text,
  cause text,
  human_damage text,
  property_damage text,
  likelihood text,
  severity text,
  design_control text,
  construction_control text,
  UNIQUE (source_id, content_key)
);

COMMENT ON TABLE public.risk_records IS
  'KALIS risk-profile content entities. One row per unique 19-field tuple. Not 47559 fake IDs.';
COMMENT ON COLUMN public.risk_records.id IS
  'Internal UUID. Not content identity.';
COMMENT ON COLUMN public.risk_records.content_key IS
  'SHA256 of canonical 19 source fields. Excludes UUID, row number, timestamps.';
COMMENT ON COLUMN public.risk_records.raw_payload IS
  'Lossless 19-field object. Derived columns must not replace it.';
COMMENT ON COLUMN public.risk_records.task_source_key IS
  'Native KALIS task node source_key. Not a TAI canonical task id.';
COMMENT ON COLUMN public.risk_records.likelihood IS
  'Source-native 사고가능성. Not a TAI legal risk score.';
COMMENT ON COLUMN public.risk_records.severity IS
  'Source-native 사고심각성. Not a TAI legal risk score.';

CREATE INDEX IF NOT EXISTS risk_records_task_idx
  ON public.risk_records (source_id, task_source_key);

CREATE TABLE IF NOT EXISTS public.risk_snapshot_memberships (
  snapshot_id uuid NOT NULL REFERENCES public.risk_snapshots (id),
  member_kind text NOT NULL CHECK (member_kind IN ('NODE', 'RECORD')),
  source_id text NOT NULL REFERENCES public.risk_sources (source_id),
  member_key text NOT NULL,
  occurrence_count integer NOT NULL CHECK (occurrence_count >= 1),
  PRIMARY KEY (snapshot_id, member_kind, source_id, member_key)
);

COMMENT ON TABLE public.risk_snapshot_memberships IS
  'Snapshot membership with occurrence preservation. Duplicates are counted, not deleted.';
COMMENT ON COLUMN public.risk_snapshot_memberships.member_key IS
  'NODE = source_key. RECORD = content_key.';
COMMENT ON COLUMN public.risk_snapshot_memberships.occurrence_count IS
  'Source occurrence N for one knowledge entity. SUM(RECORD) must equal raw_row_count.';

CREATE INDEX IF NOT EXISTS risk_snapshot_memberships_member_idx
  ON public.risk_snapshot_memberships (source_id, member_kind, member_key);

CREATE OR REPLACE VIEW public.risk_accepted_snapshots AS
SELECT DISTINCT ON (s.source_id)
  s.id,
  s.source_id,
  s.source_version,
  s.source_filename,
  s.source_sha256,
  s.raw_row_count,
  s.unique_record_count,
  s.published_or_modified_date,
  s.metadata,
  s.status
FROM public.risk_snapshots s
WHERE s.status = 'ACCEPTED'
ORDER BY s.source_id, s.published_or_modified_date DESC NULLS LAST, s.source_sha256 DESC;

COMMENT ON VIEW public.risk_accepted_snapshots IS
  'Current pointer = latest ACCEPTED snapshot per source. Historical snapshots remain in risk_snapshots. No PUBLISHED state.';

ALTER TABLE public.risk_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.risk_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.risk_source_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.risk_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.risk_snapshot_memberships ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.risk_sources FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.risk_snapshots FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.risk_source_nodes FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.risk_records FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.risk_snapshot_memberships FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.risk_accepted_snapshots FROM PUBLIC, anon, authenticated;

GRANT SELECT, INSERT, UPDATE ON public.risk_sources TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.risk_snapshots TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.risk_source_nodes TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.risk_records TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.risk_snapshot_memberships TO service_role;
GRANT SELECT ON public.risk_accepted_snapshots TO service_role;

REVOKE DELETE, TRUNCATE ON public.risk_sources FROM service_role;
REVOKE DELETE, TRUNCATE ON public.risk_snapshots FROM service_role;
REVOKE DELETE, TRUNCATE ON public.risk_source_nodes FROM service_role;
REVOKE DELETE, TRUNCATE ON public.risk_records FROM service_role;
REVOKE DELETE, TRUNCATE ON public.risk_snapshot_memberships FROM service_role;

INSERT INTO public.risk_sources (
  source_id, source_name, provider, official_url, source_role,
  rights_status, customer_display_status, redistribution_status, attribution_required,
  current_policy, version_policy, active, metadata
) VALUES
  (
    'CIC_W',
    '건설정보분류체계 공종분류(W)',
    '국토교통부 / 한국건설기술연구원 CALSPIA',
    'https://www.calspia.go.kr/portal/intro/introStandard04.do',
    'REFERENCE_CLASSIFICATION',
    'CONDITIONAL',
    'CONDITIONAL',
    'CONDITIONAL',
    true,
    '별표 PDF snapshot',
    '고시/지침 개정',
    true,
    '{"model_d":"REFERENCE_CLASSIFICATION"}'::jsonb
  ),
  (
    'KOSHA_CONSTRUCTION_PROCESS',
    '한국산업안전보건공단_건설업 공종별 세부공정 목록',
    '한국산업안전보건공단',
    'https://www.data.go.kr/data/15087828/fileData.do',
    'USEFUL_BRIDGE',
    'CLEAR',
    'CONDITIONAL',
    'CONDITIONAL',
    true,
    'latest accepted official CSV = 20210910 filename',
    '수시(1회성)',
    true,
    '{"dataset_id":"15087828","model_d":"USEFUL_BRIDGE"}'::jsonb
  ),
  (
    'KALIS_RISK_PROFILE',
    '국토안전관리원_위험요소프로파일',
    '국토안전관리원',
    'https://www.data.go.kr/data/15090644/fileData.do',
    'RISK_CONTEXT_SOURCE',
    'CLEAR',
    'CONDITIONAL',
    'CONDITIONAL',
    true,
    'latest accepted official file = _20260814',
    '연간 파일 스냅샷',
    true,
    '{"dataset_id":"15090644","model_d":"RISK_CONTEXT_SOURCE"}'::jsonb
  )
ON CONFLICT (source_id) DO NOTHING;
