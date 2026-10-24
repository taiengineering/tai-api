-- Migration: 20261023124050_sec_searchpath_rem97_w3_cycle_guard_functions.sql
-- WO: WO-TAI-SEC-SEARCHPATH-REM97-C3-W3-SOURCE-001
-- SEC SEARCHPATH REM97 W3 — 도움말 순환 방지 트리거 함수 2개 search_path 고정
--
-- 배경:
--   A-그룹 W3 대상 2개 함수: 모두 SECURITY INVOKER, proconfig=NULL
--   → function_search_path_mutable Advisor 경고 85건 중 W3 2건 해소 (85→83).
--   함수 본문은 순환 참조 방지 순수 연산으로 search_path 고정이 동작에 영향 없음
--   (METADATA_ONLY).
--
-- 변경 범위:
--   ALTER FUNCTION ... SET search_path = pg_catalog, public, pg_temp (2건).
--   함수 본문·ACL·SECURITY INVOKER·Volatility·Parallel 속성 변경 없음.
--   트리거 정의·활성 상태 변경 없음.
--
-- 참조:
--   20261023082048_sec_searchpath_rem97_w2_utility_functions.sql
--   C2 설계: WO-TAI-SEC-SEARCHPATH-REM97-C2-DESIGN-001 / CLOSED_WITH_W4_HOLD
--   C1 기준: WO-TAI-SEC-SEARCHPATH-REM97-C1 CLOSED_FINAL (97건 / A=20 / W3=2)

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1: PRE 조건 검증
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  -- ACL 기준선 (2개 함수 동일)
  c_acl_baseline CONSTANT text :=
    '{=X/postgres,postgres=X/postgres,anon=X/postgres,authenticated=X/postgres,service_role=X/postgres}';

  -- 함수별 기대값 (fn_sig, expected_oid, expected_prosrc_md5)
  v_fn_sigs  text[]  := ARRAY[
    'public.help_doc_no_include_cycle()',
    'public.help_node_no_cycle()'
  ];
  v_oids     oid[]   := ARRAY[246456, 246423];
  v_md5s     text[]  := ARRAY[
    'e4707fa3c5fcd447c9b900e29a9b55e3',
    '9f0f34ca03105dd05ace9815bbbafc8b'
  ];

  i           int;
  v_fn_sig    text;
  v_oid       oid;
  v_secdef    bool;
  v_owner     text;
  v_body_md5  text;
  v_proconfig text[];
  v_proacl    text;
  v_volat     char;
  v_parallel  char;

BEGIN
  FOR i IN 1..array_length(v_fn_sigs, 1) LOOP
    v_fn_sig := v_fn_sigs[i];

    -- 1-a. 함수 존재 확인
    IF to_regprocedure(v_fn_sig) IS NULL THEN
      RAISE EXCEPTION 'PRE FAILED: % not found.', v_fn_sig;
    END IF;

    v_oid := to_regprocedure(v_fn_sig)::oid;

    -- 1-b. OID 기준선 확인
    IF v_oid IS DISTINCT FROM v_oids[i] THEN
      RAISE EXCEPTION 'PRE FAILED: % OID mismatch (expected %, got %).', v_fn_sig, v_oids[i], v_oid;
    END IF;

    -- 1-c. SECURITY INVOKER 확인
    SELECT p.prosecdef INTO v_secdef FROM pg_proc p WHERE p.oid = v_oid;
    IF v_secdef IS DISTINCT FROM false THEN
      RAISE EXCEPTION 'PRE FAILED: % is not SECURITY INVOKER.', v_fn_sig;
    END IF;

    -- 1-d. 소유자 = postgres
    SELECT pg_get_userbyid(p.proowner) INTO v_owner FROM pg_proc p WHERE p.oid = v_oid;
    IF v_owner IS DISTINCT FROM 'postgres' THEN
      RAISE EXCEPTION 'PRE FAILED: % owner is %, expected postgres.', v_fn_sig, v_owner;
    END IF;

    -- 1-e. 함수 본문 MD5 기준선
    SELECT md5(p.prosrc) INTO v_body_md5 FROM pg_proc p WHERE p.oid = v_oid;
    IF v_body_md5 IS DISTINCT FROM v_md5s[i] THEN
      RAISE EXCEPTION 'PRE FAILED: % prosrc_md5 mismatch (expected %, got %).', v_fn_sig, v_md5s[i], v_body_md5;
    END IF;

    -- 1-f. proconfig = NULL (아직 미적용)
    SELECT p.proconfig INTO v_proconfig FROM pg_proc p WHERE p.oid = v_oid;
    IF v_proconfig IS NOT NULL THEN
      RAISE EXCEPTION 'PRE FAILED: % proconfig already set: %.', v_fn_sig, v_proconfig;
    END IF;

    -- 1-g. anon EXECUTE = TRUE
    IF NOT has_function_privilege('anon', v_fn_sig, 'EXECUTE') THEN
      RAISE EXCEPTION 'PRE FAILED: anon does not have EXECUTE on %.', v_fn_sig;
    END IF;

    -- 1-h. authenticated EXECUTE = TRUE
    IF NOT has_function_privilege('authenticated', v_fn_sig, 'EXECUTE') THEN
      RAISE EXCEPTION 'PRE FAILED: authenticated does not have EXECUTE on %.', v_fn_sig;
    END IF;

    -- 1-i. 전체 ACL 기준선
    SELECT p.proacl::text INTO v_proacl FROM pg_proc p WHERE p.oid = v_oid;
    IF v_proacl IS DISTINCT FROM c_acl_baseline THEN
      RAISE EXCEPTION 'PRE FAILED: % ACL mismatch (got %).', v_fn_sig, v_proacl;
    END IF;

    -- 1-j. Volatility 기준선 (v = VOLATILE)
    SELECT p.provolatile INTO v_volat FROM pg_proc p WHERE p.oid = v_oid;
    IF v_volat IS DISTINCT FROM 'v' THEN
      RAISE EXCEPTION 'PRE FAILED: % volatility mismatch (expected v, got %).', v_fn_sig, v_volat;
    END IF;

    -- 1-k. Parallel 기준선 (u = UNSAFE)
    SELECT p.proparallel INTO v_parallel FROM pg_proc p WHERE p.oid = v_oid;
    IF v_parallel IS DISTINCT FROM 'u' THEN
      RAISE EXCEPTION 'PRE FAILED: % proparallel is %, expected u.', v_fn_sig, v_parallel;
    END IF;

  END LOOP;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1B: PRE 트리거 식별자·정의 기준선 검증 (2건)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_tg_names text[] := ARRAY[
    'help_doc_no_include_cycle_trg',
    'help_node_no_cycle_trg'
  ];
  v_tg_fns   text[] := ARRAY[
    'help_doc_no_include_cycle',
    'help_node_no_cycle'
  ];
  v_tg_md5s  text[] := ARRAY[
    '5dfd34dce1196d9dc124d2e60eeb7afc',
    '78df84a85f863bdd1e44a7bef2e98c8a'
  ];

  i            int;
  v_actual_md5 text;
  v_enabled    char;

BEGIN
  FOR i IN 1..array_length(v_tg_names, 1) LOOP
    SELECT md5(pg_get_triggerdef(t.oid)), t.tgenabled
    INTO v_actual_md5, v_enabled
    FROM pg_trigger t
    JOIN pg_proc p ON t.tgfoid = p.oid
    JOIN pg_namespace n ON p.pronamespace = n.oid
    WHERE t.tgname = v_tg_names[i]
      AND p.proname = v_tg_fns[i]
      AND n.nspname = 'public';

    IF v_actual_md5 IS NULL THEN
      RAISE EXCEPTION 'PRE FAILED: trigger % for %() not found.',
        v_tg_names[i], v_tg_fns[i];
    END IF;
    IF v_enabled IS DISTINCT FROM 'O' THEN
      RAISE EXCEPTION 'PRE FAILED: trigger % is not enabled (tgenabled=%).',
        v_tg_names[i], v_enabled;
    END IF;
    IF v_actual_md5 IS DISTINCT FROM v_tg_md5s[i] THEN
      RAISE EXCEPTION 'PRE FAILED: trigger % definition changed (expected %, got %).',
        v_tg_names[i], v_tg_md5s[i], v_actual_md5;
    END IF;

  END LOOP;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1C: PRE W2 의존 함수 설정 유지 확인
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_proconfig text[];
BEGIN
  SELECT p.proconfig INTO v_proconfig
  FROM pg_proc p
  WHERE p.oid = to_regprocedure('public.help_doc_include_refs(jsonb)');

  IF v_proconfig IS DISTINCT FROM ARRAY['search_path=pg_catalog, public, pg_temp']::text[] THEN
    RAISE EXCEPTION 'PRE FAILED: W2 help_doc_include_refs proconfig unexpected (got %).', v_proconfig;
  END IF;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 2: search_path 고정 (METADATA_ONLY — 함수 본문·트리거·ACL 변경 없음)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER FUNCTION public.help_doc_no_include_cycle()
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.help_node_no_cycle()
  SET search_path = pg_catalog, public, pg_temp;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3: POST 조건 검증
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_acl_baseline  CONSTANT text :=
    '{=X/postgres,postgres=X/postgres,anon=X/postgres,authenticated=X/postgres,service_role=X/postgres}';
  c_search_path   CONSTANT text := 'search_path=pg_catalog, public, pg_temp';

  v_fn_sigs  text[]  := ARRAY[
    'public.help_doc_no_include_cycle()',
    'public.help_node_no_cycle()'
  ];
  v_oids     oid[]   := ARRAY[246456, 246423];
  v_md5s     text[]  := ARRAY[
    'e4707fa3c5fcd447c9b900e29a9b55e3',
    '9f0f34ca03105dd05ace9815bbbafc8b'
  ];

  i           int;
  v_fn_sig    text;
  v_oid       oid;
  v_secdef    bool;
  v_owner     text;
  v_body_md5  text;
  v_proconfig text[];
  v_proacl    text;
  v_volat     char;
  v_parallel  char;

BEGIN
  FOR i IN 1..array_length(v_fn_sigs, 1) LOOP
    v_fn_sig := v_fn_sigs[i];
    v_oid    := v_oids[i];

    -- 3-a. OID 불변 확인
    IF to_regprocedure(v_fn_sig)::oid IS DISTINCT FROM v_oid THEN
      RAISE EXCEPTION 'POST FAILED: % OID changed unexpectedly.', v_fn_sig;
    END IF;

    -- 3-b. proconfig 정확 일치 확인 (NULL-safe, 추가 설정 불허)
    SELECT p.proconfig INTO v_proconfig FROM pg_proc p WHERE p.oid = v_oid;
    IF v_proconfig IS DISTINCT FROM ARRAY[c_search_path]::text[] THEN
      RAISE EXCEPTION 'POST FAILED: % unexpected proconfig: %.', v_fn_sig, v_proconfig;
    END IF;

    -- 3-c. 함수 본문 MD5 불변 확인
    SELECT md5(p.prosrc) INTO v_body_md5 FROM pg_proc p WHERE p.oid = v_oid;
    IF v_body_md5 IS DISTINCT FROM v_md5s[i] THEN
      RAISE EXCEPTION 'POST FAILED: % prosrc_md5 changed (expected %, got %).', v_fn_sig, v_md5s[i], v_body_md5;
    END IF;

    -- 3-d. SECURITY INVOKER 불변
    SELECT p.prosecdef INTO v_secdef FROM pg_proc p WHERE p.oid = v_oid;
    IF v_secdef IS DISTINCT FROM false THEN
      RAISE EXCEPTION 'POST FAILED: % prosecdef changed.', v_fn_sig;
    END IF;

    -- 3-e. 소유자 불변
    SELECT pg_get_userbyid(p.proowner) INTO v_owner FROM pg_proc p WHERE p.oid = v_oid;
    IF v_owner IS DISTINCT FROM 'postgres' THEN
      RAISE EXCEPTION 'POST FAILED: % owner changed (got %).', v_fn_sig, v_owner;
    END IF;

    -- 3-f. ACL 불변
    SELECT p.proacl::text INTO v_proacl FROM pg_proc p WHERE p.oid = v_oid;
    IF v_proacl IS DISTINCT FROM c_acl_baseline THEN
      RAISE EXCEPTION 'POST FAILED: % ACL changed (got %).', v_fn_sig, v_proacl;
    END IF;

    -- 3-g. Volatility 불변
    SELECT p.provolatile INTO v_volat FROM pg_proc p WHERE p.oid = v_oid;
    IF v_volat IS DISTINCT FROM 'v' THEN
      RAISE EXCEPTION 'POST FAILED: % volatility changed (got %).', v_fn_sig, v_volat;
    END IF;

    -- 3-h. Parallel 불변 (u = UNSAFE)
    SELECT p.proparallel INTO v_parallel FROM pg_proc p WHERE p.oid = v_oid;
    IF v_parallel IS DISTINCT FROM 'u' THEN
      RAISE EXCEPTION 'POST FAILED: % proparallel changed (got %).', v_fn_sig, v_parallel;
    END IF;

  END LOOP;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3B: POST 트리거 불변 검증 (2건)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_tg_names text[] := ARRAY[
    'help_doc_no_include_cycle_trg',
    'help_node_no_cycle_trg'
  ];
  v_tg_fns   text[] := ARRAY[
    'help_doc_no_include_cycle',
    'help_node_no_cycle'
  ];
  v_tg_md5s  text[] := ARRAY[
    '5dfd34dce1196d9dc124d2e60eeb7afc',
    '78df84a85f863bdd1e44a7bef2e98c8a'
  ];

  i            int;
  v_actual_md5 text;
  v_enabled    char;

BEGIN
  FOR i IN 1..array_length(v_tg_names, 1) LOOP
    SELECT md5(pg_get_triggerdef(t.oid)), t.tgenabled
    INTO v_actual_md5, v_enabled
    FROM pg_trigger t
    JOIN pg_proc p ON t.tgfoid = p.oid
    JOIN pg_namespace n ON p.pronamespace = n.oid
    WHERE t.tgname = v_tg_names[i]
      AND p.proname = v_tg_fns[i]
      AND n.nspname = 'public';

    IF v_actual_md5 IS NULL THEN
      RAISE EXCEPTION 'POST FAILED: trigger % for %() not found.',
        v_tg_names[i], v_tg_fns[i];
    END IF;
    IF v_enabled IS DISTINCT FROM 'O' THEN
      RAISE EXCEPTION 'POST FAILED: trigger % became disabled (tgenabled=%).',
        v_tg_names[i], v_enabled;
    END IF;
    IF v_actual_md5 IS DISTINCT FROM v_tg_md5s[i] THEN
      RAISE EXCEPTION 'POST FAILED: trigger % definition changed (expected %, got %).',
        v_tg_names[i], v_tg_md5s[i], v_actual_md5;
    END IF;

  END LOOP;
END;
$$;

COMMIT;
