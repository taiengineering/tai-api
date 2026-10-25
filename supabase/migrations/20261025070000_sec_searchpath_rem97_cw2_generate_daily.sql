-- Migration: 20261025070000_sec_searchpath_rem97_cw2_generate_daily.sql
-- WO: WO-TAI-SEC-SEARCHPATH-REM97-CW2-C3-SOURCE-001
-- SEC SEARCHPATH REM97 C-W2 — generate_daily_assignments search_path 고정
--
-- 대상:
--   public.generate_daily_assignments()   OID=18564
--
-- 변경 범위:
--   ALTER FUNCTION ... SET search_path = pg_catalog, public, pg_temp
--   함수 본문·ACL·SECURITY INVOKER·Volatility·Parallel 변경 없음
--   work_schedules/work_assignments 비한정 참조는 pg_catalog, public, pg_temp 경로에서
--   public.work_schedules / public.work_assignments 로 해석 (운영 동일)
--
-- 승인:
--   D-01~D-04 Owner 승인: 2026-10-25
--   WO-TAI-SEC-SEARCHPATH-REM97-CW2-C3-SOURCE-001 OWNER_APPROVAL=APPROVED: 2026-10-25
--
-- 참조:
--   GPT_REM97_CW1_PROD_IV = PASS
--   GPT_REM97_C20_C2_CONTRACT_IV = CONDITIONAL_PASS
--   C-W2 (generate_daily_assignments) — 일일 작업 배정 스케줄러

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1: PRE 기준선 검증 (1건)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_sig         CONSTANT text := 'public.generate_daily_assignments()';
  c_oid         CONSTANT oid  := 18564::oid;
  c_md5         CONSTANT text := '24c1a1e740e4365ea0a82b321d3e247b';
  c_search_path CONSTANT text := 'search_path=pg_catalog, public, pg_temp';
  v_oid       oid;
  v_secdef    bool;
  v_owner     text;
  v_body_md5  text;
  v_proconfig text[];
  v_volat     char;
  v_parallel  char;
BEGIN
  v_oid := to_regprocedure(c_sig)::oid;
  IF v_oid IS NULL THEN
    RAISE EXCEPTION 'PRE FAILED: % not found.', c_sig;
  END IF;
  IF v_oid IS DISTINCT FROM c_oid THEN
    RAISE EXCEPTION 'PRE FAILED: % OID mismatch (expected %, got %).', c_sig, c_oid, v_oid;
  END IF;

  SELECT p.prosecdef, pg_get_userbyid(p.proowner), md5(p.prosrc), p.proconfig, p.provolatile, p.proparallel
  INTO v_secdef, v_owner, v_body_md5, v_proconfig, v_volat, v_parallel
  FROM pg_proc p WHERE p.oid = v_oid;

  IF v_secdef IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'PRE FAILED: % is not SECURITY INVOKER.', c_sig;
  END IF;
  IF v_owner IS DISTINCT FROM 'postgres' THEN
    RAISE EXCEPTION 'PRE FAILED: % owner is %, expected postgres.', c_sig, v_owner;
  END IF;
  IF v_body_md5 IS DISTINCT FROM c_md5 THEN
    RAISE EXCEPTION 'PRE FAILED: % prosrc_md5 mismatch (expected %, got %).', c_sig, c_md5, v_body_md5;
  END IF;
  IF v_proconfig IS NOT NULL THEN
    RAISE EXCEPTION 'PRE FAILED: % proconfig already set: %.', c_sig, v_proconfig;
  END IF;
  IF v_volat IS DISTINCT FROM 'v' THEN
    RAISE EXCEPTION 'PRE FAILED: % volatility is %, expected v (VOLATILE).', c_sig, v_volat;
  END IF;
  IF v_parallel IS DISTINCT FROM 'u' THEN
    RAISE EXCEPTION 'PRE FAILED: % proparallel is %, expected u (UNSAFE).', c_sig, v_parallel;
  END IF;

  RAISE NOTICE 'PRE OK: % OID=% MD5=% INVOKER owner=postgres proconfig=NULL',
    c_sig, c_oid, c_md5;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1B: PRE ACL 스냅샷
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TEMP TABLE _cw2_acl_baseline (
  fn_oid  oid  PRIMARY KEY,
  proacl  text
) ON COMMIT DROP;

INSERT INTO _cw2_acl_baseline (fn_oid, proacl)
SELECT p.oid, p.proacl::text
FROM pg_proc p
WHERE p.oid = 18564::oid;

DO $$
DECLARE v_count int;
BEGIN
  SELECT COUNT(*) INTO v_count FROM _cw2_acl_baseline;
  IF v_count IS DISTINCT FROM 1 THEN
    RAISE EXCEPTION 'PRE FAILED: ACL baseline captured % rows, expected 1.', v_count;
  END IF;
  RAISE NOTICE 'PRE ACL SNAPSHOT OK: 1 row captured';
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 2: search_path 고정 (1건 — METADATA_ONLY)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER FUNCTION public.generate_daily_assignments()
  SET search_path = pg_catalog, public, pg_temp;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3: POST 검증 (1건)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_sig         CONSTANT text := 'public.generate_daily_assignments()';
  c_oid         CONSTANT oid  := 18564::oid;
  c_md5         CONSTANT text := '24c1a1e740e4365ea0a82b321d3e247b';
  c_search_path CONSTANT text := 'search_path=pg_catalog, public, pg_temp';
  v_secdef    bool;
  v_owner     text;
  v_body_md5  text;
  v_proconfig text[];
  v_volat     char;
  v_parallel  char;
BEGIN
  IF to_regprocedure(c_sig)::oid IS DISTINCT FROM c_oid THEN
    RAISE EXCEPTION 'POST FAILED: % OID changed.', c_sig;
  END IF;

  SELECT p.prosecdef, pg_get_userbyid(p.proowner), md5(p.prosrc), p.proconfig, p.provolatile, p.proparallel
  INTO v_secdef, v_owner, v_body_md5, v_proconfig, v_volat, v_parallel
  FROM pg_proc p WHERE p.oid = c_oid;

  IF v_proconfig IS DISTINCT FROM ARRAY[c_search_path]::text[] THEN
    RAISE EXCEPTION 'POST FAILED: % proconfig mismatch: %.', c_sig, v_proconfig;
  END IF;
  IF v_body_md5 IS DISTINCT FROM c_md5 THEN
    RAISE EXCEPTION 'POST FAILED: % prosrc_md5 changed.', c_sig;
  END IF;
  IF v_secdef IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'POST FAILED: % prosecdef changed.', c_sig;
  END IF;
  IF v_owner IS DISTINCT FROM 'postgres' THEN
    RAISE EXCEPTION 'POST FAILED: % owner changed.', c_sig;
  END IF;
  IF v_volat IS DISTINCT FROM 'v' THEN
    RAISE EXCEPTION 'POST FAILED: % volatility changed.', c_sig;
  END IF;
  IF v_parallel IS DISTINCT FROM 'u' THEN
    RAISE EXCEPTION 'POST FAILED: % proparallel changed.', c_sig;
  END IF;

  RAISE NOTICE 'POST OK: % proconfig=[%] MD5=% OID=%',
    c_sig, c_search_path, c_md5, c_oid;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3B: POST ACL 불변 검증
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  r        record;
  v_proacl text;
BEGIN
  FOR r IN SELECT fn_oid, proacl FROM _cw2_acl_baseline ORDER BY fn_oid LOOP
    SELECT p.proacl::text INTO v_proacl FROM pg_proc p WHERE p.oid = r.fn_oid;
    IF v_proacl IS DISTINCT FROM r.proacl THEN
      RAISE EXCEPTION 'POST FAILED: ACL changed for OID % (before=%, after=%).',
        r.fn_oid, r.proacl, v_proacl;
    END IF;
  END LOOP;
  RAISE NOTICE 'POST ACL OK: ACL unchanged for C-W2 function';
END;
$$;

COMMIT;
