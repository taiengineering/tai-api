-- WO-E2E2000-C10-SECURITY-CONTAINMENT-PATCH-001 S1
-- C10(anonymous_diagnosis_results) RLS 강화 — anon/authenticated USING true 제거.
--
-- 배경:
--   운영 DB 확인(GPT, 2026-10-16) 결과 아래 과다 허용 정책이 존재:
--     anon SELECT USING(true)    — 전체 열람 가능
--     anon UPDATE USING(true)    — 인증 없이 상태 변경 가능
--     anon DELETE USING(true)    — 인증 없이 삭제 가능
--     authenticated ALL          — 모든 인증 사용자 전체 접근
--   API 서버는 service_role 키로 직접 접근(RLS 우회)하므로
--   PostgREST(anon/authenticated)의 C10 직접 접근은 의도된 사용 경로가 아니다.
--
-- 적용 전 DB_APPLY_READINESS 확인 필수:
--   SUPABASE_SERVICE_KEY 환경변수 설정 여부를 Railway에서 확인할 것.
--   (.env.example의 SUPABASE_SERVICE_ROLE_KEY와 이름 불일치 가능성 존재)
--
-- DRAFT — DB_PUSH_APPLY_MIGRATION = BLOCKED (운영 적용은 Owner 승인 후)

-- 기존 정책 전부 삭제(재실행 안전)
DROP POLICY IF EXISTS anon_diag_insert_open     ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_diag_select_by_token ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_diag_select_claimed  ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_diag_update_claim    ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_diag_admin_all       ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_diag_service_role    ON public.anonymous_diagnosis_results;

-- 운영 DB에서 GPT가 확인한 추가 과다 허용 정책 이름 (존재하는 경우 삭제)
DROP POLICY IF EXISTS anon_select_all    ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_update_all    ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_delete_all    ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS authenticated_all  ON public.anonymous_diagnosis_results;

-- service_role 전체 접근 (API 서버 전용, RLS 실질적 우회)
CREATE POLICY anon_diag_service_role
  ON public.anonymous_diagnosis_results
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- anon: public_token 조회 전용 (결과 확인 페이지 전용 경로 — API 경유)
-- 주의: 직접 PostgREST 접근 차단이 목표이나, 기존 결과 조회 흐름 보존을 위해
--       status/expires 조건부 SELECT만 허용. INSERT/UPDATE/DELETE는 부여하지 않는다.
CREATE POLICY anon_diag_select_by_token
  ON public.anonymous_diagnosis_results
  FOR SELECT
  TO anon
  USING (
    status IN ('ACTIVE', 'CLAIMED')
    AND expires_at IS NOT NULL
    AND expires_at > now()
  );

-- authenticated: 본인 claimed 레코드 SELECT 전용
CREATE POLICY anon_diag_select_claimed
  ON public.anonymous_diagnosis_results
  FOR SELECT
  TO authenticated
  USING (
    claimed_user_id = auth.uid()
    OR (status IN ('ACTIVE', 'CLAIMED') AND expires_at IS NOT NULL AND expires_at > now())
  );

-- authenticated: claim UPDATE (본인 귀속만, 타인 레코드 덮어쓰기 차단)
CREATE POLICY anon_diag_update_claim
  ON public.anonymous_diagnosis_results
  FOR UPDATE
  TO authenticated
  USING (
    claimed_user_id IS NULL
    OR claimed_user_id = auth.uid()
  )
  WITH CHECK (
    claimed_user_id = auth.uid()
  );

-- anon INSERT: 삭제(API 서버가 service_role로 처리, 비로그인 클라이언트 직접 INSERT 불필요)
-- authenticated INSERT/DELETE: 부여하지 않음 (API 서버만 처리)

COMMENT ON TABLE public.anonymous_diagnosis_results IS
  'C10 — anon USING true(SELECT/UPDATE/DELETE)/authenticated ALL 제거. '
  'service_role ALL + anon SELECT(status/expires 조건부) + auth SELECT/UPDATE(본인) 유지. '
  '(WO-E2E2000-C10-SECURITY-CONTAINMENT-PATCH-001 S1, 2026-10-16)';
