-- cw5_migration_iso.sql
-- WO-TAI-SEC-SEARCHPATH-REM97-CW5-C3-R2-GUARD-CLOSE-001
-- ISO 변환본: 운영 Migration의 격리 DB 실행 전용 사본
--
-- 원본 대비 최소 차이:
--   1. BEGIN 전: 동적 OID 해석 블록 추가 (set_config으로 세션 변수 저장)
--   2. STEP1 PRE DECLARE: OID 리터럴(78511/78515/78513) → current_setting() 동적 조회
--   3. STEP1B INSERT WHERE: IN (78511,78513,78515) → IN (current_setting()::oid, ...)
--   4. STEP3 POST DECLARE: 위와 동일
--   5. STEP3B WHERE:       위와 동일
--   6. STEP2 ALTER x2: 변경 없음 (함수 이름 사용)
-- 기능 로직·검사 조건·MD5 기준선·ACL 기준선: 운영 원본과 100% 동일

-- =========================================================
-- ISO OID 해석 (BEGIN 트랜잭션 외부 → set_config is_local=false 세션 유지)
-- =========================================================
DO $$
DECLARE
  v_c20_oid oid;
  v_c19_oid oid;
  v_rc_oid  oid;
BEGIN
  SELECT p.oid INTO v_c20_oid
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'sieve_executor';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'C-W5 PRE STOP: sieve_executor not found in public schema';
  END IF;

  SELECT p.oid INTO v_c19_oid
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'diagnose_clauses_common';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'C-W5 PRE STOP: diagnose_clauses_common not found in public schema';
  END IF;

  SELECT p.oid INTO v_rc_oid
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'run_common_sieve';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'C-W5 PRE STOP: run_common_sieve not found in public schema';
  END IF;

  PERFORM set_config('cw5iso.c20_oid', v_c20_oid::text, false);
  PERFORM set_config('cw5iso.c19_oid', v_c19_oid::text, false);
  PERFORM set_config('cw5iso.rc_oid',  v_rc_oid::text,  false);
  RAISE NOTICE 'ISO OID RESOLVE: C20=% C19=% RC=%', v_c20_oid, v_c19_oid, v_rc_oid;
END;
$$;

BEGIN;

-- =========================================================
-- STEP1  PRE FAIL-CLOSED  (운영 원본과 로직 동일, OID만 동적)
-- =========================================================
DO $$
DECLARE
  c20_oid  oid  := current_setting('cw5iso.c20_oid')::oid;
  c20_name text := 'sieve_executor';
  c20_md5  text := '79c50e3985bf489f80b1b11ec516aac6';
  c19_oid  oid  := current_setting('cw5iso.c19_oid')::oid;
  c19_name text := 'diagnose_clauses_common';
  c19_md5  text := 'f205550a5412f9111ac3a5449468ac7b';
  rc_oid   oid  := current_setting('cw5iso.rc_oid')::oid;
  rc_name  text := 'run_common_sieve';
  rc_md5   text := 'fbaf7f9a900d09f748ea02a1c6cc9bc6';
  c_acl_expected CONSTANT text :=
    '{=X/postgres,postgres=X/postgres,anon=X/postgres,authenticated=X/postgres,service_role=X/postgres}';
  v_acl_sorted   text;
  c_acl_sorted   text;
  v RECORD;
BEGIN
  /* C20 sieve_executor */
  SELECT proname,
         pronamespace::regnamespace::text AS nsp,
         md5(prosrc)                      AS md5,
         proconfig, prosecdef, provolatile, proparallel,
         (SELECT rolname FROM pg_roles    WHERE oid = p.proowner) AS owner,
         (SELECT lanname FROM pg_language WHERE oid = p.prolang)  AS lang,
         pronargs, proargtypes, proacl
  INTO v FROM pg_proc p WHERE p.oid = c20_oid;

  IF NOT FOUND     THEN RAISE EXCEPTION 'C-W5 PRE STOP: sieve_executor OID % not found', c20_oid; END IF;
  IF v.proname    <> c20_name   THEN RAISE EXCEPTION 'C-W5 PRE C20 funcname: expected % got %', c20_name, v.proname; END IF;
  IF v.nsp        <> 'public'   THEN RAISE EXCEPTION 'C-W5 PRE C20 schema: expected public got %', v.nsp; END IF;
  IF v.md5        <> c20_md5    THEN RAISE EXCEPTION 'C-W5 PRE C20 MD5: expected % got %', c20_md5, v.md5; END IF;
  IF v.proconfig  IS NOT NULL   THEN RAISE EXCEPTION 'C-W5 PRE C20 proconfig not NULL: %', v.proconfig; END IF;
  IF v.prosecdef                THEN RAISE EXCEPTION 'C-W5 PRE C20 unexpected SECURITY DEFINER'; END IF;
  IF v.provolatile <> 's'       THEN RAISE EXCEPTION 'C-W5 PRE C20 volatility: expected s got %', v.provolatile; END IF;
  IF v.proparallel <> 'u'       THEN RAISE EXCEPTION 'C-W5 PRE C20 parallel: expected u got %', v.proparallel; END IF;
  IF v.owner      <> 'postgres' THEN RAISE EXCEPTION 'C-W5 PRE C20 owner: expected postgres got %', v.owner; END IF;
  IF v.lang       <> 'sql'      THEN RAISE EXCEPTION 'C-W5 PRE C20 lang: expected sql got %', v.lang; END IF;
  /* C20 signature */
  IF v.pronargs <> 1 THEN
    RAISE EXCEPTION 'C-W5 PRE C20 pronargs: expected 1 got %', v.pronargs;
  END IF;
  IF v.proargtypes::text <> '25' THEN
    RAISE EXCEPTION 'C-W5 PRE C20 proargtypes: expected 25(text) got %', v.proargtypes::text;
  END IF;
  /* C20 ACL baseline (sorted, order-independent) */
  SELECT string_agg(a::text, ',' ORDER BY a::text) INTO c_acl_sorted
  FROM unnest(c_acl_expected::aclitem[]) a;
  SELECT string_agg(a::text, ',' ORDER BY a::text) INTO v_acl_sorted
  FROM unnest(v.proacl) a;
  IF v_acl_sorted IS DISTINCT FROM c_acl_sorted THEN
    RAISE EXCEPTION 'C-W5 PRE C20 proacl baseline: expected [%] got [%]', c_acl_sorted, v_acl_sorted;
  END IF;

  /* C19 diagnose_clauses_common */
  SELECT proname,
         pronamespace::regnamespace::text AS nsp,
         md5(prosrc)                      AS md5,
         proconfig, prosecdef, provolatile, proparallel,
         (SELECT rolname FROM pg_roles    WHERE oid = p.proowner) AS owner,
         (SELECT lanname FROM pg_language WHERE oid = p.prolang)  AS lang,
         pronargs, proacl
  INTO v FROM pg_proc p WHERE p.oid = c19_oid;

  IF NOT FOUND     THEN RAISE EXCEPTION 'C-W5 PRE STOP: diagnose_clauses_common OID % not found', c19_oid; END IF;
  IF v.proname    <> c19_name   THEN RAISE EXCEPTION 'C-W5 PRE C19 funcname: expected % got %', c19_name, v.proname; END IF;
  IF v.nsp        <> 'public'   THEN RAISE EXCEPTION 'C-W5 PRE C19 schema: expected public got %', v.nsp; END IF;
  IF v.md5        <> c19_md5    THEN RAISE EXCEPTION 'C-W5 PRE C19 MD5: expected % got %', c19_md5, v.md5; END IF;
  IF v.proconfig  IS NOT NULL   THEN RAISE EXCEPTION 'C-W5 PRE C19 proconfig not NULL: %', v.proconfig; END IF;
  IF v.prosecdef                THEN RAISE EXCEPTION 'C-W5 PRE C19 unexpected SECURITY DEFINER'; END IF;
  IF v.provolatile <> 's'       THEN RAISE EXCEPTION 'C-W5 PRE C19 volatility: expected s got %', v.provolatile; END IF;
  IF v.proparallel <> 'u'       THEN RAISE EXCEPTION 'C-W5 PRE C19 parallel: expected u got %', v.proparallel; END IF;
  IF v.owner      <> 'postgres' THEN RAISE EXCEPTION 'C-W5 PRE C19 owner: expected postgres got %', v.owner; END IF;
  IF v.lang       <> 'sql'      THEN RAISE EXCEPTION 'C-W5 PRE C19 lang: expected sql got %', v.lang; END IF;
  /* C19 signature */
  IF v.pronargs <> 0 THEN
    RAISE EXCEPTION 'C-W5 PRE C19 pronargs: expected 0 got %', v.pronargs;
  END IF;
  /* C19 ACL baseline */
  SELECT string_agg(a::text, ',' ORDER BY a::text) INTO v_acl_sorted
  FROM unnest(v.proacl) a;
  IF v_acl_sorted IS DISTINCT FROM c_acl_sorted THEN
    RAISE EXCEPTION 'C-W5 PRE C19 proacl baseline: expected [%] got [%]', c_acl_sorted, v_acl_sorted;
  END IF;

  /* run_common_sieve indirect */
  SELECT proname, md5(prosrc) AS md5, proconfig, pronargs, proacl
  INTO v FROM pg_proc p WHERE p.oid = rc_oid;

  IF NOT FOUND    THEN RAISE EXCEPTION 'C-W5 PRE STOP: run_common_sieve OID % not found', rc_oid; END IF;
  IF v.proname <> rc_name THEN RAISE EXCEPTION 'C-W5 PRE RC funcname: expected % got %', rc_name, v.proname; END IF;
  IF v.md5     <> rc_md5  THEN RAISE EXCEPTION 'C-W5 PRE RC MD5: expected % got %', rc_md5, v.md5; END IF;
  /* RC signature */
  IF v.pronargs <> 0 THEN
    RAISE EXCEPTION 'C-W5 PRE RC pronargs: expected 0 got %', v.pronargs;
  END IF;
  /* RC ACL baseline */
  SELECT string_agg(a::text, ',' ORDER BY a::text) INTO v_acl_sorted
  FROM unnest(v.proacl) a;
  IF v_acl_sorted IS DISTINCT FROM c_acl_sorted THEN
    RAISE EXCEPTION 'C-W5 PRE RC proacl baseline: expected [%] got [%]', c_acl_sorted, v_acl_sorted;
  END IF;

  RAISE NOTICE 'C-W5 PRE PASS: C20 OID=% MD5=% sig=1arg_text ACL=baseline_match', c20_oid, c20_md5;
  RAISE NOTICE 'C-W5 PRE PASS: C19 OID=% MD5=% sig=0arg ACL=baseline_match', c19_oid, c19_md5;
  RAISE NOTICE 'C-W5 PRE PASS: RC  OID=% MD5=% sig=0arg ACL=baseline_match', rc_oid,  rc_md5;
END;
$$;

-- STEP1B  ACL 스냅샷 (ON COMMIT DROP) — ISO: 동적 OID 사용
CREATE TEMP TABLE _cw5_acl_baseline (
  func_oid oid,
  funcname text,
  proacl   text
) ON COMMIT DROP;

INSERT INTO _cw5_acl_baseline
SELECT p.oid, p.proname, p.proacl::text
FROM pg_proc p
WHERE p.oid IN (
  current_setting('cw5iso.c20_oid')::oid,
  current_setting('cw5iso.c19_oid')::oid,
  current_setting('cw5iso.rc_oid')::oid
);

-- =========================================================
-- STEP2  ALTER x2 — search_path 고정 (METADATA ONLY) — 원본과 동일
-- =========================================================
ALTER FUNCTION public.sieve_executor(text)
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.diagnose_clauses_common()
  SET search_path = pg_catalog, public, pg_temp;

-- =========================================================
-- STEP3  POST FAIL-CLOSED (운영 원본과 로직 동일, OID만 동적)
-- =========================================================
DO $$
DECLARE
  c20_oid  oid  := current_setting('cw5iso.c20_oid')::oid;
  c19_oid  oid  := current_setting('cw5iso.c19_oid')::oid;
  rc_oid   oid  := current_setting('cw5iso.rc_oid')::oid;
  c20_md5  text := '79c50e3985bf489f80b1b11ec516aac6';
  c19_md5  text := 'f205550a5412f9111ac3a5449468ac7b';
  rc_md5   text := 'fbaf7f9a900d09f748ea02a1c6cc9bc6';
  v_target text[] := ARRAY['search_path=pg_catalog, public, pg_temp'];
  v RECORD;
BEGIN
  /* C20 POST */
  SELECT md5(prosrc) AS md5, proconfig, prosecdef, provolatile, proparallel,
         (SELECT rolname FROM pg_roles WHERE oid = p.proowner) AS owner
  INTO v FROM pg_proc p WHERE p.oid = c20_oid;

  IF v.md5 <> c20_md5                     THEN RAISE EXCEPTION 'C-W5 POST C20 body MD5 changed: %', v.md5; END IF;
  IF v.proconfig IS NULL OR
     v.proconfig <> v_target               THEN RAISE EXCEPTION 'C-W5 POST C20 proconfig mismatch: %', v.proconfig; END IF;
  IF v.prosecdef                           THEN RAISE EXCEPTION 'C-W5 POST C20 SECURITY DEFINER changed'; END IF;
  IF v.provolatile <> 's'                 THEN RAISE EXCEPTION 'C-W5 POST C20 volatility changed: %', v.provolatile; END IF;
  IF v.proparallel <> 'u'                 THEN RAISE EXCEPTION 'C-W5 POST C20 parallel changed: %', v.proparallel; END IF;
  IF v.owner       <> 'postgres'          THEN RAISE EXCEPTION 'C-W5 POST C20 owner changed: %', v.owner; END IF;

  /* C19 POST */
  SELECT md5(prosrc) AS md5, proconfig, prosecdef, provolatile, proparallel,
         (SELECT rolname FROM pg_roles WHERE oid = p.proowner) AS owner
  INTO v FROM pg_proc p WHERE p.oid = c19_oid;

  IF v.md5 <> c19_md5                     THEN RAISE EXCEPTION 'C-W5 POST C19 body MD5 changed: %', v.md5; END IF;
  IF v.proconfig IS NULL OR
     v.proconfig <> v_target               THEN RAISE EXCEPTION 'C-W5 POST C19 proconfig mismatch: %', v.proconfig; END IF;
  IF v.prosecdef                           THEN RAISE EXCEPTION 'C-W5 POST C19 SECURITY DEFINER changed'; END IF;
  IF v.provolatile <> 's'                 THEN RAISE EXCEPTION 'C-W5 POST C19 volatility changed: %', v.provolatile; END IF;
  IF v.proparallel <> 'u'                 THEN RAISE EXCEPTION 'C-W5 POST C19 parallel changed: %', v.proparallel; END IF;
  IF v.owner       <> 'postgres'          THEN RAISE EXCEPTION 'C-W5 POST C19 owner changed: %', v.owner; END IF;

  /* run_common_sieve 불변 */
  SELECT md5(prosrc) AS md5, proconfig INTO v FROM pg_proc p WHERE p.oid = rc_oid;
  IF v.md5 <> rc_md5          THEN RAISE EXCEPTION 'C-W5 POST RC body MD5 changed: %', v.md5; END IF;
  IF v.proconfig IS NOT NULL   THEN RAISE EXCEPTION 'C-W5 POST RC proconfig must remain NULL: %', v.proconfig; END IF;

  RAISE NOTICE 'C-W5 POST PASS: C20 proconfig=search_path=pg_catalog,public,pg_temp MD5 intact';
  RAISE NOTICE 'C-W5 POST PASS: C19 proconfig=search_path=pg_catalog,public,pg_temp MD5 intact';
  RAISE NOTICE 'C-W5 POST PASS: run_common_sieve MD5 intact proconfig=NULL';
END;
$$;

-- STEP3B  ACL 불변 확인 — ISO: 동적 OID 사용
DO $$
DECLARE
  v_diff integer;
BEGIN
  SELECT COUNT(*) INTO v_diff
  FROM (
    SELECT func_oid, funcname, proacl FROM _cw5_acl_baseline
    EXCEPT
    SELECT p.oid, p.proname, p.proacl::text FROM pg_proc p
    WHERE p.oid IN (
      current_setting('cw5iso.c20_oid')::oid,
      current_setting('cw5iso.c19_oid')::oid,
      current_setting('cw5iso.rc_oid')::oid
    )
  ) d;

  IF v_diff > 0 THEN
    RAISE EXCEPTION 'C-W5 ACL STOP: ACL changed for % function(s)', v_diff;
  END IF;
  RAISE NOTICE 'C-W5 ACL PASS: 3 functions ACL unchanged';
END;
$$;

COMMIT;
