-- WO-E2E2000-C10-PR626-SECURITY-GATE-CORRECTION-001 S1 v2
-- C10(anonymous_diagnosis_results) RLS 강화 — 실제 운영 정책 이름 기준.
--
-- 운영 DB 실측 확인(GPT IV, 2026-10-16) 정책 이름:
--   anon_delete_anonymous_diagnosis_results    -- DENY 대상
--   anon_insert_anonymous_diagnosis_results    -- DENY 대상
--   anon_select_anonymous_diagnosis_results    -- DENY 대상 (USING true 실측)
--   anon_update_anonymous_diagnosis_results    -- DENY 대상 (USING true 실측)
--   authenticated_all_anonymous_diagnosis_results -- DENY 대상
--   service_role_full                          -- 보존 (백엔드 전용)
--
-- 소스 DDL(20260405_anon_diag_cron_and_rls.sql) 구형 이름도 함께 DROP.
--
-- 최소 권한 목표:
--   anon          C10 SELECT/INSERT/UPDATE/DELETE = DENY (직접 접근 전면 차단)
--   authenticated C10 SELECT/INSERT/UPDATE/DELETE = DENY (직접 접근 전면 차단)
--   service_role  C10 backend 접근                = PRESERVE
--
-- 근거: API 서버는 service_role 키로 직접 접근(RLS 우회).
--   PostgREST(anon/authenticated)의 C10 직접 접근은 의도된 경로가 아님.
--   status/expires 조건부 SELECT도 소유권(public_token) 미검증이므로 최소 권한 원칙 위반.
--
-- DRAFT — DB_PUSH_APPLY_MIGRATION = BLOCKED (Owner 승인 + RAILWAY_ENV_NAME_VERIFICATION 완료 후 적용)

-- ── 1. 기존 정책 전부 DROP ────────────────────────────────────────────

-- 운영 DB 실측 이름
DROP POLICY IF EXISTS anon_delete_anonymous_diagnosis_results   ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_insert_anonymous_diagnosis_results   ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_select_anonymous_diagnosis_results   ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_update_anonymous_diagnosis_results   ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS authenticated_all_anonymous_diagnosis_results ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS service_role_full                         ON public.anonymous_diagnosis_results;

-- 소스 DDL(20260405_anon_diag_cron_and_rls.sql) 구형 이름 (혹시 존재하면 삭제)
DROP POLICY IF EXISTS anon_diag_insert_open     ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_diag_select_by_token ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_diag_select_claimed  ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_diag_update_claim    ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_diag_admin_all       ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_diag_service_role    ON public.anonymous_diagnosis_results;

-- v1 마이그레이션(20261016000001, 미적용)에서 사용된 이름 (충돌 방지)
DROP POLICY IF EXISTS anon_select_all   ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_update_all   ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_delete_all   ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS authenticated_all ON public.anonymous_diagnosis_results;

-- ── 2. anon / authenticated 테이블 GRANT 회수 ──────────────────────────

REVOKE ALL PRIVILEGES ON public.anonymous_diagnosis_results FROM anon;
REVOKE ALL PRIVILEGES ON public.anonymous_diagnosis_results FROM authenticated;

-- PUBLIC 경유 유효 권한도 차단
REVOKE ALL PRIVILEGES ON public.anonymous_diagnosis_results FROM PUBLIC;

-- ── 3. service_role 전체 접근 재설정 (백엔드 전용) ─────────────────────

CREATE POLICY service_role_full
  ON public.anonymous_diagnosis_results
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- ── 4. DRIFT GUARD — 예상치 못한 과다 허용 정책 차단 ────────────────────

DO $$
DECLARE
    unexpected_count INTEGER;
    policy_names TEXT;
BEGIN
    SELECT COUNT(*), string_agg(policyname, ', ')
    INTO unexpected_count, policy_names
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'anonymous_diagnosis_results'
      AND policyname <> 'service_role_full';

    IF unexpected_count > 0 THEN
        RAISE EXCEPTION
            'C10_DRIFT_GUARD_FAIL: anon/authenticated 예상치 못한 RLS 정책 %개 발견: [%]. '
            '운영 DB에 알 수 없는 정책이 있습니다. 적용 중단 후 조사하세요.',
            unexpected_count, policy_names;
    END IF;
END $$;

COMMENT ON TABLE public.anonymous_diagnosis_results IS
  'C10 — anon/authenticated 직접 접근 전면 차단. service_role 전용. '
  '(WO-E2E2000-C10-PR626-SECURITY-GATE-CORRECTION-001 S1 v2, 2026-10-16)';
