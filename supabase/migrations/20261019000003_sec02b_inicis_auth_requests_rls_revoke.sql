-- SEC-02B: WO-TAI-SUPABASE-SEC-02B
-- inicis_auth_requests — RLS 활성화 + 일반 역할 테이블 권한 회수
--
-- 배경:
--   RLS = DISABLED, anon/authenticated에 SELECT/INSERT/UPDATE/DELETE/TRUNCATE 부여됨.
--   모든 서버 호출(routers/inicis_auth.py, auth.py, company_users.py,
--   services/diagnosis_integrated_svc.py)은 service_role 전용 클라이언트 사용.
--
-- RLS만으로는 TRUNCATE 권한을 통제할 수 없음 (PostgreSQL 공식 문서 명시).
-- 따라서 RLS 활성화와 테이블 권한 회수를 함께 적용한다.
--
-- service_role은 Supabase에서 RLS를 자동 우회하므로 기존 기능에 영향 없음.

BEGIN;

ALTER TABLE public.inicis_auth_requests
  ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES
  ON TABLE public.inicis_auth_requests
  FROM PUBLIC, anon, authenticated;

COMMIT;
