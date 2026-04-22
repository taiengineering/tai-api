-- 🚨 긴급 보안 패치: otp_store RLS enable + service_role 전용 정책
-- Date: 2026-04-22
-- Issue: Supabase security advisor ERROR (rls_disabled_in_public, sensitive_columns_exposed)
-- Column otp, phone 노출 위험 차단
--
-- Before:
--   - RLS: DISABLED
--   - 누구나 anon key로 OTP 코드 읽기/쓰기/삭제 가능
--   - 공격자가 phone 번호 열거, OTP 스푸핑 등 가능
--
-- After:
--   - RLS: ENABLED
--   - service_role 키만 접근 가능
--   - anon/authenticated는 기본 deny
--   - 서버 API (SUPABASE_SERVICE_ROLE_KEY 사용)로만 OTP 처리
--
-- Verification (end-to-end):
--   POST /auth/send-otp → otp_store에 저장 확인 → ✅ 성공 (2026-04-22)

-- 1. RLS 활성화
ALTER TABLE public.otp_store ENABLE ROW LEVEL SECURITY;

-- 2. service_role(서버 API)만 전체 접근 허용
-- Note: service_role은 기본적으로 RLS를 bypass 하지만, 명시적 정책으로 의도 문서화
CREATE POLICY "service_role_full_access"
  ON public.otp_store
  AS PERMISSIVE
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- anon/authenticated는 정책이 없으므로 자동 차단됨 (기본 deny)

-- 3. 문서용 코멘트
COMMENT ON TABLE public.otp_store IS
'OTP 인증 코드 임시 저장. RLS: service_role만 접근 가능.
anon/authenticated는 차단됨. 서버 API(SUPABASE_SERVICE_ROLE_KEY)로만 읽기/쓰기 가능.
2026-04-22 긴급 보안 패치 적용.';
