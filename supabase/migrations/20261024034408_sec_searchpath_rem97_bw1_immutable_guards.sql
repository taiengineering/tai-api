-- Migration: 20261024034408_sec_searchpath_rem97_bw1_immutable_guards.sql
-- WO: WO-TAI-SEC-SEARCHPATH-REM97-C2-BW1-SOURCE-001
-- SEC SEARCHPATH REM97 B-W1 — 불변 가드 함수 4개 search_path 고정
--
-- 배경:
--   B24 Source Gate CLOSED_FINAL (GPT_REM97_B24_SOURCE_R2_IV PASS_WITH_CORRECTIONS).
--   B-W1 대상 4개 함수: 모두 SECURITY INVOKER, proconfig=NULL.
--   → function_search_path_mutable Advisor 82건 중 B-W1 4건 해소 (82→78) 예정.
--   4개 함수 모두 순수 불변 가드 트리거 — 외부 테이블 DML·비한정 참조 없음
--   (METADATA_ONLY, 기존 동작 변경 없음).
--
-- 변경 범위:
--   ALTER FUNCTION public.fn_rdarch_reject_mutation()
--     SET search_path = pg_catalog, public, pg_temp  (B01)
--   ALTER FUNCTION public.fn_rdd_seal_guard()
--     SET search_path = pg_catalog, public, pg_temp  (B02)
--   ALTER FUNCTION public.fn_reject_inspection_base_mutation()
--     SET search_path = pg_catalog, public, pg_temp  (B03)
--   ALTER FUNCTION public.fn_reject_inspection_record_mutation()
--     SET search_path = pg_catalog, public, pg_temp  (B04)
--   함수 본문·ACL·SECURITY INVOKER·Volatility·Parallel·트리거 변경 없음.
--
-- 트리거 보존 (8개):
--   B01: trg_rdarch_no_delete, trg_rdarch_no_update (runtime_document_archive)
--   B02: trg_rdd_seal_guard (runtime_document_data)
--   B03: trg_safety_inspections_immutable, trg_safety_inspection_results_immutable
--        (safety_inspections / safety_inspection_results — 둘 다 ALWAYS)
--   B04: trg_sirj_append_only, trg_sicr_append_only, trg_sicreation_append_only
--        (record_journal / command_receipt / creation_receipt)
--
-- 참조:
--   20261024021404_sec_searchpath_rem97_w5_reindex_help.sql
--   C2 설계: WO-TAI-SEC-SEARCHPATH-REM97-C2-BW1-SOURCE-001
--   C1 기준: WO-TAI-SEC-SEARCHPATH-REM97-C1 CLOSED_FINAL (97건 / B=24 / B-W1=4)

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1: PRE 함수 기준선 검증
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_fn_sigs  text[]  := ARRAY[
    'public.fn_rdarch_reject_mutation()',
    'public.fn_rdd_seal_guard()',
    'public.fn_reject_inspection_base_mutation()',
    'public.fn_reject_inspection_record_mutation()'
  ];
  v_oids     oid[]   := ARRAY[247895, 247898, 250821, 250768];
  v_md5s     text[]  := ARRAY[
    '975ad08342e5d6add7584d1ee307c9a4',
    '85d5d5d06c9f153ebd6076076f1e956c',
    '1c21312b9ee8095ec7a0ec15c559e915',
    'e92d457621c2733c7d4bf93ca7356e30'
  ];

  i           int;
  v_fn_sig    text;
  v_oid       oid;
  v_secdef    bool;
  v_owner     text;
  v_body_md5  text;
  v_proconfig text[];
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

    -- 1-g. Volatility 기준선 (v = VOLATILE)
    SELECT p.provolatile INTO v_volat FROM pg_proc p WHERE p.oid = v_oid;
    IF v_volat IS DISTINCT FROM 'v' THEN
      RAISE EXCEPTION 'PRE FAILED: % volatility mismatch (expected v, got %).', v_fn_sig, v_volat;
    END IF;

    -- 1-h. Parallel 기준선 (u = UNSAFE)
    SELECT p.proparallel INTO v_parallel FROM pg_proc p WHERE p.oid = v_oid;
    IF v_parallel IS DISTINCT FROM 'u' THEN
      RAISE EXCEPTION 'PRE FAILED: % proparallel is %, expected u.', v_fn_sig, v_parallel;
    END IF;

  END LOOP;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1B: PRE ACL 기준선 스냅샷 (동적 캡처 — 트리거 함수는 anon/authenticated
--          직접 EXECUTE 부여 불필요; 실제 ACL 값을 POST 비교용으로 보존)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TEMP TABLE _bw1_fn_acl_baseline (
  fn_oid  oid  PRIMARY KEY,
  proacl  text
) ON COMMIT DROP;

INSERT INTO _bw1_fn_acl_baseline (fn_oid, proacl)
SELECT p.oid, p.proacl::text
FROM pg_proc p
WHERE p.oid IN (247895, 247898, 250821, 250768);

DO $$
DECLARE v_count int;
BEGIN
  SELECT COUNT(*) INTO v_count FROM _bw1_fn_acl_baseline;
  IF v_count IS DISTINCT FROM 4 THEN
    RAISE EXCEPTION 'PRE FAILED: ACL baseline captured % rows, expected 4.', v_count;
  END IF;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1C: PRE 트리거 기준선 스냅샷 (동적 캡처 — 8개)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TEMP TABLE _bw1_trig_baseline (
  tg_name    text NOT NULL,
  rel_name   text NOT NULL,
  tg_enabled char NOT NULL,
  tgdef_md5  text NOT NULL,
  PRIMARY KEY (tg_name, rel_name)
) ON COMMIT DROP;

INSERT INTO _bw1_trig_baseline (tg_name, rel_name, tg_enabled, tgdef_md5)
SELECT t.tgname, c.relname, t.tgenabled, md5(pg_get_triggerdef(t.oid))
FROM pg_trigger t
JOIN pg_proc p   ON t.tgfoid = p.oid
JOIN pg_namespace n ON p.pronamespace = n.oid
JOIN pg_class c  ON t.tgrelid = c.oid
WHERE n.nspname = 'public'
  AND p.proname IN (
    'fn_rdarch_reject_mutation',
    'fn_rdd_seal_guard',
    'fn_reject_inspection_base_mutation',
    'fn_reject_inspection_record_mutation'
  )
  AND NOT t.tgisinternal;

DO $$
DECLARE v_count int;
BEGIN
  SELECT COUNT(*) INTO v_count FROM _bw1_trig_baseline;
  IF v_count IS DISTINCT FROM 8 THEN
    RAISE EXCEPTION 'PRE FAILED: expected 8 triggers for B01~B04, found %.', v_count;
  END IF;
END;
$$;

-- B03 ALWAYS 트리거 2개 상태 확인
DO $$
DECLARE v_count int;
BEGIN
  SELECT COUNT(*) INTO v_count
  FROM _bw1_trig_baseline
  WHERE tg_name IN (
    'trg_safety_inspections_immutable',
    'trg_safety_inspection_results_immutable'
  )
    AND tg_enabled = 'A';
  IF v_count IS DISTINCT FROM 2 THEN
    RAISE EXCEPTION 'PRE FAILED: B03 ALWAYS 트리거가 2개(A상태)여야 하나 %개 발견.', v_count;
  END IF;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 2: search_path 고정 (METADATA_ONLY — 함수 본문·트리거·ACL 변경 없음)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER FUNCTION public.fn_rdarch_reject_mutation()
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.fn_rdd_seal_guard()
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.fn_reject_inspection_base_mutation()
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.fn_reject_inspection_record_mutation()
  SET search_path = pg_catalog, public, pg_temp;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3: POST 함수 검증
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_search_path  CONSTANT text := 'search_path=pg_catalog, public, pg_temp';

  v_fn_sigs  text[]  := ARRAY[
    'public.fn_rdarch_reject_mutation()',
    'public.fn_rdd_seal_guard()',
    'public.fn_reject_inspection_base_mutation()',
    'public.fn_reject_inspection_record_mutation()'
  ];
  v_oids     oid[]   := ARRAY[247895, 247898, 250821, 250768];
  v_md5s     text[]  := ARRAY[
    '975ad08342e5d6add7584d1ee307c9a4',
    '85d5d5d06c9f153ebd6076076f1e956c',
    '1c21312b9ee8095ec7a0ec15c559e915',
    'e92d457621c2733c7d4bf93ca7356e30'
  ];

  i           int;
  v_fn_sig    text;
  v_oid       oid;
  v_secdef    bool;
  v_owner     text;
  v_body_md5  text;
  v_proconfig text[];
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

    -- 3-b. proconfig 정확 일치 (NULL-safe, 추가 설정 불허)
    SELECT p.proconfig INTO v_proconfig FROM pg_proc p WHERE p.oid = v_oid;
    IF v_proconfig IS DISTINCT FROM ARRAY[c_search_path]::text[] THEN
      RAISE EXCEPTION 'POST FAILED: % unexpected proconfig: %.', v_fn_sig, v_proconfig;
    END IF;

    -- 3-c. 함수 본문 MD5 불변
    SELECT md5(p.prosrc) INTO v_body_md5 FROM pg_proc p WHERE p.oid = v_oid;
    IF v_body_md5 IS DISTINCT FROM v_md5s[i] THEN
      RAISE EXCEPTION 'POST FAILED: % prosrc_md5 changed.', v_fn_sig;
    END IF;

    -- 3-d. SECURITY INVOKER 불변
    SELECT p.prosecdef INTO v_secdef FROM pg_proc p WHERE p.oid = v_oid;
    IF v_secdef IS DISTINCT FROM false THEN
      RAISE EXCEPTION 'POST FAILED: % prosecdef changed.', v_fn_sig;
    END IF;

    -- 3-e. 소유자 불변
    SELECT pg_get_userbyid(p.proowner) INTO v_owner FROM pg_proc p WHERE p.oid = v_oid;
    IF v_owner IS DISTINCT FROM 'postgres' THEN
      RAISE EXCEPTION 'POST FAILED: % owner changed.', v_fn_sig;
    END IF;

    -- 3-f. Volatility 불변
    SELECT p.provolatile INTO v_volat FROM pg_proc p WHERE p.oid = v_oid;
    IF v_volat IS DISTINCT FROM 'v' THEN
      RAISE EXCEPTION 'POST FAILED: % volatility changed.', v_fn_sig;
    END IF;

    -- 3-g. Parallel 불변
    SELECT p.proparallel INTO v_parallel FROM pg_proc p WHERE p.oid = v_oid;
    IF v_parallel IS DISTINCT FROM 'u' THEN
      RAISE EXCEPTION 'POST FAILED: % proparallel changed.', v_fn_sig;
    END IF;

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
  FOR r IN SELECT fn_oid, proacl FROM _bw1_fn_acl_baseline LOOP
    SELECT p.proacl::text INTO v_proacl FROM pg_proc p WHERE p.oid = r.fn_oid;
    IF v_proacl IS DISTINCT FROM r.proacl THEN
      RAISE EXCEPTION 'POST FAILED: ACL changed for OID % (before=%, after=%).',
        r.fn_oid, r.proacl, v_proacl;
    END IF;
  END LOOP;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3C: POST 트리거 불변 검증 (8개 — MD5·활성 상태·수량)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  r                 record;
  v_current_md5     text;
  v_current_enabled char;
  v_count           int;
BEGIN
  -- 트리거 총 수 불변
  SELECT COUNT(*) INTO v_count
  FROM pg_trigger t
  JOIN pg_proc p   ON t.tgfoid = p.oid
  JOIN pg_namespace n ON p.pronamespace = n.oid
  WHERE n.nspname = 'public'
    AND p.proname IN (
      'fn_rdarch_reject_mutation',
      'fn_rdd_seal_guard',
      'fn_reject_inspection_base_mutation',
      'fn_reject_inspection_record_mutation'
    )
    AND NOT t.tgisinternal;
  IF v_count IS DISTINCT FROM 8 THEN
    RAISE EXCEPTION 'POST FAILED: trigger count changed (expected 8, got %).', v_count;
  END IF;

  -- 각 트리거 MD5·활성 상태 불변 (tg_name + rel_name 복합 식별)
  FOR r IN SELECT tg_name, rel_name, tg_enabled, tgdef_md5 FROM _bw1_trig_baseline LOOP
    SELECT md5(pg_get_triggerdef(t.oid)), t.tgenabled
    INTO v_current_md5, v_current_enabled
    FROM pg_trigger t
    JOIN pg_class c ON t.tgrelid = c.oid
    WHERE t.tgname = r.tg_name
      AND c.relname = r.rel_name
      AND NOT t.tgisinternal;

    IF v_current_md5 IS NULL THEN
      RAISE EXCEPTION 'POST FAILED: trigger % on table % not found.',
        r.tg_name, r.rel_name;
    END IF;
    IF v_current_md5 IS DISTINCT FROM r.tgdef_md5 THEN
      RAISE EXCEPTION 'POST FAILED: trigger % on % definition changed.',
        r.tg_name, r.rel_name;
    END IF;
    IF v_current_enabled IS DISTINCT FROM r.tg_enabled THEN
      RAISE EXCEPTION 'POST FAILED: trigger % on % enabled state changed (before=%, after=%).',
        r.tg_name, r.rel_name, r.tg_enabled, v_current_enabled;
    END IF;
  END LOOP;

  -- B03 ALWAYS 상태 재확인
  SELECT COUNT(*) INTO v_count
  FROM pg_trigger t
  JOIN pg_proc p ON t.tgfoid = p.oid
  JOIN pg_namespace n ON p.pronamespace = n.oid
  WHERE n.nspname = 'public'
    AND p.proname = 'fn_reject_inspection_base_mutation'
    AND t.tgenabled = 'A'
    AND NOT t.tgisinternal;
  IF v_count IS DISTINCT FROM 2 THEN
    RAISE EXCEPTION 'POST FAILED: B03 ALWAYS 트리거 수 변경 (expected 2, got %).', v_count;
  END IF;
END;
$$;

COMMIT;
