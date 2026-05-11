-- ============================================================================
-- Migration: Inbox System Phase 1 — inquiries 확장
-- Date: 2026-05-04
-- Purpose:
--   1. inquiries 테이블이 없으면 생성 (어드민 inquiry-list가 아직 mock인 상태)
--   2. source / inquiry_type 컬럼 추가 (외부 채널 통합 + TAI에 바란다 분류)
--   3. anon role의 외부 INSERT만 허용하는 RLS 정책
--   4. inquiry-list 페이지 정상 작동 보장 (service_role은 RLS 무시)
--
-- Apply:
--   Supabase Studio (https://supabase.com/dashboard) → SQL Editor → Run
--   project: vwlahtguyggrhvslabax (서울)
--
-- Safety: BEGIN/COMMIT 트랜잭션 — 중간 실패 시 자동 롤백
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. inquiries 테이블 (없으면 생성)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS inquiries (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  -- 인간이 읽는 번호 (예: TAI-INQ-20260504-0001) — 트리거 또는 앱 레벨에서 채움
  no              text,

  -- 분류 — 채널마다 의미가 다름
  -- INQUIRY  : consult / safety / electric / risk / csia / saas / repair / edu / partner / other
  -- FEEDBACK : fb_feature / fb_bug / fb_ux / fb_idea / fb_praise
  category        text,

  -- 본문
  title           text,
  content         text NOT NULL,
  answer          text,            -- 어드민 답변 본문

  -- 보낸이 (비회원도 가능)
  name            text,
  company         text,
  phone           text,
  email           text,
  is_member       boolean DEFAULT false,

  -- 회원 컨텍스트 (있을 때만 채움)
  user_id         uuid,
  company_id      uuid,

  -- 처리 상태
  status          text DEFAULT 'RECEIVED',
    -- RECEIVED / IN_PROGRESS / ANSWERED / CLOSED
  priority        text DEFAULT 'NORMAL',
    -- HIGH / NORMAL / LOW
  assigned        text,            -- 담당자명 (추후 user_id로 마이그레이션 가능)

  -- 신규: 채널 통합용 컬럼
  source          text DEFAULT 'direct',
    -- direct (어드민 직접 입력) / marketing (taieng.co.kr) / safe (safe.taieng.co.kr)
  inquiry_type    text DEFAULT 'INQUIRY',
    -- INQUIRY (도입 문의) / FEEDBACK (TAI에 바란다)

  -- 컨텍스트 / 스팸 방지
  page_url        text,            -- 어느 페이지에서 보냈나
  ip_hash         text,            -- IP 해시 (rate limit용, 평문 저장 X)

  -- 타임스탬프
  replied_at      timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- 2. 기존 테이블이 이미 있는 경우 — 컬럼 누락분 추가 (IF NOT EXISTS)
-- ----------------------------------------------------------------------------
ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS source       text DEFAULT 'direct';
ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS inquiry_type text DEFAULT 'INQUIRY';
ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS page_url     text;
ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ip_hash      text;
ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS user_id      uuid;
ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS company_id   uuid;
ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS replied_at   timestamptz;
ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS updated_at   timestamptz NOT NULL DEFAULT now();

-- ----------------------------------------------------------------------------
-- 3. CHECK 제약 (이미 있으면 스킵)
-- ----------------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'inquiries_source_chk') THEN
    ALTER TABLE inquiries ADD CONSTRAINT inquiries_source_chk
      CHECK (source IN ('direct','marketing','safe'));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'inquiries_type_chk') THEN
    ALTER TABLE inquiries ADD CONSTRAINT inquiries_type_chk
      CHECK (inquiry_type IN ('INQUIRY','FEEDBACK'));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'inquiries_status_chk') THEN
    ALTER TABLE inquiries ADD CONSTRAINT inquiries_status_chk
      CHECK (status IN ('RECEIVED','IN_PROGRESS','ANSWERED','CLOSED'));
  END IF;
END $$;

-- ----------------------------------------------------------------------------
-- 4. 기존 row 마이그레이션 (NULL인 것만)
-- ----------------------------------------------------------------------------
UPDATE inquiries
   SET source       = COALESCE(source, 'direct'),
       inquiry_type = COALESCE(inquiry_type, 'INQUIRY')
 WHERE source IS NULL OR inquiry_type IS NULL;

-- ----------------------------------------------------------------------------
-- 5. 인덱스 (필터 성능)
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_inquiries_source            ON inquiries(source);
CREATE INDEX IF NOT EXISTS idx_inquiries_type              ON inquiries(inquiry_type);
CREATE INDEX IF NOT EXISTS idx_inquiries_status            ON inquiries(status);
CREATE INDEX IF NOT EXISTS idx_inquiries_category          ON inquiries(category);
CREATE INDEX IF NOT EXISTS idx_inquiries_created_at_desc   ON inquiries(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_inquiries_user_id           ON inquiries(user_id) WHERE user_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 6. updated_at 자동 갱신 트리거
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_inquiries_updated_at ON inquiries;
CREATE TRIGGER trg_inquiries_updated_at
BEFORE UPDATE ON inquiries
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- ----------------------------------------------------------------------------
-- 7. RLS — anon은 외부 INSERT만 허용
-- ----------------------------------------------------------------------------
ALTER TABLE inquiries ENABLE ROW LEVEL SECURITY;

-- 기존 정책이 있다면 제거
DROP POLICY IF EXISTS "anon insert external inquiries" ON inquiries;

CREATE POLICY "anon insert external inquiries"
ON inquiries FOR INSERT TO anon
WITH CHECK (
  source IN ('marketing','safe')
  AND content IS NOT NULL
  AND length(content) BETWEEN 10 AND 2000
  AND inquiry_type IN ('INQUIRY','FEEDBACK')
);

-- anon SELECT/UPDATE/DELETE 정책 없음 → 자동 차단
-- service_role(서버·어드민)은 RLS 무시 → inquiry-list 페이지 정상 작동

COMMIT;

-- ============================================================================
-- 검증 쿼리 (위 마이그레이션 적용 후 실행해서 결과 확인)
-- ============================================================================

-- 7-1. 컬럼 확인
-- SELECT column_name, data_type, column_default, is_nullable
--   FROM information_schema.columns
--  WHERE table_name = 'inquiries'
--  ORDER BY ordinal_position;

-- 7-2. row 분포 확인
-- SELECT
--   count(*) as total,
--   count(*) FILTER (WHERE source='direct')          as direct_count,
--   count(*) FILTER (WHERE source='marketing')       as marketing_count,
--   count(*) FILTER (WHERE source='safe')            as safe_count,
--   count(*) FILTER (WHERE inquiry_type='INQUIRY')   as inquiry_count,
--   count(*) FILTER (WHERE inquiry_type='FEEDBACK')  as feedback_count
-- FROM inquiries;

-- 7-3. RLS 정책 확인
-- SELECT policyname, cmd, roles
--   FROM pg_policies
--  WHERE tablename = 'inquiries';

-- 7-4. 인덱스 확인
-- SELECT indexname, indexdef
--   FROM pg_indexes
--  WHERE tablename = 'inquiries'
--  ORDER BY indexname;

-- 7-5. anon 정책 시뮬레이션 — 실패해야 정상 (source=direct 차단)
-- SET LOCAL ROLE anon;
-- INSERT INTO inquiries (source, inquiry_type, category, content)
--   VALUES ('direct', 'FEEDBACK', 'fb_feature', '이건 차단되어야 정상입니다');
-- -- 결과: "new row violates row-level security policy" → ✅
-- RESET ROLE;

-- 7-6. anon 정책 시뮬레이션 — 성공해야 정상 (source=marketing 통과)
-- SET LOCAL ROLE anon;
-- INSERT INTO inquiries (source, inquiry_type, category, content)
--   VALUES ('marketing', 'FEEDBACK', 'fb_feature', '의견 테스트 — 길이 10자 이상이어야 통과합니다');
-- -- 결과: row 1개 INSERT 됨 → ✅
-- RESET ROLE;
-- DELETE FROM inquiries WHERE content LIKE '의견 테스트%';  -- 정리
