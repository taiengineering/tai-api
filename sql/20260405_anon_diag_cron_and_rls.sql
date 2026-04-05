-- ============================================================
-- 1. 만료 처리 크론 작업 등록
--    매일 KST 03:00 에 /anonymous-diagnosis/admin/expire-stale 호출
-- ============================================================
INSERT INTO public.cron_job_master (
  job_code,
  job_name,
  cron_expression,
  endpoint_url,
  http_method,
  request_payload,
  timeout_seconds,
  is_active,
  description
) VALUES (
  'ANON_DIAG_EXPIRE',
  '익명진단 만료처리',
  '0 3 * * *',
  '/anonymous-diagnosis/admin/expire-stale',
  'POST',
  '{}',
  60,
  true,
  'expires_at이 지난 ACTIVE 익명진단 레코드를 EXPIRED로 일괄 변경'
) ON CONFLICT (job_code) DO UPDATE SET
  cron_expression = EXCLUDED.cron_expression,
  endpoint_url    = EXCLUDED.endpoint_url,
  is_active       = EXCLUDED.is_active,
  description     = EXCLUDED.description;


-- ============================================================
-- 2. RLS 정책 — anonymous_diagnosis_results
-- ============================================================

-- RLS 활성화
ALTER TABLE public.anonymous_diagnosis_results ENABLE ROW LEVEL SECURITY;

-- 기존 정책 삭제 (재실행 안전)
DROP POLICY IF EXISTS anon_diag_insert_open     ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_diag_select_by_token ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_diag_select_claimed  ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_diag_update_claim    ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_diag_admin_all       ON public.anonymous_diagnosis_results;
DROP POLICY IF EXISTS anon_diag_service_role    ON public.anonymous_diagnosis_results;

-- (a) service_role은 전체 접근 (API 서버가 service_role key 사용)
CREATE POLICY anon_diag_service_role
  ON public.anonymous_diagnosis_results
  FOR ALL
  USING (current_setting('request.jwt.claim.role', true) = 'service_role')
  WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');

-- (b) anon: INSERT 허용 (비로그인 진단 생성)
CREATE POLICY anon_diag_insert_open
  ON public.anonymous_diagnosis_results
  FOR INSERT
  TO anon
  WITH CHECK (true);

-- (c) anon: public_token으로 SELECT (partial_result만 — full_result 제외는 API에서 처리)
CREATE POLICY anon_diag_select_by_token
  ON public.anonymous_diagnosis_results
  FOR SELECT
  TO anon
  USING (
    status IN ('ACTIVE', 'CLAIMED')
    AND expires_at > now()
  );

-- (d) authenticated: 본인 claimed 레코드 SELECT
CREATE POLICY anon_diag_select_claimed
  ON public.anonymous_diagnosis_results
  FOR SELECT
  TO authenticated
  USING (
    claimed_user_id = auth.uid()
    OR (status IN ('ACTIVE', 'CLAIMED') AND expires_at > now())
  );

-- (e) authenticated: claim UPDATE (본인에게 귀속)
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

-- (f) 관리자 전체 접근은 service_role 정책으로 커버됨
--     (API가 SUPABASE_KEY=service_role_key 사용)

COMMENT ON TABLE public.anonymous_diagnosis_results IS '비로그인 무료진단 결과 임시 저장 (token 조회, 7일 만료, claim 시 users 귀속)';
