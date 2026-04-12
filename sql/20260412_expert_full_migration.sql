-- ============================================================
-- TAI API — 전문가 등록 전체 DB 마이그레이션
-- 작성일: 2026-04-12
-- ============================================================

-- ── 1-A. expert_applications 누락 컬럼 추가 ───────────────

ALTER TABLE expert_applications

  -- 사업자 구분
  ADD COLUMN IF NOT EXISTS entity_type          text,

  -- 사업자 정보
  ADD COLUMN IF NOT EXISTS biz_ceo_name         text,
  ADD COLUMN IF NOT EXISTS biz_type             text,
  ADD COLUMN IF NOT EXISTS biz_item             text,
  ADD COLUMN IF NOT EXISTS biz_open_date        date,
  ADD COLUMN IF NOT EXISTS biz_address          text,
  ADD COLUMN IF NOT EXISTS biz_zipcode          text,
  ADD COLUMN IF NOT EXISTS biz_verify_status    text,   -- VALID / CLOSED / SUSPENDED / UNVERIFIED
  ADD COLUMN IF NOT EXISTS biz_verify_at        timestamp,
  ADD COLUMN IF NOT EXISTS biz_verify_raw       jsonb,

  -- 법인 전용
  ADD COLUMN IF NOT EXISTS corp_number          text,
  ADD COLUMN IF NOT EXISTS corp_established_at  date,

  -- 자격증 (선임/컨설팅)
  ADD COLUMN IF NOT EXISTS license_type         text,
  ADD COLUMN IF NOT EXISTS license_number       text,
  ADD COLUMN IF NOT EXISTS license_issued_at    date,
  ADD COLUMN IF NOT EXISTS license_issuer       text,

  -- 인허가 (수선)
  ADD COLUMN IF NOT EXISTS permit_type          text,
  ADD COLUMN IF NOT EXISTS permit_number        text,
  ADD COLUMN IF NOT EXISTS permit_doc_number    text,

  -- 활동 정보
  ADD COLUMN IF NOT EXISTS expert_fields        jsonb,
  ADD COLUMN IF NOT EXISTS career_summary       text,
  ADD COLUMN IF NOT EXISTS career_years         int,

  -- 선임 전용: 근무형태
  ADD COLUMN IF NOT EXISTS work_types           jsonb,
  ADD COLUMN IF NOT EXISTS employment_type      text,
  ADD COLUMN IF NOT EXISTS immediate_join       text,
  ADD COLUMN IF NOT EXISTS salary_min           int,
  ADD COLUMN IF NOT EXISTS salary_max           int,
  ADD COLUMN IF NOT EXISTS visit_per_month      int,
  ADD COLUMN IF NOT EXISTS remote_support       text,
  ADD COLUMN IF NOT EXISTS visit_price          int,

  -- 검토 상태 고도화
  ADD COLUMN IF NOT EXISTS ai_review_result     jsonb,
  ADD COLUMN IF NOT EXISTS ai_review_at         timestamp,
  ADD COLUMN IF NOT EXISTS reject_reason        text,
  ADD COLUMN IF NOT EXISTS approved_at          timestamp,
  ADD COLUMN IF NOT EXISTS trust_level          int DEFAULT 0,

  -- 법적 동의
  ADD COLUMN IF NOT EXISTS legal_terms_agreed    boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS legal_terms_agreed_at timestamp;

-- status 가능값: PENDING / AI_REVIEWING / REVIEWING / APPROVED / REJECTED


-- ── 1-B. safety_personnel 연결 컬럼 추가 ──────────────────

ALTER TABLE safety_personnel
  ADD COLUMN IF NOT EXISTS user_id          uuid REFERENCES users(id),
  ADD COLUMN IF NOT EXISTS application_id   uuid REFERENCES expert_applications(id),
  ADD COLUMN IF NOT EXISTS entity_type      text,
  ADD COLUMN IF NOT EXISTS work_types       jsonb,
  ADD COLUMN IF NOT EXISTS employment_type  text,
  ADD COLUMN IF NOT EXISTS immediate_join   text,
  ADD COLUMN IF NOT EXISTS salary_min       int,
  ADD COLUMN IF NOT EXISTS salary_max       int,
  ADD COLUMN IF NOT EXISTS visit_per_month  int,
  ADD COLUMN IF NOT EXISTS remote_support   text,
  ADD COLUMN IF NOT EXISTS visit_price      int,
  ADD COLUMN IF NOT EXISTS expert_type      text,
  ADD COLUMN IF NOT EXISTS biz_number       text,
  ADD COLUMN IF NOT EXISTS biz_name         text;

CREATE INDEX IF NOT EXISTS idx_safety_personnel_user_id        ON safety_personnel(user_id);
CREATE INDEX IF NOT EXISTS idx_safety_personnel_application_id ON safety_personnel(application_id);


-- ── 1-C. safety_agencies 연결 컬럼 추가 ───────────────────

ALTER TABLE safety_agencies
  ADD COLUMN IF NOT EXISTS user_id          uuid REFERENCES users(id),
  ADD COLUMN IF NOT EXISTS application_id   uuid REFERENCES expert_applications(id),
  ADD COLUMN IF NOT EXISTS entity_type      text,
  ADD COLUMN IF NOT EXISTS expert_type      text,
  ADD COLUMN IF NOT EXISTS corp_number      text,
  ADD COLUMN IF NOT EXISTS expert_fields    jsonb;

CREATE INDEX IF NOT EXISTS idx_safety_agencies_user_id        ON safety_agencies(user_id);
CREATE INDEX IF NOT EXISTS idx_safety_agencies_application_id ON safety_agencies(application_id);


-- ── 1-D. repair_companies 연결 컬럼 추가 ──────────────────

ALTER TABLE repair_companies
  ADD COLUMN IF NOT EXISTS user_id           uuid REFERENCES users(id),
  ADD COLUMN IF NOT EXISTS application_id    uuid REFERENCES expert_applications(id),
  ADD COLUMN IF NOT EXISTS entity_type       text,
  ADD COLUMN IF NOT EXISTS permit_type       text,
  ADD COLUMN IF NOT EXISTS permit_number     text,
  ADD COLUMN IF NOT EXISTS permit_doc_number text,
  ADD COLUMN IF NOT EXISTS expert_fields     jsonb,
  ADD COLUMN IF NOT EXISTS biz_type          text,
  ADD COLUMN IF NOT EXISTS biz_item          text;

CREATE INDEX IF NOT EXISTS idx_repair_companies_user_id        ON repair_companies(user_id);
CREATE INDEX IF NOT EXISTS idx_repair_companies_application_id ON repair_companies(application_id);


-- ── 2. system_codes 등록 ──────────────────────────────────

INSERT INTO system_codes (category, category_name, code, code_name, sort_order, is_active)
VALUES
  -- 전문가 유형
  ('expert_type','전문가유형','EXPERT',     '선임대행', 1, true),
  ('expert_type','전문가유형','CONSULTING', '컨설팅',   2, true),
  ('expert_type','전문가유형','REPAIR',     '수선중개', 3, true),

  -- 사업자 구분
  ('entity_type','사업자구분','INDIVIDUAL',      '개인',       1, true),
  ('entity_type','사업자구분','SOLE_PROPRIETOR', '개인사업자', 2, true),
  ('entity_type','사업자구분','SIMPLIFIED_TAX',  '간이과세자', 3, true),
  ('entity_type','사업자구분','CORPORATION',     '법인',       4, true),

  -- 근무형태 (선임 전용)
  ('work_type','근무형태','RESIDENT',     '상주',   1, true),
  ('work_type','근무형태','NON_RESIDENT', '비상주', 2, true),

  -- 고용형태 (상주 선임 전용)
  ('employment_type','고용형태','REGULAR',   '정규직', 1, true),
  ('employment_type','고용형태','CONTRACT',  '계약직', 2, true),
  ('employment_type','고용형태','DISPATCH',  '파견직', 3, true),
  ('employment_type','고용형태','NEGOTIATE', '협의',   4, true),

  -- 안전 자격증
  ('safety_license_type','안전자격증','INDUSTRIAL_SAFETY_ENG',   '산업안전기사',     1, true),
  ('safety_license_type','안전자격증','CONSTRUCTION_SAFETY_ENG', '건설안전기사',     2, true),
  ('safety_license_type','안전자격증','FIRE_SAFETY_ENG',         '소방설비기사',     3, true),
  ('safety_license_type','안전자격증','INDUSTRIAL_SAFETY_TECH',  '산업안전산업기사', 4, true),
  ('safety_license_type','안전자격증','SAFETY_TECHNICIAN',       '산업안전기술사',   5, true),
  ('safety_license_type','안전자격증','OTHER',                   '기타',             9, true),

  -- 수선 인허가
  ('repair_license_type','수선인허가','GENERAL_CONSTRUCTION',   '종합건설업',     1, true),
  ('repair_license_type','수선인허가','SPECIALTY_CONSTRUCTION', '전문건설업',     2, true),
  ('repair_license_type','수선인허가','ELECTRICAL',             '전기공사업',     3, true),
  ('repair_license_type','수선인허가','FIRE_PROTECTION',        '소방시설공사업', 4, true),
  ('repair_license_type','수선인허가','PLUMBING',               '설비공사업',     5, true),
  ('repair_license_type','수선인허가','OTHER',                  '기타',           9, true)

ON CONFLICT (category, code) DO NOTHING;
