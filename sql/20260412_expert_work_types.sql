-- ============================================================
-- TAI API — 전문가 등록 DB 마이그레이션
-- 작성일: 2026-04-12
-- ============================================================

-- ── 1. expert_applications 테이블 컬럼 추가 ────────────────

ALTER TABLE expert_applications
  -- 근무형태 (복수 선택: RESIDENT / NON_RESIDENT)
  ADD COLUMN IF NOT EXISTS work_types          jsonb,

  -- 사업자 구분
  ADD COLUMN IF NOT EXISTS entity_type         text,   -- INDIVIDUAL / SOLE_PROPRIETOR / SIMPLIFIED_TAX / CORPORATION

  -- 상주 상세
  ADD COLUMN IF NOT EXISTS employment_type     text,   -- REGULAR / CONTRACT / DISPATCH / NEGOTIATE
  ADD COLUMN IF NOT EXISTS immediate_join      text,   -- Y / N
  ADD COLUMN IF NOT EXISTS salary_min          int,
  ADD COLUMN IF NOT EXISTS salary_max          int,

  -- 비상주 상세
  ADD COLUMN IF NOT EXISTS visit_per_month     int,
  ADD COLUMN IF NOT EXISTS remote_support      text,   -- Y / N
  ADD COLUMN IF NOT EXISTS visit_price         int;


-- ── 2. system_codes — 고용형태 (상주 선임 전용) ────────────

INSERT INTO system_codes (category, category_name, code, code_name, sort_order, is_active)
VALUES
  ('employment_type', '고용형태', 'REGULAR',   '정규직', 1, true),
  ('employment_type', '고용형태', 'CONTRACT',  '계약직', 2, true),
  ('employment_type', '고용형태', 'DISPATCH',  '파견직', 3, true),
  ('employment_type', '고용형태', 'NEGOTIATE', '협의',   4, true)
ON CONFLICT (category, code) DO NOTHING;


-- ── 3. system_codes — 근무형태 (선임 전용) ─────────────────

INSERT INTO system_codes (category, category_name, code, code_name, sort_order, is_active)
VALUES
  ('work_type', '근무형태', 'RESIDENT',     '상주',   1, true),
  ('work_type', '근무형태', 'NON_RESIDENT', '비상주', 2, true)
ON CONFLICT (category, code) DO NOTHING;
