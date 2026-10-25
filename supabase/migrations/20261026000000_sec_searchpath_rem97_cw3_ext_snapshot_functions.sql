-- Migration: 20261026000000_sec_searchpath_rem97_cw3_ext_snapshot_functions.sql
-- WO: WO-TAI-SEC-SEARCHPATH-REM97-CW3
-- SEC SEARCHPATH REM97 C-W3 — ext snapshot 함수 9건 search_path 고정
--
-- 대상:
--   public.fn_ext037_save_page_checkpoint(uuid,jsonb,integer,integer,uuid)   OID=315316
--   public.fn_ext037_complete_snapshot(uuid,text,integer,text,uuid)           OID=315317
--   public.fn_ext037_fail_snapshot(uuid,uuid,text)                            OID=315318
--   public.fn_ext132_save_page_checkpoint(uuid,jsonb,integer,integer,uuid)   OID=315202
--   public.fn_ext132_complete_snapshot(uuid,text,integer,text,uuid)           OID=315203
--   public.fn_ext132_fail_snapshot(uuid,uuid,text)                            OID=315205
--   public.fn_ext165_save_page_checkpoint(uuid,jsonb,integer,integer,uuid)   OID=315245
--   public.fn_ext165_complete_snapshot(uuid,text,integer,text,uuid)           OID=315246
--   public.fn_ext165_fail_snapshot(uuid,uuid,text)                            OID=315248
--
-- 변경 범위:
--   ALTER FUNCTION ... SET search_path = pg_catalog, public, pg_temp
--   함수 본문·ACL·SECURITY INVOKER·Volatility·Parallel 변경 없음
--   9건 모두 ext 스냅샷 상태 관리 함수 (save_page_checkpoint / complete_snapshot / fail_snapshot)
--
-- 참조:
--   WO-TAI-SEC-SEARCHPATH-REM97-C1 패턴 동일 적용
--   Owner=postgres, SECURITY INVOKER, VOLATILE, PARALLEL UNSAFE, proconfig=NULL (before)

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1: PRE 기준선 검증 (9건)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_sigs    CONSTANT text[] := ARRAY[
    'public.fn_ext037_save_page_checkpoint(uuid,jsonb,integer,integer,uuid)',
    'public.fn_ext037_complete_snapshot(uuid,text,integer,text,uuid)',
    'public.fn_ext037_fail_snapshot(uuid,uuid,text)',
    'public.fn_ext132_save_page_checkpoint(uuid,jsonb,integer,integer,uuid)',
    'public.fn_ext132_complete_snapshot(uuid,text,integer,text,uuid)',
    'public.fn_ext132_fail_snapshot(uuid,uuid,text)',
    'public.fn_ext165_save_page_checkpoint(uuid,jsonb,integer,integer,uuid)',
    'public.fn_ext165_complete_snapshot(uuid,text,integer,text,uuid)',
    'public.fn_ext165_fail_snapshot(uuid,uuid,text)'
  ];
  c_oids    CONSTANT oid[]  := ARRAY[315316, 315317, 315318, 315202, 315203, 315205, 315245, 315246, 315248]::oid[];
  c_md5s    CONSTANT text[] := ARRAY[
    '89d86835890a4a7bdbd712ab431e0746',
    'c03b87ddbfb01b137d68a6cc2b350223',
    'e1d00622503e4ff2fdb2f09b6eaf84e9',
    'c68f9bfc7c556ce9c339d55190617170',
    'be2ee6fc5fed2493bfe7674ab532f6d1',
    '193380895c5530681bfafbdfe28e651f',
    'e90551faa88fd415485c1561b9e072d5',
    'f94c2f16eab6fb866fb97a2ad9f37b0a',
    'b11e9c3f4be9eab0c57e0504b5155f98'
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
  FOR i IN 1..9 LOOP
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
    RAISE NOTICE 'PRE OK [%/9]: % OID=% MD5=% INVOKER owner=postgres proconfig=NULL',
      i, c_sigs[i], c_oids[i], c_md5s[i];
  END LOOP;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1B: PRE ACL 스냅샷
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TEMP TABLE _cw3_acl_baseline (
  fn_oid  oid  PRIMARY KEY,
  proacl  text
) ON COMMIT DROP;

INSERT INTO _cw3_acl_baseline (fn_oid, proacl)
SELECT p.oid, p.proacl::text
FROM pg_proc p
WHERE p.oid IN (315316, 315317, 315318, 315202, 315203, 315205, 315245, 315246, 315248);

DO $$
DECLARE v_count int;
BEGIN
  SELECT COUNT(*) INTO v_count FROM _cw3_acl_baseline;
  IF v_count IS DISTINCT FROM 9 THEN
    RAISE EXCEPTION 'PRE FAILED: ACL baseline captured % rows, expected 9.', v_count;
  END IF;
  RAISE NOTICE 'PRE ACL SNAPSHOT OK: 9 rows captured';
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 2: search_path 고정 (9건 — METADATA_ONLY)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER FUNCTION public.fn_ext037_save_page_checkpoint(uuid, jsonb, integer, integer, uuid)
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.fn_ext037_complete_snapshot(uuid, text, integer, text, uuid)
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.fn_ext037_fail_snapshot(uuid, uuid, text)
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.fn_ext132_save_page_checkpoint(uuid, jsonb, integer, integer, uuid)
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.fn_ext132_complete_snapshot(uuid, text, integer, text, uuid)
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.fn_ext132_fail_snapshot(uuid, uuid, text)
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.fn_ext165_save_page_checkpoint(uuid, jsonb, integer, integer, uuid)
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.fn_ext165_complete_snapshot(uuid, text, integer, text, uuid)
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.fn_ext165_fail_snapshot(uuid, uuid, text)
  SET search_path = pg_catalog, public, pg_temp;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3: POST 검증 (9건)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_sigs        CONSTANT text[] := ARRAY[
    'public.fn_ext037_save_page_checkpoint(uuid,jsonb,integer,integer,uuid)',
    'public.fn_ext037_complete_snapshot(uuid,text,integer,text,uuid)',
    'public.fn_ext037_fail_snapshot(uuid,uuid,text)',
    'public.fn_ext132_save_page_checkpoint(uuid,jsonb,integer,integer,uuid)',
    'public.fn_ext132_complete_snapshot(uuid,text,integer,text,uuid)',
    'public.fn_ext132_fail_snapshot(uuid,uuid,text)',
    'public.fn_ext165_save_page_checkpoint(uuid,jsonb,integer,integer,uuid)',
    'public.fn_ext165_complete_snapshot(uuid,text,integer,text,uuid)',
    'public.fn_ext165_fail_snapshot(uuid,uuid,text)'
  ];
  c_oids        CONSTANT oid[]  := ARRAY[315316, 315317, 315318, 315202, 315203, 315205, 315245, 315246, 315248]::oid[];
  c_md5s        CONSTANT text[] := ARRAY[
    '89d86835890a4a7bdbd712ab431e0746',
    'c03b87ddbfb01b137d68a6cc2b350223',
    'e1d00622503e4ff2fdb2f09b6eaf84e9',
    'c68f9bfc7c556ce9c339d55190617170',
    'be2ee6fc5fed2493bfe7674ab532f6d1',
    '193380895c5530681bfafbdfe28e651f',
    'e90551faa88fd415485c1561b9e072d5',
    'f94c2f16eab6fb866fb97a2ad9f37b0a',
    'b11e9c3f4be9eab0c57e0504b5155f98'
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
  FOR i IN 1..9 LOOP
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
    RAISE NOTICE 'POST OK [%/9]: % proconfig=[%] MD5=% OID=%',
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
  FOR r IN SELECT fn_oid, proacl FROM _cw3_acl_baseline ORDER BY fn_oid LOOP
    SELECT p.proacl::text INTO v_proacl FROM pg_proc p WHERE p.oid = r.fn_oid;
    IF v_proacl IS DISTINCT FROM r.proacl THEN
      RAISE EXCEPTION 'POST FAILED: ACL changed for OID % (before=%, after=%).',
        r.fn_oid, r.proacl, v_proacl;
    END IF;
  END LOOP;
  RAISE NOTICE 'POST ACL OK: ACL unchanged for 9 C-W3 functions';
END;
$$;

COMMIT;
