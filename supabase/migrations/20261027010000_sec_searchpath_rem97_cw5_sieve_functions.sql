-- WO-TAI-SEC-SEARCHPATH-REM97-CW5-C3-SOURCE-001
-- Target : public.sieve_executor(text)          OID 78511 (C20)
--          public.diagnose_clauses_common()      OID 78515 (C19)
-- Change : SET search_path = pg_catalog, public, pg_temp  (METADATA ONLY)
-- Indirect regression check: public.run_common_sieve()    OID 78513
-- Function body / ACL / SECURITY / Volatility / Parallel -- all unchanged.
-- DDL gap note: no prior CREATE FUNCTION migration exists in git for these
--   functions.  Gap is recorded; restoration is a separate work item.

BEGIN;

-- =========================================================
-- STEP1  PRE FAIL-CLOSED  -- 대상 2건 + 간접 호출자 기준선 검증
-- =========================================================
DO $$
DECLARE
  c20_oid  oid  := 78511;   c20_name text := 'sieve_executor';
  c20_md5  text := '79c50e3985bf489f80b1b11ec516aac6';
  c19_oid  oid  := 78515;   c19_name text := 'diagnose_clauses_common';
  c19_md5  text := 'f205550a5412f9111ac3a5449468ac7b';
  rc_oid   oid  := 78513;   rc_name  text := 'run_common_sieve';
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

-- STEP1B  ACL 스냅샷 (ON COMMIT DROP)
CREATE TEMP TABLE _cw5_acl_baseline (
  func_oid oid,
  funcname text,
  proacl   text
) ON COMMIT DROP;

INSERT INTO _cw5_acl_baseline
SELECT p.oid, p.proname, p.proacl::text
FROM pg_proc p
WHERE p.oid IN (78511, 78513, 78515);

-- =========================================================
-- STEP2  ALTER x2 -- search_path 고정 (METADATA ONLY)
-- =========================================================
ALTER FUNCTION public.sieve_executor(text)
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.diagnose_clauses_common()
  SET search_path = pg_catalog, public, pg_temp;

-- =========================================================
-- STEP3  POST FAIL-CLOSED
-- =========================================================
DO $$
DECLARE
  c20_oid  oid  := 78511;
  c19_oid  oid  := 78515;
  rc_oid   oid  := 78513;
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

-- STEP3B  ACL 불변 확인
DO $$
DECLARE
  v_diff integer;
BEGIN
  SELECT COUNT(*) INTO v_diff
  FROM (
    SELECT func_oid, funcname, proacl FROM _cw5_acl_baseline
    EXCEPT
    SELECT p.oid, p.proname, p.proacl::text FROM pg_proc p
    WHERE p.oid IN (78511, 78513, 78515)
  ) d;

  IF v_diff > 0 THEN
    RAISE EXCEPTION 'C-W5 ACL STOP: ACL changed for % function(s)', v_diff;
  END IF;
  RAISE NOTICE 'C-W5 ACL PASS: 3 functions ACL unchanged';
END;
$$;

COMMIT;
