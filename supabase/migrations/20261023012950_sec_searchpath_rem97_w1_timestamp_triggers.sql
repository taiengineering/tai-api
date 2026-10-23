-- Migration: 20261023012950_sec_searchpath_rem97_w1_timestamp_triggers.sql
-- WO: WO-TAI-SEC-SEARCHPATH-REM97-C3-W1-SOURCE-001
-- GOAL: G-mvkal9vd-0008e5
-- SEC SEARCHPATH REM97 W1 — 타임스탬프 트리거 함수 8개 search_path 고정
--
-- 배경:
--   A-그룹 W1 대상 8개 함수: 모두 SECURITY INVOKER, proconfig=NULL
--   → function_search_path_mutable Advisor 경고 97건 중 W1 8건 해소.
--   함수 본문은 "NEW.updated_at := now(); RETURN NEW;" 패턴 (또는 동등)으로
--   search_path 고정이 동작에 영향 없음 (METADATA_ONLY).
--
-- 변경 범위:
--   ALTER FUNCTION ... SET search_path = pg_catalog, public, pg_temp (8건).
--   함수 본문, 트리거, ACL, SECURITY INVOKER 속성 변경 없음.
--
-- 참조:
--   20261022152140_sec_searchpath_p0c_ddl_helper_functions.sql
--   C2 설계: WO-TAI-SEC-SEARCHPATH-REM97-C2-DESIGN-001 / CLOSED_WITH_W4_HOLD
--   C1 기준: WO-TAI-SEC-SEARCHPATH-REM97-C1 CLOSED_FINAL (97건 / A=20 / W1=8)

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1: PRE 조건 검증
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  -- ACL 기준선 (8개 함수 동일)
  c_acl_baseline CONSTANT text :=
    '{=X/postgres,postgres=X/postgres,anon=X/postgres,authenticated=X/postgres,service_role=X/postgres}';

  -- 함수별 기대값 (proname, expected_oid, expected_prosrc_md5, expected_trigger_count)
  v_names   text[]  := ARRAY[
    'fn_set_updated_at',
    'set_updated_at',
    'help_touch_updated_at',
    'update_cmc_updated_at',
    'update_documents_timestamp',
    'update_timestamp',
    'update_updated_at_column',
    'tg_kosha_guide_body_touch'
  ];
  v_oids    oid[]   := ARRAY[18562, 29548, 246343, 79663, 18584, 18585, 18586, 231239];
  v_md5s    text[]  := ARRAY[
    'e48740bd35e2a9e17c5e8ae049421527',
    'ef6b2d76360a727c9d6479352655b7ba',
    '9cd5ec4496cf5a9c5a108e23d2551d06',
    '301a884953d37769916294bb60562e05',
    '5b733ab523bad442e4b10f836de9e4ba',
    '9b1889f56258bf9d6554213c05019c76',
    '301a884953d37769916294bb60562e05',
    'f8778fa84b849f96f2f2197b9a7b56fb'
  ];
  v_trigs   int[]   := ARRAY[1, 8, 2, 1, 1, 1, 2, 1];

  i          int;
  v_fn_sig   text;
  v_oid      oid;
  v_secdef   bool;
  v_owner    text;
  v_body_md5 text;
  v_proconfig text[];
  v_proacl   text;
  v_trig_cnt int;

BEGIN
  FOR i IN 1..array_length(v_names, 1) LOOP
    v_fn_sig := 'public.' || v_names[i] || '()';

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

    -- 1-j. 활성 트리거 수 기준선
    SELECT COUNT(*)::int INTO v_trig_cnt FROM pg_trigger t WHERE t.tgfoid = v_oid;
    IF v_trig_cnt IS DISTINCT FROM v_trigs[i] THEN
      RAISE EXCEPTION 'PRE FAILED: % trigger count mismatch (expected %, got %).', v_fn_sig, v_trigs[i], v_trig_cnt;
    END IF;

    -- 1-k. 연결 트리거 모두 활성 상태 확인 (tgenabled = 'O')
    IF EXISTS (
      SELECT 1 FROM pg_trigger t WHERE t.tgfoid = v_oid AND t.tgenabled IS DISTINCT FROM 'O'
    ) THEN
      RAISE EXCEPTION 'PRE FAILED: % has disabled trigger.', v_fn_sig;
    END IF;

  END LOOP;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1B: PRE 트리거 식별자·정의 기준선 검증 (17건)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  -- (trigger_name, function_name, triggerdef_md5) 기준선
  v_tg_names text[] := ARRAY[
    'trg_master_fields_updated_at',
    'help_doc_touch_trg',
    'help_node_touch_trg',
    'trg_inquiries_updated_at',
    'trg_rtc_updated',
    'trg_runtime_dependency_updated_at',
    'trg_runtime_doc_updated_at',
    'trg_runtime_evidence_updated_at',
    'trg_runtime_schedule_updated_at',
    'trg_runtime_task_updated_at',
    'trg_user_profile_updated_at',
    'trg_kosha_guide_body_touch',
    'trg_cmc_updated_at',
    'trg_documents_updated_at',
    'trg_update_master_products_elec',
    'trg_billing_keys_updated_at',
    'trg_subscriptions_updated_at'
  ];
  v_tg_fns  text[] := ARRAY[
    'fn_set_updated_at',
    'help_touch_updated_at',
    'help_touch_updated_at',
    'set_updated_at',
    'set_updated_at',
    'set_updated_at',
    'set_updated_at',
    'set_updated_at',
    'set_updated_at',
    'set_updated_at',
    'set_updated_at',
    'tg_kosha_guide_body_touch',
    'update_cmc_updated_at',
    'update_documents_timestamp',
    'update_timestamp',
    'update_updated_at_column',
    'update_updated_at_column'
  ];
  v_tg_md5s text[] := ARRAY[
    '31385e8917683003499dd127476c31a6',
    '78772ce5158e8420bd8877f468d7c39c',
    '1838c6df987051282aab56dc1496580a',
    '355aa6ccf67978e624832828205b6ae9',
    '30b73f8c98328db19ef52e0078e48c3e',
    'fd73431d0070cd82d8c04ea150b46ad6',
    '0fc2f219752ee5dc052e0ce3612d8f25',
    'afa49c17f779436b900523b845289dc8',
    'e0666511a85e9f1d193336d7890b012e',
    'db5e339add68d968f6ee38f3ddba97a8',
    'b8cbe767cc2b021ecf1f1d848195d801',
    '4765b011abd404a5a59f390db6232d33',
    '82fdc43c9bc7eb426a737f78c9274ffb',
    '47782aad0d163b8b0575bb8a56c9c842',
    'e5c63e70d5bba989e963f75b0d71baa3',
    'cee5dddfb63a3bfd4b85a265df912645',
    '3e4b19c7912516202eb46c0366df7069'
  ];

  i             int;
  v_actual_md5  text;
  v_enabled     char;

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
-- STEP 2: search_path 고정 (METADATA_ONLY — 함수 본문·트리거·ACL 변경 없음)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER FUNCTION public.fn_set_updated_at()
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.set_updated_at()
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.help_touch_updated_at()
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.update_cmc_updated_at()
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.update_documents_timestamp()
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.update_timestamp()
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.update_updated_at_column()
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.tg_kosha_guide_body_touch()
  SET search_path = pg_catalog, public, pg_temp;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3: POST 조건 검증
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_acl_baseline  CONSTANT text :=
    '{=X/postgres,postgres=X/postgres,anon=X/postgres,authenticated=X/postgres,service_role=X/postgres}';
  c_search_path   CONSTANT text := 'search_path=pg_catalog, public, pg_temp';

  v_names   text[]  := ARRAY[
    'fn_set_updated_at',
    'set_updated_at',
    'help_touch_updated_at',
    'update_cmc_updated_at',
    'update_documents_timestamp',
    'update_timestamp',
    'update_updated_at_column',
    'tg_kosha_guide_body_touch'
  ];
  v_oids    oid[]   := ARRAY[18562, 29548, 246343, 79663, 18584, 18585, 18586, 231239];
  v_md5s    text[]  := ARRAY[
    'e48740bd35e2a9e17c5e8ae049421527',
    'ef6b2d76360a727c9d6479352655b7ba',
    '9cd5ec4496cf5a9c5a108e23d2551d06',
    '301a884953d37769916294bb60562e05',
    '5b733ab523bad442e4b10f836de9e4ba',
    '9b1889f56258bf9d6554213c05019c76',
    '301a884953d37769916294bb60562e05',
    'f8778fa84b849f96f2f2197b9a7b56fb'
  ];
  v_trigs   int[]   := ARRAY[1, 8, 2, 1, 1, 1, 2, 1];

  i          int;
  v_fn_sig   text;
  v_oid      oid;
  v_secdef   bool;
  v_owner    text;
  v_body_md5 text;
  v_proconfig text[];
  v_proacl   text;
  v_trig_cnt int;

BEGIN
  FOR i IN 1..array_length(v_names, 1) LOOP
    v_fn_sig := 'public.' || v_names[i] || '()';
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

    -- 3-g. 트리거 수 불변
    SELECT COUNT(*)::int INTO v_trig_cnt FROM pg_trigger t WHERE t.tgfoid = v_oid;
    IF v_trig_cnt IS DISTINCT FROM v_trigs[i] THEN
      RAISE EXCEPTION 'POST FAILED: % trigger count changed (expected %, got %).', v_fn_sig, v_trigs[i], v_trig_cnt;
    END IF;

    -- 3-h. 연결 트리거 모두 활성 상태 불변 확인 (tgenabled = 'O')
    IF EXISTS (
      SELECT 1 FROM pg_trigger t WHERE t.tgfoid = v_oid AND t.tgenabled IS DISTINCT FROM 'O'
    ) THEN
      RAISE EXCEPTION 'POST FAILED: % trigger became disabled.', v_fn_sig;
    END IF;

  END LOOP;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3B: POST 트리거 식별자·정의 불변 검증 (17건)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_tg_names text[] := ARRAY[
    'trg_master_fields_updated_at',
    'help_doc_touch_trg',
    'help_node_touch_trg',
    'trg_inquiries_updated_at',
    'trg_rtc_updated',
    'trg_runtime_dependency_updated_at',
    'trg_runtime_doc_updated_at',
    'trg_runtime_evidence_updated_at',
    'trg_runtime_schedule_updated_at',
    'trg_runtime_task_updated_at',
    'trg_user_profile_updated_at',
    'trg_kosha_guide_body_touch',
    'trg_cmc_updated_at',
    'trg_documents_updated_at',
    'trg_update_master_products_elec',
    'trg_billing_keys_updated_at',
    'trg_subscriptions_updated_at'
  ];
  v_tg_fns  text[] := ARRAY[
    'fn_set_updated_at',
    'help_touch_updated_at',
    'help_touch_updated_at',
    'set_updated_at',
    'set_updated_at',
    'set_updated_at',
    'set_updated_at',
    'set_updated_at',
    'set_updated_at',
    'set_updated_at',
    'set_updated_at',
    'tg_kosha_guide_body_touch',
    'update_cmc_updated_at',
    'update_documents_timestamp',
    'update_timestamp',
    'update_updated_at_column',
    'update_updated_at_column'
  ];
  v_tg_md5s text[] := ARRAY[
    '31385e8917683003499dd127476c31a6',
    '78772ce5158e8420bd8877f468d7c39c',
    '1838c6df987051282aab56dc1496580a',
    '355aa6ccf67978e624832828205b6ae9',
    '30b73f8c98328db19ef52e0078e48c3e',
    'fd73431d0070cd82d8c04ea150b46ad6',
    '0fc2f219752ee5dc052e0ce3612d8f25',
    'afa49c17f779436b900523b845289dc8',
    'e0666511a85e9f1d193336d7890b012e',
    'db5e339add68d968f6ee38f3ddba97a8',
    'b8cbe767cc2b021ecf1f1d848195d801',
    '4765b011abd404a5a59f390db6232d33',
    '82fdc43c9bc7eb426a737f78c9274ffb',
    '47782aad0d163b8b0575bb8a56c9c842',
    'e5c63e70d5bba989e963f75b0d71baa3',
    'cee5dddfb63a3bfd4b85a265df912645',
    '3e4b19c7912516202eb46c0366df7069'
  ];

  i             int;
  v_actual_md5  text;
  v_enabled     char;

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
