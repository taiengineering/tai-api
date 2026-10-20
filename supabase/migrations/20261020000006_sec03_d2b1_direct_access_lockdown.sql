-- SEC-03 D2-B1 — 원본 테이블 직접 접근 차단 및 특권 RPC 실행권한 제거
-- WO-TAI-SEC03-D2B1-DB-DIRECT-ACCESS-LOCKDOWN-001
-- BASE: 31bb1ad7cc3a1a716696a542881dba394f45d1e2

-- ── FIX-A: 직접 객체 권한 제거 ─────────────────────────────────────────────
-- 세 테이블에서 anon·authenticated 직접 접근권한 전체 제거.
-- postgres·service_role 권한은 보존.

REVOKE ALL PRIVILEGES ON TABLE public.documents         FROM anon;
REVOKE ALL PRIVILEGES ON TABLE public.documents         FROM authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.company_files     FROM anon;
REVOKE ALL PRIVILEGES ON TABLE public.company_files     FROM authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.law_rule_drafts   FROM anon;
REVOKE ALL PRIVILEGES ON TABLE public.law_rule_drafts   FROM authenticated;

-- ── FIX-B: 무조건 허용 RLS 정책 제거 ────────────────────────────────────────
-- documents — 5개 (anon_* 4개 + authenticated_all_documents)

DROP POLICY IF EXISTS anon_select_documents       ON public.documents;
DROP POLICY IF EXISTS anon_insert_documents       ON public.documents;
DROP POLICY IF EXISTS anon_update_documents       ON public.documents;
DROP POLICY IF EXISTS anon_delete_documents       ON public.documents;
DROP POLICY IF EXISTS authenticated_all_documents ON public.documents;

-- company_files — 5개 (anon_* 4개 + authenticated_all_company_files)

DROP POLICY IF EXISTS anon_select_company_files        ON public.company_files;
DROP POLICY IF EXISTS anon_insert_company_files        ON public.company_files;
DROP POLICY IF EXISTS anon_update_company_files        ON public.company_files;
DROP POLICY IF EXISTS anon_delete_company_files        ON public.company_files;
DROP POLICY IF EXISTS authenticated_all_company_files  ON public.company_files;

-- law_rule_drafts — 1개

DROP POLICY IF EXISTS anon_select_law_rule_drafts ON public.law_rule_drafts;

-- ── FIX-C: 특권 RPC 실행 권한 제거 ──────────────────────────────────────────
-- refresh_dashboard_stats() SECURITY DEFINER 함수 정의는 변경하지 않는다.
-- PUBLIC·anon·authenticated의 EXECUTE만 제거.
-- service_role EXECUTE 유지.

REVOKE EXECUTE ON FUNCTION public.refresh_dashboard_stats() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.refresh_dashboard_stats() FROM anon;
REVOKE EXECUTE ON FUNCTION public.refresh_dashboard_stats() FROM authenticated;
