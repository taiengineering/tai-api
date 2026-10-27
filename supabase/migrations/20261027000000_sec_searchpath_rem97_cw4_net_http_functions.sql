-- Migration: 20261027000000_sec_searchpath_rem97_cw4_net_http_functions.sql
-- WO: WO-TAI-SEC-SEARCHPATH-REM97-CW4-C3-SOURCE-001
-- SEC SEARCHPATH REM97 C-W4 — net HTTP 함수 3건 search_path 고정
--
-- 대상:
--   public.collect_auto_qa_results()   OID=18553
--   public.daily_health_check()        OID=18555
--   public.send_auto_qa_requests()     OID=18574
--
-- 변경 범위:
--   ALTER FUNCTION ... SET search_path = pg_catalog, public, pg_temp
--   함수 본문·ACL·SECURITY INVOKER·Volatility·Parallel 변경 없음
--   net.* 참조는 모두 명시적 한정 — search_path 변경과 무관
--
-- 선행 Gate:
--   D02_RUNTIME_IV = CONDITIONAL_PASS
--   D02_OWNER_DECISION = A_APPROVED
--   SAME_DB_END_TO_END = UNVERIFIED_ACCEPTED
--
-- 참조:
--   WO-TAI-SEC-SEARCHPATH-REM97-CW3 패턴 동일 적용
--   Owner=postgres, SECURITY INVOKER, VOLATILE, PARALLEL UNSAFE, proconfig=NULL (before)

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1: PRE 기준선 검증 (3건)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_sigs    CONSTANT text[] := ARRAY[
    'public.collect_auto_qa_results()',
    'public.daily_health_check()',
    'public.send_auto_qa_requests()'
  ];
  c_oids    CONSTANT oid[]  := ARRAY[18553, 18555, 18574]::oid[];
  c_md5s    CONSTANT text[] := ARRAY[
    '43f43f91b3a21b9265010cd2c8c0c615',
    '6c2dc44e46fa7dc46c97028d9d20af41',
    'f7829e2463819ebd000836db971485d8'
  ];
  v_oid       oid;
  v_secdef    bool;
  v_owner     text;
  v_body_md5  text;
  v_proconfig text[];
  v_volat     char;
  v_parallel  char;
  i           int;
BEGIN
  FOR i IN 1..3 LOOP
    v_oid := to_regprocedure(c_sigs[i])::oid;
    IF v_oid IS NULL THEN
      RAISE EXCEPTION 'PRE FAILED: % not found.', c_sigs[i];
    END IF;
    IF v_oid IS DISTINCT FROM c_oids[i] THEN
      RAISE EXCEPTION 'PRE FAILED: % OID mismatch (expected %, got %).', c_sigs[i], c_oids[i], v_oid;
    END IF;
    SELECT p.prosecdef, pg_get_userbyid(p.proowner), md5(p.prosrc), p.proconfig, p.provolatile, p.proparallel
    INTO v_secdef, v_owner, v_body_md5, v_proconfig, v_volat, v_parallel
    FROM pg_proc p WHERE p.oid = v_oid;
    IF v_secdef IS DISTINCT FROM false THEN
      RAISE EXCEPTION 'PRE FAILED: % is not SECURITY INVOKER.', c_sigs[i];
    END IF;
    IF v_owner IS DISTINCT FROM 'postgres' THEN
      RAISE EXCEPTION 'PRE FAILED: % owner is %, expected postgres.', c_sigs[i], v_owner;
    END IF;
    IF v_body_md5 IS DISTINCT FROM c_md5s[i] THEN
      RAISE EXCEPTION 'PRE FAILED: % prosrc_md5 mismatch (expected %, got %).', c_sigs[i], c_md5s[i], v_body_md5;
    END IF;
    IF v_proconfig IS NOT NULL THEN
      RAISE EXCEPTION 'PRE FAILED: % proconfig already set: %.', c_sigs[i], v_proconfig;
    END IF;
    IF v_volat IS DISTINCT FROM 'v' THEN
      RAISE EXCEPTION 'PRE FAILED: % volatility is %, expected v (VOLATILE).', c_sigs[i], v_volat;
    END IF;
    IF v_parallel IS DISTINCT FROM 'u' THEN
      RAISE EXCEPTION 'PRE FAILED: % proparallel is %, expected u (UNSAFE).', c_sigs[i], v_parallel;
    END IF;
    RAISE NOTICE 'PRE OK [%/3]: % OID=% MD5=% INVOKER owner=postgres proconfig=NULL',
      i, c_sigs[i], c_oids[i], c_md5s[i];
  END LOOP;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1B: PRE ACL 스냅샷
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TEMP TABLE _cw4_acl_baseline (
  fn_oid  oid  PRIMARY KEY,
  proacl  text
) ON COMMIT DROP;

INSERT INTO _cw4_acl_baseline (fn_oid, proacl)
SELECT p.oid, p.proacl::text
FROM pg_proc p
WHERE p.oid IN (18553, 18555, 18574);

DO $$
DECLARE v_count int;
BEGIN
  SELECT COUNT(*) INTO v_count FROM _cw4_acl_baseline;
  IF v_count IS DISTINCT FROM 3 THEN
    RAISE EXCEPTION 'PRE FAILED: ACL baseline captured % rows, expected 3.', v_count;
  END IF;
  RAISE NOTICE 'PRE ACL SNAPSHOT OK: 3 rows captured';
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 2: search_path 고정 (3건 — METADATA_ONLY)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER FUNCTION public.collect_auto_qa_results()
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.daily_health_check()
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.send_auto_qa_requests()
  SET search_path = pg_catalog, public, pg_temp;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3: POST 검증 (3건)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_sigs        CONSTANT text[] := ARRAY[
    'public.collect_auto_qa_results()',
    'public.daily_health_check()',
    'public.send_auto_qa_requests()'
  ];
  c_oids        CONSTANT oid[]  := ARRAY[18553, 18555, 18574]::oid[];
  c_md5s        CONSTANT text[] := ARRAY[
    '43f43f91b3a21b9265010cd2c8c0c615',
    '6c2dc44e46fa7dc46c97028d9d20af41',
    'f7829e2463819ebd000836db971485d8'
  ];
  c_search_path CONSTANT text := 'search_path=pg_catalog, public, pg_temp';
  v_secdef    bool;
  v_owner     text;
  v_body_md5  text;
  v_proconfig text[];
  v_volat     char;
  v_parallel  char;
  i           int;
BEGIN
  FOR i IN 1..3 LOOP
    IF to_regprocedure(c_sigs[i])::oid IS DISTINCT FROM c_oids[i] THEN
      RAISE EXCEPTION 'POST FAILED: % OID changed.', c_sigs[i];
    END IF;
    SELECT p.prosecdef, pg_get_userbyid(p.proowner), md5(p.prosrc), p.proconfig, p.provolatile, p.proparallel
    INTO v_secdef, v_owner, v_body_md5, v_proconfig, v_volat, v_parallel
    FROM pg_proc p WHERE p.oid = c_oids[i];
    IF v_proconfig IS DISTINCT FROM ARRAY[c_search_path]::text[] THEN
      RAISE EXCEPTION 'POST FAILED: % proconfig mismatch: %.', c_sigs[i], v_proconfig;
    END IF;
    IF v_body_md5 IS DISTINCT FROM c_md5s[i] THEN
      RAISE EXCEPTION 'POST FAILED: % prosrc_md5 changed.', c_sigs[i];
    END IF;
    IF v_secdef IS DISTINCT FROM false THEN
      RAISE EXCEPTION 'POST FAILED: % prosecdef changed.', c_sigs[i];
    END IF;
    IF v_owner IS DISTINCT FROM 'postgres' THEN
      RAISE EXCEPTION 'POST FAILED: % owner changed.', c_sigs[i];
    END IF;
    IF v_volat IS DISTINCT FROM 'v' THEN
      RAISE EXCEPTION 'POST FAILED: % volatility changed.', c_sigs[i];
    END IF;
    IF v_parallel IS DISTINCT FROM 'u' THEN
      RAISE EXCEPTION 'POST FAILED: % proparallel changed.', c_sigs[i];
    END IF;
    RAISE NOTICE 'POST OK [%/3]: % proconfig=[%] MD5=% OID=%',
      i, c_sigs[i], c_search_path, c_md5s[i], c_oids[i];
  END LOOP;
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
  FOR r IN SELECT fn_oid, proacl FROM _cw4_acl_baseline ORDER BY fn_oid LOOP
    SELECT p.proacl::text INTO v_proacl FROM pg_proc p WHERE p.oid = r.fn_oid;
    IF v_proacl IS DISTINCT FROM r.proacl THEN
      RAISE EXCEPTION 'POST FAILED: ACL changed for OID % (before=%, after=%).',
        r.fn_oid, r.proacl, v_proacl;
    END IF;
  END LOOP;
  RAISE NOTICE 'POST ACL OK: ACL unchanged for 3 C-W4 functions';
END;
$$;

COMMIT;
