-- SEC-03 D0 — 전문가 정보 접근통제: 4개 객체 최소 권한 정리
-- WO-TAI-SEC03-D0-EXPERT-LOCKDOWN-001
-- BASE: 10bb7a1d6f6c590ff01310c820e92427a1c38397
--
-- GPT 설계 결정: B안 + D안 결합
-- - anon / authenticated 직접 객체 권한 전부 제거
-- - 무조건 허용 RLS 정책 13개 제거
-- - service_role_full 정책 3개 유지
-- - RLS 활성화 상태 유지
-- - 테이블·뷰 구조·데이터 변경 없음
--
-- 대상 객체
--   public.safety_personnel   (15건, rowsecurity=true)
--   public.safety_agencies    (0건,  rowsecurity=true)
--   public.repair_companies   (1건,  rowsecurity=true)
--   public.v_expert_list      (UNION ALL View, is_updatable=NO)
--
-- 사전 확인 (PREFLIGHT 기준)
--   anon has_table_privilege: 원본 3개 SELECT/INSERT/UPDATE/DELETE = true
--   anon v_expert_list SELECT = true
--   PUBLIC 직접 권한: 없음 (정보_스키마 기준)
--   service_role_full 정책: 3개 유지 대상

-- ── FIX-A: 직접 객체 권한 제거 ──────────────────────────────────────────

REVOKE ALL PRIVILEGES ON TABLE public.safety_personnel  FROM anon;
REVOKE ALL PRIVILEGES ON TABLE public.safety_personnel  FROM authenticated;

REVOKE ALL PRIVILEGES ON TABLE public.safety_agencies   FROM anon;
REVOKE ALL PRIVILEGES ON TABLE public.safety_agencies   FROM authenticated;

REVOKE ALL PRIVILEGES ON TABLE public.repair_companies  FROM anon;
REVOKE ALL PRIVILEGES ON TABLE public.repair_companies  FROM authenticated;

REVOKE ALL PRIVILEGES ON TABLE public.v_expert_list     FROM anon;
REVOKE ALL PRIVILEGES ON TABLE public.v_expert_list     FROM authenticated;

-- ── FIX-B: 무조건 허용 RLS 정책 제거 (13개) ──────────────────────────────

-- safety_personnel — anon 4개
DROP POLICY IF EXISTS anon_select_safety_personnel ON public.safety_personnel;
DROP POLICY IF EXISTS anon_insert_safety_personnel ON public.safety_personnel;
DROP POLICY IF EXISTS anon_update_safety_personnel ON public.safety_personnel;
DROP POLICY IF EXISTS anon_delete_safety_personnel ON public.safety_personnel;

-- safety_personnel — authenticated 1개
DROP POLICY IF EXISTS authenticated_all_safety_personnel ON public.safety_personnel;

-- safety_agencies — anon 4개
DROP POLICY IF EXISTS anon_select_safety_agencies ON public.safety_agencies;
DROP POLICY IF EXISTS anon_insert_safety_agencies ON public.safety_agencies;
DROP POLICY IF EXISTS anon_update_safety_agencies ON public.safety_agencies;
DROP POLICY IF EXISTS anon_delete_safety_agencies ON public.safety_agencies;

-- repair_companies — anon 4개
DROP POLICY IF EXISTS anon_select_repair_companies ON public.repair_companies;
DROP POLICY IF EXISTS anon_insert_repair_companies ON public.repair_companies;
DROP POLICY IF EXISTS anon_update_repair_companies ON public.repair_companies;
DROP POLICY IF EXISTS anon_delete_repair_companies ON public.repair_companies;

-- ── 유지 확인 메모 (코드 변경 없음) ─────────────────────────────────────
-- service_role_full ON safety_personnel  (ALL, USING true)  → 유지
-- service_role_full ON safety_agencies   (ALL, USING true)  → 유지
-- service_role_full ON repair_companies  (ALL, USING true)  → 유지
-- RLS ENABLED ON 원본 3개 테이블                              → 유지
-- v_expert_list 정의·구조·데이터                              → 변경 없음
