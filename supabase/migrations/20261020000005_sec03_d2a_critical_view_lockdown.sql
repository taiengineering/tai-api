-- SEC-03 D2-A — 고위험 View 7개 anon/authenticated 접근권한 차단
-- WO-TAI-SEC03-D2A-CRITICAL-VIEW-LOCKDOWN-001
-- BASE: 188047f33e0d20c543aeb1a84be7be4040108c4c
--
-- GPT 설계 결정: REVOKE ALL FROM anon + authenticated (7개 View)
-- D1 조사 근거: 소비처 없거나 service_role 대체 경로 확인됨.
--              소유자 postgres / security_invoker=false 로 원본 테이블 RLS 우회 가능.
--
-- 대상 객체 (모두 VIEW, security_invoker=false)
--   public.v_worker_runtime_queue       — 작업자 배정·작업지시 전체 노출 (P0)
--   public.v_documents_expiring         — 사업장별 만료 문서명·파일명 노출 (P0)
--   public.v_document_stats             — 회사별 문서 사용 통계 노출 (P1)
--   public.v_files_unified              — 회사별 파일명·스토리지 경로 노출 (P0)
--   public.v_drafts_with_code           — 법령·AI 처리 내부 초안 노출 (P1)
--   public.v_runtime_metrics            — 내부 문서 처리 통계 노출 (P1)
--   public.v_runtime_metrics_by_factory — 공장별 업무 처리 현황 노출 (P0)
--
-- 사전 확인 (D1 조사 기준, 2026-10-20)
--   anon SELECT: 7개 모두 TRUE (has_table_privilege 확인)
--   PUBLIC 직접 권한: 없음
--   service_role 직접 권한: 없음 (postgres 소유자 권한으로 접근)
--   View RLS 정책: 해당 없음 (VIEW 객체에 RLS 정책 없음)
--
-- 변경 금지 (이번 Migration 범위 외)
--   원본 테이블 권한·RLS — 미변경
--   View 정의·구조·데이터 — 미변경
--   security_invoker 옵션 — 미변경
--   D0 대상(safety_personnel/safety_agencies/repair_companies/v_expert_list) — 미변경
--   잔여 P0(원본 테이블 direct + API 인증 결함) — D2-B 별도 범위

-- ── FIX-A: 직접 객체 권한 제거 (7개 View × 2 역할 = 14 REVOKE) ────────────

REVOKE ALL PRIVILEGES ON TABLE public.v_worker_runtime_queue        FROM anon;
REVOKE ALL PRIVILEGES ON TABLE public.v_worker_runtime_queue        FROM authenticated;

REVOKE ALL PRIVILEGES ON TABLE public.v_documents_expiring           FROM anon;
REVOKE ALL PRIVILEGES ON TABLE public.v_documents_expiring           FROM authenticated;

REVOKE ALL PRIVILEGES ON TABLE public.v_document_stats               FROM anon;
REVOKE ALL PRIVILEGES ON TABLE public.v_document_stats               FROM authenticated;

REVOKE ALL PRIVILEGES ON TABLE public.v_files_unified                FROM anon;
REVOKE ALL PRIVILEGES ON TABLE public.v_files_unified                FROM authenticated;

REVOKE ALL PRIVILEGES ON TABLE public.v_drafts_with_code             FROM anon;
REVOKE ALL PRIVILEGES ON TABLE public.v_drafts_with_code             FROM authenticated;

REVOKE ALL PRIVILEGES ON TABLE public.v_runtime_metrics              FROM anon;
REVOKE ALL PRIVILEGES ON TABLE public.v_runtime_metrics              FROM authenticated;

REVOKE ALL PRIVILEGES ON TABLE public.v_runtime_metrics_by_factory   FROM anon;
REVOKE ALL PRIVILEGES ON TABLE public.v_runtime_metrics_by_factory   FROM authenticated;

-- ── 유지 확인 메모 (코드 변경 없음) ──────────────────────────────────────────
-- service_role: postgres 소유자 권한으로 접근 — 영향 없음
-- services/document_engine_svc.py 소비처: get_supabase()(service_role) 사용 — 영향 없음
-- 원본 테이블 RLS(documents/company_files/law_rule_drafts/runtime_*): 변경 없음
-- View 정의: 변경 없음
