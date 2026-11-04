-- bizinfo_source_records + bizinfo_editorial_content
-- STORAGE_GATE: OBJ-BZI-004/005/006 DB 계층
--
-- 활성화 경로:
--   STORAGE_GATE Owner 승인 후 Supabase SQL Editor에서 직접 실행.
--   코드에서 자동 실행 금지.
--
-- 테이블 2개:
--   bizinfo_source_records       — 수집·정규화된 원천 공고 스냅샷
--   bizinfo_editorial_content    — TAI 해설 + 권리확인 + 공개승인

-- ---------------------------------------------------------------------------
-- 1. bizinfo_source_records
-- ---------------------------------------------------------------------------
-- 각 (source_kind, source_key) 쌍의 최신 스냅샷을 보관한다.
-- 중복 공고 방지: UPSERT on conflict (source_kind, source_key).
-- 과거 이력은 changed_fields / change_verdict 컬럼으로 추적한다.

CREATE TABLE IF NOT EXISTS public.bizinfo_source_records (
  id                  UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  source_kind         TEXT        NOT NULL CHECK (source_kind IN ('PROGRAM', 'EVENT')),
  source_key          TEXT        NOT NULL,
  title               TEXT        NOT NULL,
  source_org          TEXT,
  origin_url          TEXT,
  bizinfo_url         TEXT,
  retrieved_at        TIMESTAMPTZ NOT NULL,
  source_updated_at   TIMESTAMPTZ,
  summary             TEXT,
  support_target      TEXT,
  hashtags            TEXT[]      NOT NULL DEFAULT '{}',
  parse_errors        TEXT[]      NOT NULL DEFAULT '{}',
  evidence_pending    TEXT[]      NOT NULL DEFAULT '{}',

  -- DateRange 필드 (PROGRAM: application_*, EVENT: event_* + reception_*)
  application_start   DATE,
  application_end     DATE,
  event_start         DATE,
  event_end           DATE,
  reception_start     DATE,
  reception_end       DATE,

  -- 선별·분석기 판정
  relevance_verdict   TEXT,

  -- 변경 추적
  change_verdict      TEXT,
  changed_fields      TEXT[]      NOT NULL DEFAULT '{}',

  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT uq_bizinfo_source_records_kind_key UNIQUE (source_kind, source_key)
);

CREATE INDEX IF NOT EXISTS idx_bizinfo_source_records_kind
  ON public.bizinfo_source_records (source_kind);

CREATE INDEX IF NOT EXISTS idx_bizinfo_source_records_relevance
  ON public.bizinfo_source_records (source_kind, relevance_verdict);

-- ---------------------------------------------------------------------------
-- 2. bizinfo_editorial_content
-- ---------------------------------------------------------------------------
-- 하나의 행이 TAI 해설 + 권리확인 + 공개승인을 모두 담는다.
-- 세 레코드 유형을 단일 테이블로 관리해 JOIN 없이 공개 조건을 판정한다.
-- (rights_basis IS NOT NULL → rights 존재, approved_at IS NOT NULL → 승인 완료)

CREATE TABLE IF NOT EXISTS public.bizinfo_editorial_content (
  id                  UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  source_kind         TEXT        NOT NULL CHECK (source_kind IN ('PROGRAM', 'EVENT')),
  source_key          TEXT        NOT NULL,

  -- EditorialContent
  explanation         TEXT        NOT NULL,
  guidance            TEXT        NOT NULL,
  authored_at         TIMESTAMPTZ NOT NULL,
  tai_link            TEXT,

  -- RightsRecord (NULL = 미확인)
  rights_basis        TEXT,
  rights_confirmed_at TIMESTAMPTZ,
  rights_confirmed_by TEXT,

  -- ContentApprovalRecord (NULL = 미승인)
  approved_at         TIMESTAMPTZ,
  approved_by         TEXT,

  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT uq_bizinfo_editorial_kind_key UNIQUE (source_kind, source_key)
);

CREATE INDEX IF NOT EXISTS idx_bizinfo_editorial_approved
  ON public.bizinfo_editorial_content (source_kind, approved_at)
  WHERE approved_at IS NOT NULL;
