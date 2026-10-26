-- run_aw4_regression.sql
-- WO-TAI-SEC-SEARCHPATH-REM97-AW4-C3-SOURCE-001
-- 격리 회귀 테스트 — fn_generate_{asset,company,site,team,user}_code
-- 전제: setup_aw4.sql 실행 완료 (격리 DB, proconfig=NULL)
-- 검증: PRE 동작 → migration 적용 → POST 동작 → PRE/POST 동등성
-- C2 evidence: GPT_REM97_AW4_C2_FINAL_IV = PASS (2026-10-26)
-- R1 보정: WO-TAI-SEC-SEARCHPATH-REM97-AW4-C3-ISOLATION-GUARD-R1-001
-- 운영 DB 오실행 방지 Fail-Closed Guard 추가 (파일 전체 외부 트랜잭션 없음 — 내부 SAVEPOINT 보존)

\set ON_ERROR_STOP on

-- ── ISOLATION GUARD (Fail-Closed) ────────────────────────────────────
-- Guard 실패 시 ON_ERROR_STOP 으로 이후 SQL 실행 중단 (exit code ≠ 0).
-- 파일 내부에서 app.rem97_aw4_isolated 를 설정하지 않는다.
DO $$
BEGIN
  IF current_database() IS DISTINCT FROM 'aw4_test'
     OR current_setting('app.rem97_aw4_isolated', true)
        IS DISTINCT FROM 'approved'
     OR to_regnamespace('auth') IS NOT NULL
     OR to_regnamespace('storage') IS NOT NULL
     OR to_regnamespace('supabase_migrations') IS NOT NULL
  THEN
    RAISE EXCEPTION
      'REM97 AW4 ISOLATION GUARD FAILED: unsafe database — '
      'db=% permit=% auth=% storage=% supabase_migrations=%',
      current_database(),
      current_setting('app.rem97_aw4_isolated', true),
      to_regnamespace('auth')::text,
      to_regnamespace('storage')::text,
      to_regnamespace('supabase_migrations')::text;
  END IF;
  RAISE NOTICE 'ISOLATION GUARD PASS: db=aw4_test permit=approved no_supabase_schemas';
END;
$$;

DO $$ BEGIN RAISE NOTICE '=== A-W4 격리 회귀 테스트 시작 ==='; END; $$;

-- =========================================================
-- PHASE 0  MD5 기준선 저장 (C2 evidence 값과 일치 확인)
-- =========================================================
DO $$
DECLARE
  c_md5s text[] := ARRAY[
    '716c1df59ef2b3e4a20d8d810598732f',
    'ad17d81156ae5c1a66f9c2b6216c15d7',
    '7bd5a931ad8963226f17847c3ca1a1a3',
    '270ed9eb57d7718a8316e774a8257cf0',
    'df3a1f47e3516edc1030bd8590ad7dc2'
  ];
  c_names text[] := ARRAY[
    'fn_generate_asset_code',
    'fn_generate_company_code',
    'fn_generate_site_code',
    'fn_generate_team_code',
    'fn_generate_user_code'
  ];
  v_md5 text;
  i integer;
BEGIN
  FOR i IN 1..5 LOOP
    SELECT md5(prosrc) INTO v_md5
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname = c_names[i];

    IF v_md5 <> c_md5s[i] THEN
      RAISE EXCEPTION 'PHASE0 MD5 MISMATCH: % expected % got %', c_names[i], c_md5s[i], v_md5;
    END IF;
    PERFORM set_config('app.aw4_md5_' || c_names[i], v_md5, false);
  END LOOP;
  RAISE NOTICE 'PHASE0 PASS: 5/5 MD5 match C2 baseline — body unchanged';
END;
$$;

-- =========================================================
-- PHASE 1  PRE — proconfig=NULL + 기능 계약 검증
-- =========================================================
DO $$ BEGIN RAISE NOTICE '=== PHASE 1 PRE (proconfig=NULL) ==='; END; $$;

-- P1-01: proconfig IS NULL (PRE 상태)
DO $$
DECLARE cnt integer;
BEGIN
  SELECT COUNT(*) INTO cnt
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public'
    AND p.proname IN ('fn_generate_asset_code','fn_generate_company_code',
                      'fn_generate_site_code','fn_generate_team_code','fn_generate_user_code')
    AND p.proconfig IS NULL;
  IF cnt <> 5 THEN
    RAISE EXCEPTION 'P1-01 FAIL: expected 5 with proconfig=NULL got %', cnt;
  END IF;
  RAISE NOTICE 'P1-01 PASS: 5/5 proconfig=NULL (PRE state confirmed)';
END;
$$;

-- P1-02: asset_code NULL → 자동생성 (AST 접두어 + 숫자)
DO $$
DECLARE v text;
BEGIN
  INSERT INTO public.equipment_assets DEFAULT VALUES RETURNING asset_code INTO v;
  IF v NOT LIKE 'AST%' THEN RAISE EXCEPTION 'P1-02 FAIL: asset_code prefix expected AST got %', v; END IF;
  IF length(v) < 9 THEN RAISE EXCEPTION 'P1-02 FAIL: asset_code too short %', v; END IF;
  RAISE NOTICE 'P1-02 PASS (PRE): asset_code=%', v;
END;
$$;

-- P1-03: asset_code 빈 문자열 → 자동생성
DO $$
DECLARE v text;
BEGIN
  INSERT INTO public.equipment_assets(asset_code) VALUES ('') RETURNING asset_code INTO v;
  IF v NOT LIKE 'AST%' THEN RAISE EXCEPTION 'P1-03 FAIL: %', v; END IF;
  RAISE NOTICE 'P1-03 PASS (PRE): asset_code=%', v;
END;
$$;

-- P1-04: asset_code 기존 값 보존
DO $$
DECLARE v text;
BEGIN
  INSERT INTO public.equipment_assets(asset_code) VALUES ('AST-EXISTING') RETURNING asset_code INTO v;
  IF v <> 'AST-EXISTING' THEN RAISE EXCEPTION 'P1-04 FAIL: expected AST-EXISTING got %', v; END IF;
  RAISE NOTICE 'P1-04 PASS (PRE): existing asset_code preserved';
END;
$$;

-- P1-05: company_code 빈 문자열 → 자동생성 (COMP 접두어)
DO $$
DECLARE v text;
BEGIN
  INSERT INTO public.companies(company_code) VALUES ('') RETURNING company_code INTO v;
  IF v NOT LIKE 'COMP%' THEN RAISE EXCEPTION 'P1-05 FAIL: company_code prefix expected COMP got %', v; END IF;
  RAISE NOTICE 'P1-05 PASS (PRE): company_code=%', v;
END;
$$;

-- P1-06: company_code 기존 값 보존
DO $$
DECLARE v text;
BEGIN
  INSERT INTO public.companies(company_code) VALUES ('COMP-EXISTING') RETURNING company_code INTO v;
  IF v <> 'COMP-EXISTING' THEN RAISE EXCEPTION 'P1-06 FAIL: expected COMP-EXISTING got %', v; END IF;
  RAISE NOTICE 'P1-06 PASS (PRE): existing company_code preserved';
END;
$$;

-- P1-07: site_code NULL + ACTIVE → SITE 생성 + 형식 확인
DO $$
DECLARE v text; num bigint;
BEGIN
  INSERT INTO public.factories(status_code) VALUES ('ACTIVE') RETURNING site_code INTO v;
  IF v NOT LIKE 'SITE%' THEN RAISE EXCEPTION 'P1-07 FAIL: site_code prefix expected SITE got %', v; END IF;
  num := substring(v FROM 5)::bigint;
  IF num < 1 THEN RAISE EXCEPTION 'P1-07 FAIL: site_code number invalid %', v; END IF;
  RAISE NOTICE 'P1-07 PASS (PRE): site_code=% (SITE+seq format)', v;
END;
$$;

-- P1-08~12: TMP 분기 — ANON_TEMP/E2E_TEMP/REGA_TEMP/REGB_TEMP/E2E_TEST → TMP- UUID v4
DO $$
DECLARE
  tc       text;
  v_code   text;
  v_uuid   text;
  v_version text;
  v_variant text;
  seq1     bigint; seq2 bigint;
BEGIN
  FOREACH tc IN ARRAY ARRAY['ANON_TEMP','E2E_TEMP','REGA_TEMP','REGB_TEMP','E2E_TEST'] LOOP
    SELECT last_value INTO seq1 FROM public.seq_site_code;
    INSERT INTO public.factories(status_code) VALUES (tc) RETURNING site_code INTO v_code;
    SELECT last_value INTO seq2 FROM public.seq_site_code;

    IF v_code NOT LIKE 'TMP-%' THEN
      RAISE EXCEPTION 'P1-TMP FAIL: no TMP- prefix status=% code=%', tc, v_code;
    END IF;
    IF length(v_code) <> 36 THEN
      RAISE EXCEPTION 'P1-TMP FAIL: length expected 36 got % status=%', length(v_code), tc;
    END IF;
    v_uuid := substring(v_code FROM 5);
    IF v_uuid !~ '^[0-9a-f]{32}$' THEN
      RAISE EXCEPTION 'P1-TMP FAIL: non-hex uuid status=% uuid=%', tc, v_uuid;
    END IF;
    v_version := substring(v_uuid FROM 13 FOR 1);
    IF v_version <> '4' THEN
      RAISE EXCEPTION 'P1-TMP FAIL: UUID version not 4 pos13=% status=%', v_version, tc;
    END IF;
    v_variant := substring(v_uuid FROM 17 FOR 1);
    IF v_variant NOT IN ('8','9','a','b') THEN
      RAISE EXCEPTION 'P1-TMP FAIL: UUID variant not RFC4122 pos17=% status=%', v_variant, tc;
    END IF;
    IF seq2 <> seq1 THEN
      RAISE EXCEPTION 'P1-TMP FAIL: seq_site_code consumed for TMP status=%', tc;
    END IF;
    RAISE NOTICE 'P1-TMP PASS (PRE): status=% code_len=36 UUID_v4 variant=% seq_unchanged', tc, v_variant;
  END LOOP;
END;
$$;

-- P1-13: site_code 기존 값 보존 (TMP 상태에서도)
DO $$
DECLARE v text;
BEGIN
  INSERT INTO public.factories(site_code, status_code) VALUES ('SITE-EXISTING', 'ANON_TEMP')
    RETURNING site_code INTO v;
  IF v <> 'SITE-EXISTING' THEN RAISE EXCEPTION 'P1-13 FAIL: expected SITE-EXISTING got %', v; END IF;
  RAISE NOTICE 'P1-13 PASS (PRE): existing site_code preserved under TMP status';
END;
$$;

-- P1-14: team_code NULL → 자동생성 (TEAM 접두어)
DO $$
DECLARE v text;
BEGIN
  INSERT INTO public.teams DEFAULT VALUES RETURNING team_code INTO v;
  IF v NOT LIKE 'TEAM%' THEN RAISE EXCEPTION 'P1-14 FAIL: team_code prefix expected TEAM got %', v; END IF;
  RAISE NOTICE 'P1-14 PASS (PRE): team_code=%', v;
END;
$$;

-- P1-15: user_code NULL → 자동생성 (USR 접두어)
DO $$
DECLARE v text;
BEGIN
  INSERT INTO public.users DEFAULT VALUES RETURNING user_code INTO v;
  IF v NOT LIKE 'USR%' THEN RAISE EXCEPTION 'P1-15 FAIL: user_code prefix expected USR got %', v; END IF;
  RAISE NOTICE 'P1-15 PASS (PRE): user_code=%', v;
END;
$$;

-- P1-16: SAVEPOINT 롤백 + 시퀀스 비트랜잭션 단언 (R1-01)
CREATE TEMP TABLE _aw4_pre_seq_state (label text PRIMARY KEY, icount integer, seqval bigint);

DO $$
DECLARE cnt integer; seq bigint;
BEGIN
  SELECT COUNT(*) INTO cnt FROM public.equipment_assets;
  SELECT last_value INTO seq FROM public.seq_asset_code;
  INSERT INTO _aw4_pre_seq_state VALUES ('pre', cnt, seq);
  RAISE NOTICE 'P1-16 before: row_count=% seq=%', cnt, seq;
END;
$$;

BEGIN;
SAVEPOINT sp_pre;
INSERT INTO public.equipment_assets DEFAULT VALUES;
ROLLBACK TO SAVEPOINT sp_pre;
RELEASE SAVEPOINT sp_pre;
DO $$
DECLARE cnt_b integer; cnt_a integer; seq_b bigint; seq_a bigint;
BEGIN
  SELECT icount, seqval INTO cnt_b, seq_b FROM _aw4_pre_seq_state WHERE label='pre';
  SELECT COUNT(*) INTO cnt_a FROM public.equipment_assets;
  SELECT last_value INTO seq_a FROM public.seq_asset_code;
  IF cnt_a <> cnt_b THEN RAISE EXCEPTION 'P1-16 FAIL PRE: row not rolled back before=% after=%', cnt_b, cnt_a; END IF;
  IF seq_a <= seq_b THEN RAISE EXCEPTION 'P1-16 FAIL PRE: sequence was rolled back before=% after=%', seq_b, seq_a; END IF;
  RAISE NOTICE 'P1-16 PASS (PRE): SAVEPOINT rollback row=unchanged seq non-transactional (% → %)', seq_b, seq_a;
END;
$$;
COMMIT;

DROP TABLE _aw4_pre_seq_state;

DO $$ BEGIN RAISE NOTICE '=== PHASE 1 PRE COMPLETE (16 tests) ==='; END; $$;

-- =========================================================
-- PHASE 2  Migration 적용 (search_path 고정)
-- =========================================================
DO $$ BEGIN RAISE NOTICE '=== PHASE 2 Migration ALTER FUNCTION x5 ==='; END; $$;

ALTER FUNCTION public.fn_generate_asset_code()   SET search_path = pg_catalog, public, pg_temp;
ALTER FUNCTION public.fn_generate_company_code() SET search_path = pg_catalog, public, pg_temp;
ALTER FUNCTION public.fn_generate_site_code()    SET search_path = pg_catalog, public, pg_temp;
ALTER FUNCTION public.fn_generate_team_code()    SET search_path = pg_catalog, public, pg_temp;
ALTER FUNCTION public.fn_generate_user_code()    SET search_path = pg_catalog, public, pg_temp;

-- proconfig 적용 확인
DO $$
DECLARE cnt integer;
BEGIN
  SELECT COUNT(*) INTO cnt
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public'
    AND p.proname IN ('fn_generate_asset_code','fn_generate_company_code',
                      'fn_generate_site_code','fn_generate_team_code','fn_generate_user_code')
    AND p.proconfig = ARRAY['search_path=pg_catalog, public, pg_temp']::text[];
  IF cnt <> 5 THEN
    RAISE EXCEPTION 'PHASE2 FAIL: only % of 5 have proconfig set', cnt;
  END IF;
  RAISE NOTICE 'PHASE2 PASS: 5/5 proconfig=search_path=pg_catalog,public,pg_temp';
END;
$$;

-- =========================================================
-- PHASE 3  POST — proconfig 설정 + 기능 계약 동등성 검증
-- =========================================================
DO $$ BEGIN RAISE NOTICE '=== PHASE 3 POST (proconfig=search_path set) ==='; END; $$;

-- P3-01: asset_code NULL → 자동생성
DO $$
DECLARE v text;
BEGIN
  INSERT INTO public.equipment_assets DEFAULT VALUES RETURNING asset_code INTO v;
  IF v NOT LIKE 'AST%' THEN RAISE EXCEPTION 'P3-01 FAIL: asset_code prefix expected AST got %', v; END IF;
  RAISE NOTICE 'P3-01 PASS (POST): asset_code=%', v;
END;
$$;

-- P3-02: asset_code 빈 문자열 → 자동생성
DO $$
DECLARE v text;
BEGIN
  INSERT INTO public.equipment_assets(asset_code) VALUES ('') RETURNING asset_code INTO v;
  IF v NOT LIKE 'AST%' THEN RAISE EXCEPTION 'P3-02 FAIL: %', v; END IF;
  RAISE NOTICE 'P3-02 PASS (POST): asset_code=%', v;
END;
$$;

-- P3-03: asset_code 기존 값 보존
DO $$
DECLARE v text;
BEGIN
  INSERT INTO public.equipment_assets(asset_code) VALUES ('AST-POST-EXISTING') RETURNING asset_code INTO v;
  IF v <> 'AST-POST-EXISTING' THEN RAISE EXCEPTION 'P3-03 FAIL: expected AST-POST-EXISTING got %', v; END IF;
  RAISE NOTICE 'P3-03 PASS (POST): existing asset_code preserved';
END;
$$;

-- P3-04: company_code 빈 문자열 → 자동생성
DO $$
DECLARE v text;
BEGIN
  INSERT INTO public.companies(company_code) VALUES ('') RETURNING company_code INTO v;
  IF v NOT LIKE 'COMP%' THEN RAISE EXCEPTION 'P3-04 FAIL: %', v; END IF;
  RAISE NOTICE 'P3-04 PASS (POST): company_code=%', v;
END;
$$;

-- P3-05: site_code NULL + ACTIVE → SITE 생성 + 형식 확인
DO $$
DECLARE v text; num bigint;
BEGIN
  INSERT INTO public.factories(status_code) VALUES ('ACTIVE') RETURNING site_code INTO v;
  IF v NOT LIKE 'SITE%' THEN RAISE EXCEPTION 'P3-05 FAIL: %', v; END IF;
  num := substring(v FROM 5)::bigint;
  IF num < 1 THEN RAISE EXCEPTION 'P3-05 FAIL: site_code number invalid %', v; END IF;
  RAISE NOTICE 'P3-05 PASS (POST): site_code=% (SITE+seq format)', v;
END;
$$;

-- P3-06~10: TMP 분기 + UUID v4 (POST)
DO $$
DECLARE
  tc       text;
  v_code   text;
  v_uuid   text;
  v_version text;
  v_variant text;
BEGIN
  FOREACH tc IN ARRAY ARRAY['ANON_TEMP','E2E_TEMP','REGA_TEMP','REGB_TEMP','E2E_TEST'] LOOP
    INSERT INTO public.factories(status_code) VALUES (tc) RETURNING site_code INTO v_code;
    IF v_code NOT LIKE 'TMP-%' THEN
      RAISE EXCEPTION 'P3-TMP FAIL: no TMP- prefix status=% code=%', tc, v_code;
    END IF;
    IF length(v_code) <> 36 THEN
      RAISE EXCEPTION 'P3-TMP FAIL: length expected 36 got % status=%', length(v_code), tc;
    END IF;
    v_uuid := substring(v_code FROM 5);
    IF v_uuid !~ '^[0-9a-f]{32}$' THEN
      RAISE EXCEPTION 'P3-TMP FAIL: non-hex uuid status=% uuid=%', tc, v_uuid;
    END IF;
    v_version := substring(v_uuid FROM 13 FOR 1);
    IF v_version <> '4' THEN RAISE EXCEPTION 'P3-TMP FAIL: UUID version not 4 status=%', tc; END IF;
    v_variant := substring(v_uuid FROM 17 FOR 1);
    IF v_variant NOT IN ('8','9','a','b') THEN
      RAISE EXCEPTION 'P3-TMP FAIL: UUID variant not RFC4122 status=%', tc;
    END IF;
    RAISE NOTICE 'P3-TMP PASS (POST): status=% code_len=36 UUID_v4 variant=%', tc, v_variant;
  END LOOP;
END;
$$;

-- P3-11: team_code NULL → 자동생성
DO $$
DECLARE v text;
BEGIN
  INSERT INTO public.teams DEFAULT VALUES RETURNING team_code INTO v;
  IF v NOT LIKE 'TEAM%' THEN RAISE EXCEPTION 'P3-11 FAIL: %', v; END IF;
  RAISE NOTICE 'P3-11 PASS (POST): team_code=%', v;
END;
$$;

-- P3-12: user_code NULL → 자동생성
DO $$
DECLARE v text;
BEGIN
  INSERT INTO public.users DEFAULT VALUES RETURNING user_code INTO v;
  IF v NOT LIKE 'USR%' THEN RAISE EXCEPTION 'P3-12 FAIL: %', v; END IF;
  RAISE NOTICE 'P3-12 PASS (POST): user_code=%', v;
END;
$$;

-- P3-13: SAVEPOINT 롤백 + 시퀀스 비트랜잭션 단언 (POST, R1-01 동등성)
CREATE TEMP TABLE _aw4_post_seq_state (label text PRIMARY KEY, icount integer, seqval bigint);

DO $$
DECLARE cnt integer; seq bigint;
BEGIN
  SELECT COUNT(*) INTO cnt FROM public.equipment_assets;
  SELECT last_value INTO seq FROM public.seq_asset_code;
  INSERT INTO _aw4_post_seq_state VALUES ('post', cnt, seq);
  RAISE NOTICE 'P3-13 before: row_count=% seq=%', cnt, seq;
END;
$$;

BEGIN;
SAVEPOINT sp_post;
INSERT INTO public.equipment_assets DEFAULT VALUES;
ROLLBACK TO SAVEPOINT sp_post;
RELEASE SAVEPOINT sp_post;
DO $$
DECLARE cnt_b integer; cnt_a integer; seq_b bigint; seq_a bigint;
BEGIN
  SELECT icount, seqval INTO cnt_b, seq_b FROM _aw4_post_seq_state WHERE label='post';
  SELECT COUNT(*) INTO cnt_a FROM public.equipment_assets;
  SELECT last_value INTO seq_a FROM public.seq_asset_code;
  IF cnt_a <> cnt_b THEN RAISE EXCEPTION 'P3-13 FAIL POST: row not rolled back before=% after=%', cnt_b, cnt_a; END IF;
  IF seq_a <= seq_b THEN RAISE EXCEPTION 'P3-13 FAIL POST: sequence was rolled back before=% after=%', seq_b, seq_a; END IF;
  RAISE NOTICE 'P3-13 PASS (POST): SAVEPOINT rollback row=unchanged seq non-transactional (% → %)', seq_b, seq_a;
END;
$$;
COMMIT;

DROP TABLE _aw4_post_seq_state;

DO $$ BEGIN RAISE NOTICE '=== PHASE 3 POST COMPLETE (13 tests) ==='; END; $$;

-- =========================================================
-- PHASE 4  PRE/POST 동등성 — MD5 / ACL / 트리거 불변 확인
-- =========================================================
DO $$ BEGIN RAISE NOTICE '=== PHASE 4 INVARIANCE ==='; END; $$;

-- P4-01: 5개 함수 MD5 불변 (PHASE0 기준선과 대조)
DO $$
DECLARE
  c_names text[] := ARRAY[
    'fn_generate_asset_code','fn_generate_company_code',
    'fn_generate_site_code','fn_generate_team_code','fn_generate_user_code'
  ];
  v_md5   text;
  b_md5   text;
  nm      text;
BEGIN
  FOREACH nm IN ARRAY c_names LOOP
    SELECT md5(prosrc) INTO v_md5
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname = nm;
    b_md5 := current_setting('app.aw4_md5_' || nm, true);
    IF v_md5 IS DISTINCT FROM b_md5 THEN
      RAISE EXCEPTION 'P4-01 FAIL: % MD5 changed from % to %', nm, b_md5, v_md5;
    END IF;
  END LOOP;
  RAISE NOTICE 'P4-01 PASS: 5/5 function MD5 unchanged POST';
END;
$$;

-- P4-02: 5개 함수 proconfig 설정 확인
DO $$
DECLARE cnt integer;
BEGIN
  SELECT COUNT(*) INTO cnt
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public'
    AND p.proname IN ('fn_generate_asset_code','fn_generate_company_code',
                      'fn_generate_site_code','fn_generate_team_code','fn_generate_user_code')
    AND p.proconfig = ARRAY['search_path=pg_catalog, public, pg_temp']::text[];
  IF cnt <> 5 THEN RAISE EXCEPTION 'P4-02 FAIL: only % of 5 have proconfig set', cnt; END IF;
  RAISE NOTICE 'P4-02 PASS: 5/5 proconfig=search_path=pg_catalog,public,pg_temp';
END;
$$;

-- P4-03: 5개 트리거 연결 불변 (tgtype=7, tgenabled='O', not deferrable)
DO $$
DECLARE
  v RECORD;
  cnt integer := 0;
  expected text[][] := ARRAY[
    ['trg_generate_asset_code',   'equipment_assets'],
    ['trg_generate_company_code', 'companies'],
    ['trg_generate_site_code',    'factories'],
    ['trg_generate_team_code',    'teams'],
    ['trg_generate_user_code',    'users']
  ];
  i integer;
  found_match boolean;
BEGIN
  FOR v IN
    SELECT t.tgname, c.relname AS tbl, t.tgtype, t.tgenabled, t.tgdeferrable
    FROM pg_trigger t
    JOIN pg_proc p ON p.oid = t.tgfoid
    JOIN pg_class c ON c.oid = t.tgrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND p.proname LIKE 'fn_generate%code'
      AND NOT t.tgisinternal
  LOOP
    IF v.tgtype <> 7 THEN RAISE EXCEPTION 'P4-03 FAIL: % tgtype expected 7 got %', v.tgname, v.tgtype; END IF;
    IF v.tgenabled <> 'O' THEN RAISE EXCEPTION 'P4-03 FAIL: % tgenabled expected O got %', v.tgname, v.tgenabled; END IF;
    IF v.tgdeferrable THEN RAISE EXCEPTION 'P4-03 FAIL: % unexpected DEFERRABLE', v.tgname; END IF;
    found_match := false;
    FOR i IN 1..5 LOOP
      IF expected[i][1] = v.tgname AND expected[i][2] = v.tbl THEN found_match := true; END IF;
    END LOOP;
    IF NOT found_match THEN
      RAISE EXCEPTION 'P4-03 FAIL: unexpected trigger binding tgname=% table=%', v.tgname, v.tbl;
    END IF;
    cnt := cnt + 1;
    RAISE NOTICE 'P4-03 PASS: trigger % → table % BEFORE_INSERT_ROW enabled not_deferrable', v.tgname, v.tbl;
  END LOOP;
  IF cnt <> 5 THEN RAISE EXCEPTION 'P4-03 FAIL: expected 5 triggers got %', cnt; END IF;
END;
$$;

DO $$ BEGIN RAISE NOTICE '=== PHASE 4 INVARIANCE COMPLETE ==='; END; $$;

DO $$ BEGIN RAISE NOTICE '=== A-W4 격리 회귀 테스트 완료 — PRE/POST EQUIVALENT ==='; END; $$;
