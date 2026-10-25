-- Migration: 20261025060000_sec_searchpath_rem97_cw1_search_index.sql
-- WO: WO-TAI-SEC-SEARCHPATH-REM97-CW1-C3-SOURCE-001
-- SEC SEARCHPATH REM97 C-W1 — 검색 인덱스 관련 함수 5건 search_path 고정
--
-- 대상:
--   public.enqueue_search_index_sync(text,text,text,text,text)          OID=303180
--   public.claim_search_index_events(text,integer,integer)               OID=303181
--   public.complete_search_index_event(bigint,text)                      OID=303182
--   public.fail_search_index_event(bigint,text,text,integer,integer)     OID=303183
--   public.requeue_search_index_event(bigint,text,integer,text)          OID=303184
--
-- 변경 범위:
--   ALTER FUNCTION ... SET search_path = pg_catalog, public, pg_temp
--   함수 본문·ACL·SECURITY INVOKER·Volatility·Parallel 변경 없음
--   5건 모두 public.search_index_outbox 명시적 schema-qualified 참조
--
-- 승인:
--   D-01~D-04 Owner 승인: 2026-10-25
--   WO-TAI-SEC-SEARCHPATH-REM97-CW1-C3-SOURCE-001 OWNER_APPROVAL=APPROVED: 2026-10-25
--
-- 참조:
--   GPT_REM97_C20_C2_R1_IV = CONDITIONAL_PASS_C3_TEST_GATE
--   C-W1 (검색 인덱스 5건) — Outbox 상태 관리 RPC

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1: PRE 기준선 검증 (5건)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_sigs    CONSTANT text[] := ARRAY[
    'public.enqueue_search_index_sync(text,text,text,text,text)',
    'public.claim_search_index_events(text,integer,integer)',
    'public.complete_search_index_event(bigint,text)',
    'public.fail_search_index_event(bigint,text,text,integer,integer)',
    'public.requeue_search_index_event(bigint,text,integer,text)'
  ];
  c_oids    CONSTANT oid[]  := ARRAY[303180, 303181, 303182, 303183, 303184]::oid[];
  c_md5s    CONSTANT text[] := ARRAY[
    '7d8b51f36863d9db97c7ca7697698cfc',
    '3bf08de5bac6052dae0f3fa443c8848b',
    '93972b922b6586b1c08919cc440ff5e3',
    'bd91ea673e17a08dc2992eec23f7467f',
    'bce20988f05bf91251c0976e0e520629'
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
  FOR i IN 1..5 LOOP
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
    RAISE NOTICE 'PRE OK [%/5]: % OID=% MD5=% INVOKER owner=postgres proconfig=NULL',
      i, c_sigs[i], c_oids[i], c_md5s[i];
  END LOOP;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1B: PRE ACL 스냅샷
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TEMP TABLE _cw1_acl_baseline (
  fn_oid  oid  PRIMARY KEY,
  proacl  text
) ON COMMIT DROP;

INSERT INTO _cw1_acl_baseline (fn_oid, proacl)
SELECT p.oid, p.proacl::text
FROM pg_proc p
WHERE p.oid IN (303180, 303181, 303182, 303183, 303184);

DO $$
DECLARE v_count int;
BEGIN
  SELECT COUNT(*) INTO v_count FROM _cw1_acl_baseline;
  IF v_count IS DISTINCT FROM 5 THEN
    RAISE EXCEPTION 'PRE FAILED: ACL baseline captured % rows, expected 5.', v_count;
  END IF;
  RAISE NOTICE 'PRE ACL SNAPSHOT OK: 5 rows captured';
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 2: search_path 고정 (5건 — METADATA_ONLY)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER FUNCTION public.enqueue_search_index_sync(text, text, text, text, text)
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.claim_search_index_events(text, integer, integer)
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.complete_search_index_event(bigint, text)
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.fail_search_index_event(bigint, text, text, integer, integer)
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.requeue_search_index_event(bigint, text, integer, text)
  SET search_path = pg_catalog, public, pg_temp;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3: POST 검증 (5건)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_sigs        CONSTANT text[] := ARRAY[
    'public.enqueue_search_index_sync(text,text,text,text,text)',
    'public.claim_search_index_events(text,integer,integer)',
    'public.complete_search_index_event(bigint,text)',
    'public.fail_search_index_event(bigint,text,text,integer,integer)',
    'public.requeue_search_index_event(bigint,text,integer,text)'
  ];
  c_oids        CONSTANT oid[]  := ARRAY[303180, 303181, 303182, 303183, 303184]::oid[];
  c_md5s        CONSTANT text[] := ARRAY[
    '7d8b51f36863d9db97c7ca7697698cfc',
    '3bf08de5bac6052dae0f3fa443c8848b',
    '93972b922b6586b1c08919cc440ff5e3',
    'bd91ea673e17a08dc2992eec23f7467f',
    'bce20988f05bf91251c0976e0e520629'
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
  FOR i IN 1..5 LOOP
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
    RAISE NOTICE 'POST OK [%/5]: % proconfig=[%] MD5=% OID=%',
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
  FOR r IN SELECT fn_oid, proacl FROM _cw1_acl_baseline ORDER BY fn_oid LOOP
    SELECT p.proacl::text INTO v_proacl FROM pg_proc p WHERE p.oid = r.fn_oid;
    IF v_proacl IS DISTINCT FROM r.proacl THEN
      RAISE EXCEPTION 'POST FAILED: ACL changed for OID % (before=%, after=%).',
        r.fn_oid, r.proacl, v_proacl;
    END IF;
  END LOOP;
  RAISE NOTICE 'POST ACL OK: ACL unchanged for 5 C-W1 functions';
END;
$$;

COMMIT;
