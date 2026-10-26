-- WO-TAI-SEC-SEARCHPATH-REM97-AW4-C3-SOURCE-001
-- Target : public.fn_generate_asset_code()   OID 18557
--          public.fn_generate_company_code()  OID 18558
--          public.fn_generate_site_code()     OID 18559
--          public.fn_generate_team_code()     OID 18560
--          public.fn_generate_user_code()     OID 18561
-- Change : SET search_path = pg_catalog, public, pg_temp  (METADATA ONLY)
-- Function body / ACL / SECURITY / Volatility / Parallel / Triggers -- all unchanged.
-- C2 isolated evidence: GPT_REM97_AW4_C2_FINAL_IV = PASS (2026-10-26)
--   C2 ZIP 74ee4aa5 / R1 ZIP 6b722a5c / ACL ZIP 30a7e1f5

BEGIN;

-- =========================================================
-- STEP1  PRE FAIL-CLOSED  -- 5개 트리거 함수 기준선 검증
-- =========================================================
DO $$
DECLARE
  c_acl_expected CONSTANT text :=
    '{=X/postgres,postgres=X/postgres,anon=X/postgres,authenticated=X/postgres,service_role=X/postgres}';
  c_acl_sorted   text;
  v_acl_sorted   text;
  v RECORD;

  -- 대상 OID·이름·MD5
  t_oids  oid[]  := ARRAY[18557, 18558, 18559, 18560, 18561];
  t_names text[] := ARRAY[
    'fn_generate_asset_code',
    'fn_generate_company_code',
    'fn_generate_site_code',
    'fn_generate_team_code',
    'fn_generate_user_code'
  ];
  t_md5s  text[] := ARRAY[
    '716c1df59ef2b3e4a20d8d810598732f',
    'ad17d81156ae5c1a66f9c2b6216c15d7',
    '7bd5a931ad8963226f17847c3ca1a1a3',
    '270ed9eb57d7718a8316e774a8257cf0',
    'df3a1f47e3516edc1030bd8590ad7dc2'
  ];
  i integer;
BEGIN
  SELECT string_agg(a::text, ',' ORDER BY a::text) INTO c_acl_sorted
  FROM unnest(c_acl_expected::aclitem[]) a;

  FOR i IN 1..5 LOOP
    SELECT p.proname,
           p.pronamespace::regnamespace::text AS nsp,
           md5(p.prosrc)                      AS md5,
           p.proconfig, p.prosecdef, p.provolatile, p.proparallel,
           (SELECT rolname FROM pg_roles    WHERE oid = p.proowner) AS owner,
           (SELECT lanname FROM pg_language WHERE oid = p.prolang)  AS lang,
           p.pronargs, p.prorettype::regtype::text AS rettype, p.proacl
    INTO v FROM pg_proc p WHERE p.oid = t_oids[i];

    IF NOT FOUND THEN
      RAISE EXCEPTION 'A-W4 PRE STOP: % OID % not found', t_names[i], t_oids[i];
    END IF;
    IF v.proname    <> t_names[i]  THEN RAISE EXCEPTION 'A-W4 PRE % funcname: expected % got %', t_oids[i], t_names[i], v.proname; END IF;
    IF v.nsp        <> 'public'    THEN RAISE EXCEPTION 'A-W4 PRE % schema: expected public got %', t_names[i], v.nsp; END IF;
    IF v.md5        <> t_md5s[i]   THEN RAISE EXCEPTION 'A-W4 PRE % MD5: expected % got %', t_names[i], t_md5s[i], v.md5; END IF;
    IF v.proconfig  IS NOT NULL    THEN RAISE EXCEPTION 'A-W4 PRE % proconfig not NULL: %', t_names[i], v.proconfig; END IF;
    IF v.prosecdef                 THEN RAISE EXCEPTION 'A-W4 PRE % unexpected SECURITY DEFINER', t_names[i]; END IF;
    IF v.provolatile <> 'v'        THEN RAISE EXCEPTION 'A-W4 PRE % volatility: expected v got %', t_names[i], v.provolatile; END IF;
    IF v.proparallel <> 'u'        THEN RAISE EXCEPTION 'A-W4 PRE % parallel: expected u got %', t_names[i], v.proparallel; END IF;
    IF v.owner       <> 'postgres' THEN RAISE EXCEPTION 'A-W4 PRE % owner: expected postgres got %', t_names[i], v.owner; END IF;
    IF v.lang        <> 'plpgsql'  THEN RAISE EXCEPTION 'A-W4 PRE % lang: expected plpgsql got %', t_names[i], v.lang; END IF;
    IF v.pronargs    <> 0          THEN RAISE EXCEPTION 'A-W4 PRE % pronargs: expected 0 got %', t_names[i], v.pronargs; END IF;
    IF v.rettype     <> 'trigger'  THEN RAISE EXCEPTION 'A-W4 PRE % rettype: expected trigger got %', t_names[i], v.rettype; END IF;

    SELECT string_agg(a::text, ',' ORDER BY a::text) INTO v_acl_sorted
    FROM unnest(v.proacl) a;
    IF v_acl_sorted IS DISTINCT FROM c_acl_sorted THEN
      RAISE EXCEPTION 'A-W4 PRE % proacl baseline: expected [%] got [%]', t_names[i], c_acl_sorted, v_acl_sorted;
    END IF;

    RAISE NOTICE 'A-W4 PRE PASS: % OID=% MD5=% pronargs=0 rettype=trigger VOLATILE UNSAFE INVOKER plpgsql ACL=baseline', t_names[i], t_oids[i], t_md5s[i];
  END LOOP;
END;
$$;

-- STEP1B  ACL 스냅샷 (ON COMMIT DROP)
CREATE TEMP TABLE _aw4_acl_baseline (
  func_oid oid,
  funcname text,
  proacl   text
) ON COMMIT DROP;

INSERT INTO _aw4_acl_baseline
SELECT p.oid, p.proname, p.proacl::text
FROM pg_proc p
WHERE p.oid IN (18557, 18558, 18559, 18560, 18561);

-- =========================================================
-- STEP2  ALTER x5 -- search_path 고정 (METADATA ONLY)
-- =========================================================
ALTER FUNCTION public.fn_generate_asset_code()
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.fn_generate_company_code()
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.fn_generate_site_code()
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.fn_generate_team_code()
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.fn_generate_user_code()
  SET search_path = pg_catalog, public, pg_temp;

-- =========================================================
-- STEP3  POST FAIL-CLOSED
-- =========================================================
DO $$
DECLARE
  v_target text[] := ARRAY['search_path=pg_catalog, public, pg_temp'];
  t_oids  oid[]  := ARRAY[18557, 18558, 18559, 18560, 18561];
  t_names text[] := ARRAY[
    'fn_generate_asset_code',
    'fn_generate_company_code',
    'fn_generate_site_code',
    'fn_generate_team_code',
    'fn_generate_user_code'
  ];
  t_md5s  text[] := ARRAY[
    '716c1df59ef2b3e4a20d8d810598732f',
    'ad17d81156ae5c1a66f9c2b6216c15d7',
    '7bd5a931ad8963226f17847c3ca1a1a3',
    '270ed9eb57d7718a8316e774a8257cf0',
    'df3a1f47e3516edc1030bd8590ad7dc2'
  ];
  v RECORD;
  i integer;
BEGIN
  FOR i IN 1..5 LOOP
    SELECT md5(p.prosrc) AS md5, p.proconfig, p.prosecdef, p.provolatile, p.proparallel,
           (SELECT rolname FROM pg_roles WHERE oid = p.proowner) AS owner
    INTO v FROM pg_proc p WHERE p.oid = t_oids[i];

    IF v.md5 <> t_md5s[i]                  THEN RAISE EXCEPTION 'A-W4 POST % body MD5 changed: %', t_names[i], v.md5; END IF;
    IF v.proconfig IS NULL OR
       v.proconfig <> v_target              THEN RAISE EXCEPTION 'A-W4 POST % proconfig mismatch: %', t_names[i], v.proconfig; END IF;
    IF v.prosecdef                          THEN RAISE EXCEPTION 'A-W4 POST % SECURITY DEFINER changed', t_names[i]; END IF;
    IF v.provolatile <> 'v'                THEN RAISE EXCEPTION 'A-W4 POST % volatility changed: %', t_names[i], v.provolatile; END IF;
    IF v.proparallel <> 'u'                THEN RAISE EXCEPTION 'A-W4 POST % parallel changed: %', t_names[i], v.proparallel; END IF;
    IF v.owner       <> 'postgres'         THEN RAISE EXCEPTION 'A-W4 POST % owner changed: %', t_names[i], v.owner; END IF;

    RAISE NOTICE 'A-W4 POST PASS: % proconfig=search_path=pg_catalog,public,pg_temp MD5 intact', t_names[i];
  END LOOP;
END;
$$;

-- STEP3B  ACL 불변 확인
DO $$
DECLARE v_diff integer;
BEGIN
  SELECT COUNT(*) INTO v_diff
  FROM (
    SELECT func_oid, funcname, proacl FROM _aw4_acl_baseline
    EXCEPT
    SELECT p.oid, p.proname, p.proacl::text FROM pg_proc p
    WHERE p.oid IN (18557, 18558, 18559, 18560, 18561)
  ) d;

  IF v_diff > 0 THEN
    RAISE EXCEPTION 'A-W4 ACL STOP: ACL changed for % function(s)', v_diff;
  END IF;
  RAISE NOTICE 'A-W4 ACL PASS: 5 functions ACL unchanged';
END;
$$;

COMMIT;
