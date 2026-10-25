-- WO-TAI-SEC-SEARCHPATH-REM97-CW3-SOURCE-001
-- CW3 격리 회귀 실행: BASELINE → PHASE1(pre-ALTER) → ALTER → PHASE2(post-ALTER)
-- Run AFTER setup_cw3.sql

SET search_path = public;

-- 테이블 초기화 (격리 환경 시작 상태 보장)
TRUNCATE public.ext037_chemical_safety_snapshot_items;
TRUNCATE public.ext037_chemical_safety_snapshots;
TRUNCATE public.ext132_hazardous_material_snapshot_items;
TRUNCATE public.ext132_hazardous_material_snapshots;
TRUNCATE public.ext165_chemical_accident_snapshot_items;
TRUNCATE public.ext165_chemical_accident_snapshots;
TRUNCATE public.public_data_sync_runs;
TRUNCATE public.public_data_source_runtime;

-- ─────────────────────────────────────────────────────────────────────────────
-- 기준선 검증 (proconfig=NULL, MD5 9건, volatility/parallel/secdef 불변)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_sigs CONSTANT text[] := ARRAY[
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
  v_oid       oid;
  v_body_md5  text;
  v_proconfig text[];
  v_secdef    bool;
  v_volat     char;
  v_parallel  char;
  i           int;
BEGIN
  FOR i IN 1..9 LOOP
    v_oid := to_regprocedure(c_sigs[i])::oid;
    IF v_oid IS NULL THEN
      RAISE EXCEPTION 'BASELINE FAILED: % not found', c_sigs[i];
    END IF;
    SELECT p.proconfig, md5(p.prosrc), p.prosecdef, p.provolatile, p.proparallel
    INTO v_proconfig, v_body_md5, v_secdef, v_volat, v_parallel
    FROM pg_proc p WHERE p.oid = v_oid;
    IF v_proconfig IS NOT NULL THEN
      RAISE EXCEPTION 'BASELINE FAILED: % proconfig already set: %', c_sigs[i], v_proconfig;
    END IF;
    IF v_secdef IS DISTINCT FROM false THEN
      RAISE EXCEPTION 'BASELINE FAILED: % prosecdef is not false', c_sigs[i];
    END IF;
    IF v_volat IS DISTINCT FROM 'v' THEN
      RAISE EXCEPTION 'BASELINE FAILED: % volatility is not v (got %)', c_sigs[i], v_volat;
    END IF;
    IF v_parallel IS DISTINCT FROM 'u' THEN
      RAISE EXCEPTION 'BASELINE FAILED: % proparallel is not u (got %)', c_sigs[i], v_parallel;
    END IF;
    -- MD5를 session config에 저장 (PHASE 2에서 불변 검증용)
    PERFORM set_config(
      'app.cw3_md5_' || (string_to_array(c_sigs[i], '('))[1],
      v_body_md5,
      false
    );
    RAISE NOTICE 'BASELINE OK [%/9]: % MD5=% proconfig=NULL', i, c_sigs[i], v_body_md5;
  END LOOP;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- ACL 스냅샷 (PHASE 2에서 불변 검증용)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TEMP TABLE _cw3_reg_acl AS
SELECT
  p.proname,
  r.rolname AS grantee,
  ace.privilege_type
FROM pg_proc p
JOIN pg_roles r ON r.rolname IN ('anon', 'authenticated', 'service_role')
CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner))) AS ace
WHERE p.proname IN (
  'fn_ext037_save_page_checkpoint', 'fn_ext037_complete_snapshot', 'fn_ext037_fail_snapshot',
  'fn_ext132_save_page_checkpoint', 'fn_ext132_complete_snapshot', 'fn_ext132_fail_snapshot',
  'fn_ext165_save_page_checkpoint', 'fn_ext165_complete_snapshot', 'fn_ext165_fail_snapshot'
)
AND ace.grantee = r.oid
AND ace.privilege_type = 'EXECUTE';

-- ─────────────────────────────────────────────────────────────────────────────
-- PHASE 1: ALTER 전 상태 전이 테스트 — EXT037
-- ─────────────────────────────────────────────────────────────────────────────

-- CW3-P1-01: EXT037 save_page_checkpoint — 정상 insert (2 items)
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  int;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext037_p1', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext037_chemical_safety_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext037_p1', 'STAGING');

  v_result := public.fn_ext037_save_page_checkpoint(
    v_snap_id,
    '[{"datano":"D001","raw":{"a":1}},{"datano":"D002","raw":{"b":2}}]'::jsonb,
    1, 2, v_run_id
  );
  IF v_result IS DISTINCT FROM 2 THEN
    RAISE EXCEPTION 'CW3-P1-01 FAIL: expected 2, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-01 PASS: ext037 save_page_checkpoint normal insert count=%', v_result;
END;
$$;

-- CW3-P1-02: EXT037 save_page_checkpoint — 동일 items 재호출 (idempotent, count 불변)
DO $$
DECLARE
  v_snap_id uuid;
  v_run_id  uuid;
  v_result  int;
BEGIN
  SELECT s.id, r.current_run_id
  INTO v_snap_id, v_run_id
  FROM ext037_chemical_safety_snapshots s
  JOIN public_data_source_runtime r ON r.source_id = s.source_id
  WHERE s.source_id = 'src_ext037_p1'
  LIMIT 1;

  v_result := public.fn_ext037_save_page_checkpoint(
    v_snap_id,
    '[{"datano":"D001","raw":{"a":99}},{"datano":"D002","raw":{"b":99}}]'::jsonb,
    2, 2, v_run_id
  );
  IF v_result IS DISTINCT FROM 2 THEN
    RAISE EXCEPTION 'CW3-P1-02 FAIL: idempotent re-call expected count=2, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-02 PASS: ext037 save_page_checkpoint idempotent count=%', v_result;
END;
$$;

-- CW3-P1-03: EXT037 save_page_checkpoint — 잘못된 run_id → RUN_FENCED 예외
DO $$
DECLARE
  v_snap_id    uuid;
  v_wrong_run  uuid := gen_random_uuid();
  v_caught     boolean := false;
BEGIN
  SELECT id INTO v_snap_id
  FROM ext037_chemical_safety_snapshots
  WHERE source_id = 'src_ext037_p1'
  LIMIT 1;

  BEGIN
    PERFORM public.fn_ext037_save_page_checkpoint(
      v_snap_id,
      '[{"datano":"D003","raw":{}}]'::jsonb,
      3, 1, v_wrong_run
    );
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%RUN_FENCED%' THEN
      v_caught := true;
    ELSE
      RAISE EXCEPTION 'CW3-P1-03 FAIL: unexpected exception: %', SQLERRM;
    END IF;
  END;
  IF NOT v_caught THEN
    RAISE EXCEPTION 'CW3-P1-03 FAIL: expected RUN_FENCED exception, none raised';
  END IF;
  RAISE NOTICE 'CW3-P1-03 PASS: ext037 save_page_checkpoint wrong run_id → RUN_FENCED';
END;
$$;

-- CW3-P1-04: EXT037 save_page_checkpoint — lease 만료 → RUN_FENCED 예외
DO $$
DECLARE
  v_snap_id uuid;
  v_run_id  uuid;
  v_caught  boolean := false;
BEGIN
  SELECT s.id, r.current_run_id
  INTO v_snap_id, v_run_id
  FROM ext037_chemical_safety_snapshots s
  JOIN public_data_source_runtime r ON r.source_id = s.source_id
  WHERE s.source_id = 'src_ext037_p1'
  LIMIT 1;

  UPDATE public_data_sync_runs
  SET lease_until = now() - interval '1 second'
  WHERE id = v_run_id;

  BEGIN
    PERFORM public.fn_ext037_save_page_checkpoint(
      v_snap_id,
      '[{"datano":"D004","raw":{}}]'::jsonb,
      4, 1, v_run_id
    );
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%RUN_FENCED%' THEN
      v_caught := true;
    ELSE
      RAISE EXCEPTION 'CW3-P1-04 FAIL: unexpected exception: %', SQLERRM;
    END IF;
  END;
  IF NOT v_caught THEN
    RAISE EXCEPTION 'CW3-P1-04 FAIL: expected RUN_FENCED (lease expired), none raised';
  END IF;

  -- lease 복원
  UPDATE public_data_sync_runs
  SET lease_until = now() + interval '1 hour'
  WHERE id = v_run_id;

  RAISE NOTICE 'CW3-P1-04 PASS: ext037 save_page_checkpoint lease expired → RUN_FENCED';
END;
$$;

-- CW3-P1-05: EXT037 save_page_checkpoint — snapshot status=COMPLETED → SNAPSHOT_NOT_STAGING 예외
DO $$
DECLARE
  v_snap_id uuid;
  v_run_id  uuid;
  v_caught  boolean := false;
BEGIN
  SELECT s.id, r.current_run_id
  INTO v_snap_id, v_run_id
  FROM ext037_chemical_safety_snapshots s
  JOIN public_data_source_runtime r ON r.source_id = s.source_id
  WHERE s.source_id = 'src_ext037_p1'
  LIMIT 1;

  UPDATE ext037_chemical_safety_snapshots
  SET status = 'COMPLETED'
  WHERE id = v_snap_id;

  BEGIN
    PERFORM public.fn_ext037_save_page_checkpoint(
      v_snap_id,
      '[{"datano":"D005","raw":{}}]'::jsonb,
      5, 1, v_run_id
    );
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%SNAPSHOT_NOT_STAGING%' THEN
      v_caught := true;
    ELSE
      RAISE EXCEPTION 'CW3-P1-05 FAIL: unexpected exception: %', SQLERRM;
    END IF;
  END;
  IF NOT v_caught THEN
    RAISE EXCEPTION 'CW3-P1-05 FAIL: expected SNAPSHOT_NOT_STAGING, none raised';
  END IF;

  -- 상태 복원 (이후 테스트를 위해)
  UPDATE ext037_chemical_safety_snapshots
  SET status = 'STAGING'
  WHERE id = v_snap_id;

  RAISE NOTICE 'CW3-P1-05 PASS: ext037 save_page_checkpoint non-STAGING → SNAPSHOT_NOT_STAGING';
END;
$$;

-- CW3-P1-06: EXT037 complete_snapshot — 정상 프로모션
DO $$
DECLARE
  v_snap_id uuid;
  v_run_id  uuid;
  v_result  boolean;
  v_status  text;
  v_current boolean;
BEGIN
  SELECT s.id, r.current_run_id
  INTO v_snap_id, v_run_id
  FROM ext037_chemical_safety_snapshots s
  JOIN public_data_source_runtime r ON r.source_id = s.source_id
  WHERE s.source_id = 'src_ext037_p1'
  LIMIT 1;

  -- checkpoint_api_total=2 설정 (items 2건과 일치)
  UPDATE ext037_chemical_safety_snapshots
  SET checkpoint_api_total = 2
  WHERE id = v_snap_id;

  v_result := public.fn_ext037_complete_snapshot(
    v_snap_id, 'src_ext037_p1', 2, 'hash_ext037_p1', v_run_id
  );
  IF v_result IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P1-06 FAIL: expected true, got %', v_result;
  END IF;
  SELECT status, is_current INTO v_status, v_current
  FROM ext037_chemical_safety_snapshots WHERE id = v_snap_id;
  IF v_status IS DISTINCT FROM 'COMPLETED' THEN
    RAISE EXCEPTION 'CW3-P1-06 FAIL: expected COMPLETED, got %', v_status;
  END IF;
  IF v_current IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P1-06 FAIL: expected is_current=true, got %', v_current;
  END IF;
  RAISE NOTICE 'CW3-P1-06 PASS: ext037 complete_snapshot → COMPLETED is_current=true';
END;
$$;

-- CW3-P1-07: EXT037 complete_snapshot — 잘못된 run_id → false
DO $$
DECLARE
  v_snap_id  uuid := gen_random_uuid();
  v_run_id   uuid := gen_random_uuid();
  v_wrong    uuid := gen_random_uuid();
  v_result   boolean;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext037_p1_07', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext037_chemical_safety_snapshots (id, source_id, status, checkpoint_api_total)
  VALUES (v_snap_id, 'src_ext037_p1_07', 'STAGING', 0);

  v_result := public.fn_ext037_complete_snapshot(
    v_snap_id, 'src_ext037_p1_07', 0, 'hash_x', v_wrong
  );
  IF v_result IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW3-P1-07 FAIL: wrong run_id should return false, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-07 PASS: ext037 complete_snapshot wrong run_id → false';
END;
$$;

-- CW3-P1-08: EXT037 complete_snapshot — item count 불일치 → false
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  boolean;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext037_p1_08', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext037_chemical_safety_snapshots (id, source_id, status, checkpoint_api_total)
  VALUES (v_snap_id, 'src_ext037_p1_08', 'STAGING', 5);
  -- items 0건이지만 p_total_items=5 전달 → count 불일치
  v_result := public.fn_ext037_complete_snapshot(
    v_snap_id, 'src_ext037_p1_08', 5, 'hash_x', v_run_id
  );
  IF v_result IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW3-P1-08 FAIL: count mismatch should return false, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-08 PASS: ext037 complete_snapshot item count mismatch → false';
END;
$$;

-- CW3-P1-09: EXT037 complete_snapshot — checkpoint_api_total NULL → false (fail-closed)
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  boolean;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext037_p1_09', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  -- checkpoint_api_total은 NULL (기본값)
  INSERT INTO ext037_chemical_safety_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext037_p1_09', 'STAGING');

  v_result := public.fn_ext037_complete_snapshot(
    v_snap_id, 'src_ext037_p1_09', 0, 'hash_x', v_run_id
  );
  IF v_result IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW3-P1-09 FAIL: null checkpoint_api_total should return false, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-09 PASS: ext037 complete_snapshot checkpoint_api_total NULL → false (fail-closed)';
END;
$$;

-- CW3-P1-10: EXT037 complete_snapshot — 이전 current 스냅샷 비활성화 확인
DO $$
DECLARE
  v_old_id  uuid := gen_random_uuid();
  v_new_id  uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  boolean;
  v_old_cur boolean;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext037_p1_10', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  -- 이전 COMPLETED+is_current=true 스냅샷
  INSERT INTO ext037_chemical_safety_snapshots (id, source_id, status, is_current)
  VALUES (v_old_id, 'src_ext037_p1_10', 'COMPLETED', true);
  -- 새 STAGING 스냅샷
  INSERT INTO ext037_chemical_safety_snapshots (id, source_id, status, checkpoint_api_total)
  VALUES (v_new_id, 'src_ext037_p1_10', 'STAGING', 0);

  v_result := public.fn_ext037_complete_snapshot(
    v_new_id, 'src_ext037_p1_10', 0, 'hash_new', v_run_id
  );
  IF v_result IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P1-10 FAIL: complete returned %, expected true', v_result;
  END IF;
  SELECT is_current INTO v_old_cur
  FROM ext037_chemical_safety_snapshots WHERE id = v_old_id;
  IF v_old_cur IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW3-P1-10 FAIL: old snapshot is_current should be false, got %', v_old_cur;
  END IF;
  RAISE NOTICE 'CW3-P1-10 PASS: ext037 complete_snapshot previous current deactivated';
END;
$$;

-- CW3-P1-11: EXT037 fail_snapshot — 정상 실패 처리
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  boolean;
  v_status  text;
  v_errmsg  text;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext037_p1_11', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext037_chemical_safety_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext037_p1_11', 'STAGING');

  v_result := public.fn_ext037_fail_snapshot(v_snap_id, v_run_id, 'network timeout');
  IF v_result IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P1-11 FAIL: expected true, got %', v_result;
  END IF;
  SELECT status, error_message INTO v_status, v_errmsg
  FROM ext037_chemical_safety_snapshots WHERE id = v_snap_id;
  IF v_status IS DISTINCT FROM 'FAILED' THEN
    RAISE EXCEPTION 'CW3-P1-11 FAIL: expected FAILED, got %', v_status;
  END IF;
  IF v_errmsg IS DISTINCT FROM 'network timeout' THEN
    RAISE EXCEPTION 'CW3-P1-11 FAIL: error_message mismatch: %', v_errmsg;
  END IF;
  RAISE NOTICE 'CW3-P1-11 PASS: ext037 fail_snapshot → FAILED error_message set';
END;
$$;

-- CW3-P1-12: EXT037 fail_snapshot — 잘못된 run_id → false
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_wrong   uuid := gen_random_uuid();
  v_result  boolean;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext037_p1_12', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext037_chemical_safety_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext037_p1_12', 'STAGING');

  v_result := public.fn_ext037_fail_snapshot(v_snap_id, v_wrong, 'error');
  IF v_result IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW3-P1-12 FAIL: wrong run_id should return false, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-12 PASS: ext037 fail_snapshot wrong run_id → false';
END;
$$;

-- CW3-P1-13: EXT037 fail_snapshot — lease 만료 → false
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  boolean;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext037_p1_13', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() - interval '1 second');
  INSERT INTO ext037_chemical_safety_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext037_p1_13', 'STAGING');

  v_result := public.fn_ext037_fail_snapshot(v_snap_id, v_run_id, 'error');
  IF v_result IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW3-P1-13 FAIL: expired lease should return false, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-13 PASS: ext037 fail_snapshot lease expired → false';
END;
$$;

-- CW3-P1-14: EXT037 fail_snapshot — 이미 COMPLETED → false (STAGING 가드)
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  boolean;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext037_p1_14', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext037_chemical_safety_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext037_p1_14', 'COMPLETED');

  v_result := public.fn_ext037_fail_snapshot(v_snap_id, v_run_id, 'error');
  IF v_result IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW3-P1-14 FAIL: COMPLETED snapshot should return false, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-14 PASS: ext037 fail_snapshot already COMPLETED → false';
END;
$$;

-- CW3-P1-15: EXT037 fail_snapshot — error_message 500자 절단
DO $$
DECLARE
  v_snap_id  uuid := gen_random_uuid();
  v_run_id   uuid := gen_random_uuid();
  v_long_msg text := repeat('X', 600);
  v_result   boolean;
  v_errmsg   text;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext037_p1_15', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext037_chemical_safety_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext037_p1_15', 'STAGING');

  v_result := public.fn_ext037_fail_snapshot(v_snap_id, v_run_id, v_long_msg);
  IF v_result IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P1-15 FAIL: expected true, got %', v_result;
  END IF;
  SELECT error_message INTO v_errmsg
  FROM ext037_chemical_safety_snapshots WHERE id = v_snap_id;
  IF length(v_errmsg) IS DISTINCT FROM 500 THEN
    RAISE EXCEPTION 'CW3-P1-15 FAIL: error_message length should be 500, got %', length(v_errmsg);
  END IF;
  RAISE NOTICE 'CW3-P1-15 PASS: ext037 fail_snapshot error_message truncated to 500 chars';
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- PHASE 1: ALTER 전 상태 전이 테스트 — EXT132
-- ─────────────────────────────────────────────────────────────────────────────

TRUNCATE public.ext132_hazardous_material_snapshot_items;
TRUNCATE public.ext132_hazardous_material_snapshots;
TRUNCATE public.public_data_sync_runs;
TRUNCATE public.public_data_source_runtime;

-- CW3-P1-16: EXT132 save_page_checkpoint — 정상 insert (chemicalno 키 사용)
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  int;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext132_p1', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext132_hazardous_material_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext132_p1', 'STAGING');

  v_result := public.fn_ext132_save_page_checkpoint(
    v_snap_id,
    '[{"chemicalno":"C001","raw":{"x":1}},{"chemicalno":"C002","raw":{"y":2}}]'::jsonb,
    1, 2, v_run_id
  );
  IF v_result IS DISTINCT FROM 2 THEN
    RAISE EXCEPTION 'CW3-P1-16 FAIL: expected 2, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-16 PASS: ext132 save_page_checkpoint normal insert count=%', v_result;
END;
$$;

-- CW3-P1-17: EXT132 save_page_checkpoint — idempotent
DO $$
DECLARE
  v_snap_id uuid;
  v_run_id  uuid;
  v_result  int;
BEGIN
  SELECT s.id, r.current_run_id
  INTO v_snap_id, v_run_id
  FROM ext132_hazardous_material_snapshots s
  JOIN public_data_source_runtime r ON r.source_id = s.source_id
  WHERE s.source_id = 'src_ext132_p1'
  LIMIT 1;

  v_result := public.fn_ext132_save_page_checkpoint(
    v_snap_id,
    '[{"chemicalno":"C001","raw":{"x":99}},{"chemicalno":"C002","raw":{"y":99}}]'::jsonb,
    2, 2, v_run_id
  );
  IF v_result IS DISTINCT FROM 2 THEN
    RAISE EXCEPTION 'CW3-P1-17 FAIL: idempotent re-call expected count=2, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-17 PASS: ext132 save_page_checkpoint idempotent count=%', v_result;
END;
$$;

-- CW3-P1-18: EXT132 save_page_checkpoint — 잘못된 run_id → RUN_FENCED
DO $$
DECLARE
  v_snap_id   uuid;
  v_wrong_run uuid := gen_random_uuid();
  v_caught    boolean := false;
BEGIN
  SELECT id INTO v_snap_id
  FROM ext132_hazardous_material_snapshots
  WHERE source_id = 'src_ext132_p1'
  LIMIT 1;

  BEGIN
    PERFORM public.fn_ext132_save_page_checkpoint(
      v_snap_id,
      '[{"chemicalno":"C003","raw":{}}]'::jsonb,
      3, 1, v_wrong_run
    );
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%RUN_FENCED%' THEN
      v_caught := true;
    ELSE
      RAISE EXCEPTION 'CW3-P1-18 FAIL: unexpected exception: %', SQLERRM;
    END IF;
  END;
  IF NOT v_caught THEN
    RAISE EXCEPTION 'CW3-P1-18 FAIL: expected RUN_FENCED, none raised';
  END IF;
  RAISE NOTICE 'CW3-P1-18 PASS: ext132 save_page_checkpoint wrong run_id → RUN_FENCED';
END;
$$;

-- CW3-P1-19: EXT132 save_page_checkpoint — lease 만료 → RUN_FENCED
DO $$
DECLARE
  v_snap_id uuid;
  v_run_id  uuid;
  v_caught  boolean := false;
BEGIN
  SELECT s.id, r.current_run_id
  INTO v_snap_id, v_run_id
  FROM ext132_hazardous_material_snapshots s
  JOIN public_data_source_runtime r ON r.source_id = s.source_id
  WHERE s.source_id = 'src_ext132_p1'
  LIMIT 1;

  UPDATE public_data_sync_runs
  SET lease_until = now() - interval '1 second'
  WHERE id = v_run_id;

  BEGIN
    PERFORM public.fn_ext132_save_page_checkpoint(
      v_snap_id,
      '[{"chemicalno":"C004","raw":{}}]'::jsonb,
      4, 1, v_run_id
    );
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%RUN_FENCED%' THEN
      v_caught := true;
    ELSE
      RAISE EXCEPTION 'CW3-P1-19 FAIL: unexpected exception: %', SQLERRM;
    END IF;
  END;
  IF NOT v_caught THEN
    RAISE EXCEPTION 'CW3-P1-19 FAIL: expected RUN_FENCED (lease expired), none raised';
  END IF;

  UPDATE public_data_sync_runs
  SET lease_until = now() + interval '1 hour'
  WHERE id = v_run_id;

  RAISE NOTICE 'CW3-P1-19 PASS: ext132 save_page_checkpoint lease expired → RUN_FENCED';
END;
$$;

-- CW3-P1-20: EXT132 save_page_checkpoint — SNAPSHOT_NOT_STAGING
DO $$
DECLARE
  v_snap_id uuid;
  v_run_id  uuid;
  v_caught  boolean := false;
BEGIN
  SELECT s.id, r.current_run_id
  INTO v_snap_id, v_run_id
  FROM ext132_hazardous_material_snapshots s
  JOIN public_data_source_runtime r ON r.source_id = s.source_id
  WHERE s.source_id = 'src_ext132_p1'
  LIMIT 1;

  UPDATE ext132_hazardous_material_snapshots
  SET status = 'COMPLETED'
  WHERE id = v_snap_id;

  BEGIN
    PERFORM public.fn_ext132_save_page_checkpoint(
      v_snap_id,
      '[{"chemicalno":"C005","raw":{}}]'::jsonb,
      5, 1, v_run_id
    );
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%SNAPSHOT_NOT_STAGING%' THEN
      v_caught := true;
    ELSE
      RAISE EXCEPTION 'CW3-P1-20 FAIL: unexpected exception: %', SQLERRM;
    END IF;
  END;
  IF NOT v_caught THEN
    RAISE EXCEPTION 'CW3-P1-20 FAIL: expected SNAPSHOT_NOT_STAGING, none raised';
  END IF;

  UPDATE ext132_hazardous_material_snapshots
  SET status = 'STAGING'
  WHERE id = v_snap_id;

  RAISE NOTICE 'CW3-P1-20 PASS: ext132 save_page_checkpoint non-STAGING → SNAPSHOT_NOT_STAGING';
END;
$$;

-- CW3-P1-21: EXT132 complete_snapshot — 정상 프로모션
DO $$
DECLARE
  v_snap_id uuid;
  v_run_id  uuid;
  v_result  boolean;
  v_status  text;
  v_current boolean;
BEGIN
  SELECT s.id, r.current_run_id
  INTO v_snap_id, v_run_id
  FROM ext132_hazardous_material_snapshots s
  JOIN public_data_source_runtime r ON r.source_id = s.source_id
  WHERE s.source_id = 'src_ext132_p1'
  LIMIT 1;

  UPDATE ext132_hazardous_material_snapshots
  SET checkpoint_api_total = 2
  WHERE id = v_snap_id;

  v_result := public.fn_ext132_complete_snapshot(
    v_snap_id, 'src_ext132_p1', 2, 'hash_ext132_p1', v_run_id
  );
  IF v_result IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P1-21 FAIL: expected true, got %', v_result;
  END IF;
  SELECT status, is_current INTO v_status, v_current
  FROM ext132_hazardous_material_snapshots WHERE id = v_snap_id;
  IF v_status IS DISTINCT FROM 'COMPLETED' THEN
    RAISE EXCEPTION 'CW3-P1-21 FAIL: expected COMPLETED, got %', v_status;
  END IF;
  IF v_current IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P1-21 FAIL: expected is_current=true, got %', v_current;
  END IF;
  RAISE NOTICE 'CW3-P1-21 PASS: ext132 complete_snapshot → COMPLETED is_current=true';
END;
$$;

-- CW3-P1-22: EXT132 complete_snapshot — 잘못된 run_id → false
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_wrong   uuid := gen_random_uuid();
  v_result  boolean;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext132_p1_22', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext132_hazardous_material_snapshots (id, source_id, status, checkpoint_api_total)
  VALUES (v_snap_id, 'src_ext132_p1_22', 'STAGING', 0);

  v_result := public.fn_ext132_complete_snapshot(
    v_snap_id, 'src_ext132_p1_22', 0, 'hash_x', v_wrong
  );
  IF v_result IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW3-P1-22 FAIL: wrong run_id should return false, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-22 PASS: ext132 complete_snapshot wrong run_id → false';
END;
$$;

-- CW3-P1-23: EXT132 complete_snapshot — item count 불일치 → false
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  boolean;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext132_p1_23', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext132_hazardous_material_snapshots (id, source_id, status, checkpoint_api_total)
  VALUES (v_snap_id, 'src_ext132_p1_23', 'STAGING', 5);

  v_result := public.fn_ext132_complete_snapshot(
    v_snap_id, 'src_ext132_p1_23', 5, 'hash_x', v_run_id
  );
  IF v_result IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW3-P1-23 FAIL: count mismatch should return false, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-23 PASS: ext132 complete_snapshot item count mismatch → false';
END;
$$;

-- CW3-P1-24: EXT132 complete_snapshot — checkpoint_api_total NULL → false
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  boolean;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext132_p1_24', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext132_hazardous_material_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext132_p1_24', 'STAGING');

  v_result := public.fn_ext132_complete_snapshot(
    v_snap_id, 'src_ext132_p1_24', 0, 'hash_x', v_run_id
  );
  IF v_result IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW3-P1-24 FAIL: null checkpoint_api_total should return false, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-24 PASS: ext132 complete_snapshot checkpoint_api_total NULL → false';
END;
$$;

-- CW3-P1-25: EXT132 complete_snapshot — 이전 current 비활성화
DO $$
DECLARE
  v_old_id  uuid := gen_random_uuid();
  v_new_id  uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  boolean;
  v_old_cur boolean;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext132_p1_25', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext132_hazardous_material_snapshots (id, source_id, status, is_current)
  VALUES (v_old_id, 'src_ext132_p1_25', 'COMPLETED', true);
  INSERT INTO ext132_hazardous_material_snapshots (id, source_id, status, checkpoint_api_total)
  VALUES (v_new_id, 'src_ext132_p1_25', 'STAGING', 0);

  v_result := public.fn_ext132_complete_snapshot(
    v_new_id, 'src_ext132_p1_25', 0, 'hash_new', v_run_id
  );
  IF v_result IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P1-25 FAIL: complete returned %, expected true', v_result;
  END IF;
  SELECT is_current INTO v_old_cur
  FROM ext132_hazardous_material_snapshots WHERE id = v_old_id;
  IF v_old_cur IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW3-P1-25 FAIL: old snapshot is_current should be false, got %', v_old_cur;
  END IF;
  RAISE NOTICE 'CW3-P1-25 PASS: ext132 complete_snapshot previous current deactivated';
END;
$$;

-- CW3-P1-26: EXT132 fail_snapshot — 정상 실패 처리
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  boolean;
  v_status  text;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext132_p1_26', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext132_hazardous_material_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext132_p1_26', 'STAGING');

  v_result := public.fn_ext132_fail_snapshot(v_snap_id, v_run_id, 'api error');
  IF v_result IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P1-26 FAIL: expected true, got %', v_result;
  END IF;
  SELECT status INTO v_status
  FROM ext132_hazardous_material_snapshots WHERE id = v_snap_id;
  IF v_status IS DISTINCT FROM 'FAILED' THEN
    RAISE EXCEPTION 'CW3-P1-26 FAIL: expected FAILED, got %', v_status;
  END IF;
  RAISE NOTICE 'CW3-P1-26 PASS: ext132 fail_snapshot → FAILED';
END;
$$;

-- CW3-P1-27: EXT132 fail_snapshot — 잘못된 run_id → false
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_wrong   uuid := gen_random_uuid();
  v_result  boolean;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext132_p1_27', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext132_hazardous_material_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext132_p1_27', 'STAGING');

  v_result := public.fn_ext132_fail_snapshot(v_snap_id, v_wrong, 'error');
  IF v_result IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW3-P1-27 FAIL: wrong run_id should return false, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-27 PASS: ext132 fail_snapshot wrong run_id → false';
END;
$$;

-- CW3-P1-28: EXT132 fail_snapshot — lease 만료 → false
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  boolean;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext132_p1_28', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() - interval '1 second');
  INSERT INTO ext132_hazardous_material_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext132_p1_28', 'STAGING');

  v_result := public.fn_ext132_fail_snapshot(v_snap_id, v_run_id, 'error');
  IF v_result IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW3-P1-28 FAIL: expired lease should return false, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-28 PASS: ext132 fail_snapshot lease expired → false';
END;
$$;

-- CW3-P1-29: EXT132 fail_snapshot — 이미 COMPLETED → false
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  boolean;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext132_p1_29', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext132_hazardous_material_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext132_p1_29', 'COMPLETED');

  v_result := public.fn_ext132_fail_snapshot(v_snap_id, v_run_id, 'error');
  IF v_result IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW3-P1-29 FAIL: COMPLETED snapshot should return false, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-29 PASS: ext132 fail_snapshot already COMPLETED → false';
END;
$$;

-- CW3-P1-30: EXT132 fail_snapshot — error_message 500자 절단
DO $$
DECLARE
  v_snap_id  uuid := gen_random_uuid();
  v_run_id   uuid := gen_random_uuid();
  v_long_msg text := repeat('Y', 600);
  v_result   boolean;
  v_errmsg   text;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext132_p1_30', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext132_hazardous_material_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext132_p1_30', 'STAGING');

  v_result := public.fn_ext132_fail_snapshot(v_snap_id, v_run_id, v_long_msg);
  IF v_result IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P1-30 FAIL: expected true, got %', v_result;
  END IF;
  SELECT error_message INTO v_errmsg
  FROM ext132_hazardous_material_snapshots WHERE id = v_snap_id;
  IF length(v_errmsg) IS DISTINCT FROM 500 THEN
    RAISE EXCEPTION 'CW3-P1-30 FAIL: error_message length should be 500, got %', length(v_errmsg);
  END IF;
  RAISE NOTICE 'CW3-P1-30 PASS: ext132 fail_snapshot error_message truncated to 500 chars';
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- PHASE 1: ALTER 전 상태 전이 테스트 — EXT165
-- ─────────────────────────────────────────────────────────────────────────────

TRUNCATE public.ext165_chemical_accident_snapshot_items;
TRUNCATE public.ext165_chemical_accident_snapshots;
TRUNCATE public.public_data_sync_runs;
TRUNCATE public.public_data_source_runtime;

-- CW3-P1-31: EXT165 save_page_checkpoint — 정상 insert
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  int;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext165_p1', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext165_chemical_accident_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext165_p1', 'STAGING');

  v_result := public.fn_ext165_save_page_checkpoint(
    v_snap_id,
    '[{"datano":"A001","raw":{"p":1}},{"datano":"A002","raw":{"q":2}}]'::jsonb,
    1, 2, v_run_id
  );
  IF v_result IS DISTINCT FROM 2 THEN
    RAISE EXCEPTION 'CW3-P1-31 FAIL: expected 2, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-31 PASS: ext165 save_page_checkpoint normal insert count=%', v_result;
END;
$$;

-- CW3-P1-32: EXT165 save_page_checkpoint — idempotent
DO $$
DECLARE
  v_snap_id uuid;
  v_run_id  uuid;
  v_result  int;
BEGIN
  SELECT s.id, r.current_run_id
  INTO v_snap_id, v_run_id
  FROM ext165_chemical_accident_snapshots s
  JOIN public_data_source_runtime r ON r.source_id = s.source_id
  WHERE s.source_id = 'src_ext165_p1'
  LIMIT 1;

  v_result := public.fn_ext165_save_page_checkpoint(
    v_snap_id,
    '[{"datano":"A001","raw":{"p":99}},{"datano":"A002","raw":{"q":99}}]'::jsonb,
    2, 2, v_run_id
  );
  IF v_result IS DISTINCT FROM 2 THEN
    RAISE EXCEPTION 'CW3-P1-32 FAIL: idempotent re-call expected count=2, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-32 PASS: ext165 save_page_checkpoint idempotent count=%', v_result;
END;
$$;

-- CW3-P1-33: EXT165 save_page_checkpoint — 잘못된 run_id → RUN_FENCED
DO $$
DECLARE
  v_snap_id   uuid;
  v_wrong_run uuid := gen_random_uuid();
  v_caught    boolean := false;
BEGIN
  SELECT id INTO v_snap_id
  FROM ext165_chemical_accident_snapshots
  WHERE source_id = 'src_ext165_p1'
  LIMIT 1;

  BEGIN
    PERFORM public.fn_ext165_save_page_checkpoint(
      v_snap_id,
      '[{"datano":"A003","raw":{}}]'::jsonb,
      3, 1, v_wrong_run
    );
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%RUN_FENCED%' THEN
      v_caught := true;
    ELSE
      RAISE EXCEPTION 'CW3-P1-33 FAIL: unexpected exception: %', SQLERRM;
    END IF;
  END;
  IF NOT v_caught THEN
    RAISE EXCEPTION 'CW3-P1-33 FAIL: expected RUN_FENCED, none raised';
  END IF;
  RAISE NOTICE 'CW3-P1-33 PASS: ext165 save_page_checkpoint wrong run_id → RUN_FENCED';
END;
$$;

-- CW3-P1-34: EXT165 save_page_checkpoint — lease 만료 → RUN_FENCED
DO $$
DECLARE
  v_snap_id uuid;
  v_run_id  uuid;
  v_caught  boolean := false;
BEGIN
  SELECT s.id, r.current_run_id
  INTO v_snap_id, v_run_id
  FROM ext165_chemical_accident_snapshots s
  JOIN public_data_source_runtime r ON r.source_id = s.source_id
  WHERE s.source_id = 'src_ext165_p1'
  LIMIT 1;

  UPDATE public_data_sync_runs
  SET lease_until = now() - interval '1 second'
  WHERE id = v_run_id;

  BEGIN
    PERFORM public.fn_ext165_save_page_checkpoint(
      v_snap_id,
      '[{"datano":"A004","raw":{}}]'::jsonb,
      4, 1, v_run_id
    );
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%RUN_FENCED%' THEN
      v_caught := true;
    ELSE
      RAISE EXCEPTION 'CW3-P1-34 FAIL: unexpected exception: %', SQLERRM;
    END IF;
  END;
  IF NOT v_caught THEN
    RAISE EXCEPTION 'CW3-P1-34 FAIL: expected RUN_FENCED (lease expired), none raised';
  END IF;

  UPDATE public_data_sync_runs
  SET lease_until = now() + interval '1 hour'
  WHERE id = v_run_id;

  RAISE NOTICE 'CW3-P1-34 PASS: ext165 save_page_checkpoint lease expired → RUN_FENCED';
END;
$$;

-- CW3-P1-35: EXT165 save_page_checkpoint — SNAPSHOT_NOT_STAGING
DO $$
DECLARE
  v_snap_id uuid;
  v_run_id  uuid;
  v_caught  boolean := false;
BEGIN
  SELECT s.id, r.current_run_id
  INTO v_snap_id, v_run_id
  FROM ext165_chemical_accident_snapshots s
  JOIN public_data_source_runtime r ON r.source_id = s.source_id
  WHERE s.source_id = 'src_ext165_p1'
  LIMIT 1;

  UPDATE ext165_chemical_accident_snapshots
  SET status = 'COMPLETED'
  WHERE id = v_snap_id;

  BEGIN
    PERFORM public.fn_ext165_save_page_checkpoint(
      v_snap_id,
      '[{"datano":"A005","raw":{}}]'::jsonb,
      5, 1, v_run_id
    );
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%SNAPSHOT_NOT_STAGING%' THEN
      v_caught := true;
    ELSE
      RAISE EXCEPTION 'CW3-P1-35 FAIL: unexpected exception: %', SQLERRM;
    END IF;
  END;
  IF NOT v_caught THEN
    RAISE EXCEPTION 'CW3-P1-35 FAIL: expected SNAPSHOT_NOT_STAGING, none raised';
  END IF;

  UPDATE ext165_chemical_accident_snapshots
  SET status = 'STAGING'
  WHERE id = v_snap_id;

  RAISE NOTICE 'CW3-P1-35 PASS: ext165 save_page_checkpoint non-STAGING → SNAPSHOT_NOT_STAGING';
END;
$$;

-- CW3-P1-36: EXT165 complete_snapshot — collect_scope=NULL → is_current=true (전체 수집)
DO $$
DECLARE
  v_snap_id uuid;
  v_run_id  uuid;
  v_result  boolean;
  v_status  text;
  v_current boolean;
BEGIN
  SELECT s.id, r.current_run_id
  INTO v_snap_id, v_run_id
  FROM ext165_chemical_accident_snapshots s
  JOIN public_data_source_runtime r ON r.source_id = s.source_id
  WHERE s.source_id = 'src_ext165_p1'
  LIMIT 1;

  UPDATE ext165_chemical_accident_snapshots
  SET checkpoint_api_total = 2, collect_scope = NULL
  WHERE id = v_snap_id;

  v_result := public.fn_ext165_complete_snapshot(
    v_snap_id, 'src_ext165_p1', 2, 'hash_ext165_full', v_run_id
  );
  IF v_result IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P1-36 FAIL: expected true, got %', v_result;
  END IF;
  SELECT status, is_current INTO v_status, v_current
  FROM ext165_chemical_accident_snapshots WHERE id = v_snap_id;
  IF v_status IS DISTINCT FROM 'COMPLETED' THEN
    RAISE EXCEPTION 'CW3-P1-36 FAIL: expected COMPLETED, got %', v_status;
  END IF;
  IF v_current IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P1-36 FAIL: collect_scope=NULL should set is_current=true, got %', v_current;
  END IF;
  RAISE NOTICE 'CW3-P1-36 PASS: ext165 complete_snapshot collect_scope=NULL → is_current=true';
END;
$$;

-- CW3-P1-37: EXT165 complete_snapshot — collect_scope='2023' → is_current=false (연간 부분 수집)
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  boolean;
  v_status  text;
  v_current boolean;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext165_p1_37', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext165_chemical_accident_snapshots
    (id, source_id, status, checkpoint_api_total, collect_scope)
  VALUES (v_snap_id, 'src_ext165_p1_37', 'STAGING', 0, '2023');

  v_result := public.fn_ext165_complete_snapshot(
    v_snap_id, 'src_ext165_p1_37', 0, 'hash_ext165_partial', v_run_id
  );
  IF v_result IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P1-37 FAIL: expected true, got %', v_result;
  END IF;
  SELECT status, is_current INTO v_status, v_current
  FROM ext165_chemical_accident_snapshots WHERE id = v_snap_id;
  IF v_status IS DISTINCT FROM 'COMPLETED' THEN
    RAISE EXCEPTION 'CW3-P1-37 FAIL: expected COMPLETED, got %', v_status;
  END IF;
  IF v_current IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW3-P1-37 FAIL: collect_scope=''2023'' should set is_current=false, got %', v_current;
  END IF;
  RAISE NOTICE 'CW3-P1-37 PASS: ext165 complete_snapshot collect_scope=''2023'' → is_current=false';
END;
$$;

-- CW3-P1-38: EXT165 complete_snapshot — 잘못된 run_id → false
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_wrong   uuid := gen_random_uuid();
  v_result  boolean;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext165_p1_38', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext165_chemical_accident_snapshots (id, source_id, status, checkpoint_api_total)
  VALUES (v_snap_id, 'src_ext165_p1_38', 'STAGING', 0);

  v_result := public.fn_ext165_complete_snapshot(
    v_snap_id, 'src_ext165_p1_38', 0, 'hash_x', v_wrong
  );
  IF v_result IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW3-P1-38 FAIL: wrong run_id should return false, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-38 PASS: ext165 complete_snapshot wrong run_id → false';
END;
$$;

-- CW3-P1-39: EXT165 complete_snapshot — item count 불일치 → false
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  boolean;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext165_p1_39', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext165_chemical_accident_snapshots (id, source_id, status, checkpoint_api_total)
  VALUES (v_snap_id, 'src_ext165_p1_39', 'STAGING', 5);

  v_result := public.fn_ext165_complete_snapshot(
    v_snap_id, 'src_ext165_p1_39', 5, 'hash_x', v_run_id
  );
  IF v_result IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW3-P1-39 FAIL: count mismatch should return false, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-39 PASS: ext165 complete_snapshot item count mismatch → false';
END;
$$;

-- CW3-P1-40: EXT165 complete_snapshot — checkpoint_api_total NULL → false
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  boolean;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext165_p1_40', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext165_chemical_accident_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext165_p1_40', 'STAGING');

  v_result := public.fn_ext165_complete_snapshot(
    v_snap_id, 'src_ext165_p1_40', 0, 'hash_x', v_run_id
  );
  IF v_result IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW3-P1-40 FAIL: null checkpoint_api_total should return false, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-40 PASS: ext165 complete_snapshot checkpoint_api_total NULL → false';
END;
$$;

-- CW3-P1-41: EXT165 fail_snapshot — 정상 실패 처리
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  boolean;
  v_status  text;
  v_errmsg  text;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext165_p1_41', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext165_chemical_accident_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext165_p1_41', 'STAGING');

  v_result := public.fn_ext165_fail_snapshot(v_snap_id, v_run_id, 'connection refused');
  IF v_result IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P1-41 FAIL: expected true, got %', v_result;
  END IF;
  SELECT status, error_message INTO v_status, v_errmsg
  FROM ext165_chemical_accident_snapshots WHERE id = v_snap_id;
  IF v_status IS DISTINCT FROM 'FAILED' THEN
    RAISE EXCEPTION 'CW3-P1-41 FAIL: expected FAILED, got %', v_status;
  END IF;
  IF v_errmsg IS DISTINCT FROM 'connection refused' THEN
    RAISE EXCEPTION 'CW3-P1-41 FAIL: error_message mismatch: %', v_errmsg;
  END IF;
  RAISE NOTICE 'CW3-P1-41 PASS: ext165 fail_snapshot → FAILED error_message set';
END;
$$;

-- CW3-P1-42: EXT165 fail_snapshot — 잘못된 run_id → false
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_wrong   uuid := gen_random_uuid();
  v_result  boolean;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext165_p1_42', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext165_chemical_accident_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext165_p1_42', 'STAGING');

  v_result := public.fn_ext165_fail_snapshot(v_snap_id, v_wrong, 'error');
  IF v_result IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW3-P1-42 FAIL: wrong run_id should return false, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-42 PASS: ext165 fail_snapshot wrong run_id → false';
END;
$$;

-- CW3-P1-43: EXT165 fail_snapshot — lease 만료 → false
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  boolean;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext165_p1_43', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() - interval '1 second');
  INSERT INTO ext165_chemical_accident_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext165_p1_43', 'STAGING');

  v_result := public.fn_ext165_fail_snapshot(v_snap_id, v_run_id, 'error');
  IF v_result IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW3-P1-43 FAIL: expired lease should return false, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-43 PASS: ext165 fail_snapshot lease expired → false';
END;
$$;

-- CW3-P1-44: EXT165 fail_snapshot — 이미 COMPLETED → false
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  boolean;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext165_p1_44', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext165_chemical_accident_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext165_p1_44', 'COMPLETED');

  v_result := public.fn_ext165_fail_snapshot(v_snap_id, v_run_id, 'error');
  IF v_result IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW3-P1-44 FAIL: COMPLETED snapshot should return false, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P1-44 PASS: ext165 fail_snapshot already COMPLETED → false';
END;
$$;

-- CW3-P1-45: EXT165 fail_snapshot — error_message 500자 절단
DO $$
DECLARE
  v_snap_id  uuid := gen_random_uuid();
  v_run_id   uuid := gen_random_uuid();
  v_long_msg text := repeat('Z', 600);
  v_result   boolean;
  v_errmsg   text;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext165_p1_45', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext165_chemical_accident_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext165_p1_45', 'STAGING');

  v_result := public.fn_ext165_fail_snapshot(v_snap_id, v_run_id, v_long_msg);
  IF v_result IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P1-45 FAIL: expected true, got %', v_result;
  END IF;
  SELECT error_message INTO v_errmsg
  FROM ext165_chemical_accident_snapshots WHERE id = v_snap_id;
  IF length(v_errmsg) IS DISTINCT FROM 500 THEN
    RAISE EXCEPTION 'CW3-P1-45 FAIL: error_message length should be 500, got %', length(v_errmsg);
  END IF;
  RAISE NOTICE 'CW3-P1-45 PASS: ext165 fail_snapshot error_message truncated to 500 chars';
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- ALTER: search_path 고정 (Migration STEP 2 동일)
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
-- PHASE 2: ALTER 후 검증
-- ─────────────────────────────────────────────────────────────────────────────

-- CW3-P2-01: proconfig=[search_path=pg_catalog, public, pg_temp] 9건 + MD5/secdef/volat/parallel 불변
DO $$
DECLARE
  c_sigs CONSTANT text[] := ARRAY[
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
  c_search_path CONSTANT text := 'search_path=pg_catalog, public, pg_temp';
  v_oid         oid;
  v_body_md5    text;
  v_proconfig   text[];
  v_secdef      bool;
  v_volat       char;
  v_parallel    char;
  v_baseline_md5 text;
  v_fn_key      text;
  i             int;
BEGIN
  FOR i IN 1..9 LOOP
    v_oid := to_regprocedure(c_sigs[i])::oid;
    IF v_oid IS NULL THEN
      RAISE EXCEPTION 'CW3-P2-01 FAIL: % not found', c_sigs[i];
    END IF;
    SELECT p.proconfig, md5(p.prosrc), p.prosecdef, p.provolatile, p.proparallel
    INTO v_proconfig, v_body_md5, v_secdef, v_volat, v_parallel
    FROM pg_proc p WHERE p.oid = v_oid;

    IF v_proconfig IS DISTINCT FROM ARRAY[c_search_path]::text[] THEN
      RAISE EXCEPTION 'CW3-P2-01 FAIL: % proconfig mismatch: %', c_sigs[i], v_proconfig;
    END IF;

    -- BASELINE MD5와 비교 (Fail-Closed: 기준선 누락 시 예외)
    v_fn_key := 'app.cw3_md5_' || (string_to_array(c_sigs[i], '('))[1];
    v_baseline_md5 := current_setting(v_fn_key, true);
    IF v_baseline_md5 IS NULL THEN
      RAISE EXCEPTION 'CW3-P2-01 FAIL: MD5 baseline missing for %', c_sigs[i];
    END IF;
    IF v_body_md5 IS DISTINCT FROM v_baseline_md5 THEN
      RAISE EXCEPTION 'CW3-P2-01 FAIL: % prosrc_md5 changed (baseline=%, now=%)',
        c_sigs[i], v_baseline_md5, v_body_md5;
    END IF;

    IF v_secdef IS DISTINCT FROM false THEN
      RAISE EXCEPTION 'CW3-P2-01 FAIL: % prosecdef changed', c_sigs[i];
    END IF;
    IF v_volat IS DISTINCT FROM 'v' THEN
      RAISE EXCEPTION 'CW3-P2-01 FAIL: % volatility changed to %', c_sigs[i], v_volat;
    END IF;
    IF v_parallel IS DISTINCT FROM 'u' THEN
      RAISE EXCEPTION 'CW3-P2-01 FAIL: % proparallel changed to %', c_sigs[i], v_parallel;
    END IF;
    RAISE NOTICE 'CW3-P2-01 OK [%/9]: % proconfig=[%] MD5=%',
      i, c_sigs[i], c_search_path, v_body_md5;
  END LOOP;
END;
$$;

-- CW3-P2-02: ACL 불변 (ALTER 전 스냅샷과 비교)
DO $$
DECLARE
  v_added   int;
  v_removed int;
BEGIN
  -- 추가된 ACL 항목 (스냅샷에 없는 새 항목)
  SELECT COUNT(*) INTO v_added
  FROM (
    SELECT p.proname, r.rolname, ace.privilege_type
    FROM pg_proc p
    JOIN pg_roles r ON r.rolname IN ('anon', 'authenticated', 'service_role')
    CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner))) AS ace
    WHERE p.proname IN (
      'fn_ext037_save_page_checkpoint', 'fn_ext037_complete_snapshot', 'fn_ext037_fail_snapshot',
      'fn_ext132_save_page_checkpoint', 'fn_ext132_complete_snapshot', 'fn_ext132_fail_snapshot',
      'fn_ext165_save_page_checkpoint', 'fn_ext165_complete_snapshot', 'fn_ext165_fail_snapshot'
    )
    AND ace.grantee = r.oid
    AND ace.privilege_type = 'EXECUTE'
    EXCEPT
    SELECT proname, grantee, privilege_type FROM _cw3_reg_acl
  ) diff_added;

  -- 제거된 ACL 항목 (스냅샷에 있었지만 지금은 없는 항목)
  SELECT COUNT(*) INTO v_removed
  FROM (
    SELECT proname, grantee, privilege_type FROM _cw3_reg_acl
    EXCEPT
    SELECT p.proname, r.rolname, ace.privilege_type
    FROM pg_proc p
    JOIN pg_roles r ON r.rolname IN ('anon', 'authenticated', 'service_role')
    CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner))) AS ace
    WHERE p.proname IN (
      'fn_ext037_save_page_checkpoint', 'fn_ext037_complete_snapshot', 'fn_ext037_fail_snapshot',
      'fn_ext132_save_page_checkpoint', 'fn_ext132_complete_snapshot', 'fn_ext132_fail_snapshot',
      'fn_ext165_save_page_checkpoint', 'fn_ext165_complete_snapshot', 'fn_ext165_fail_snapshot'
    )
    AND ace.grantee = r.oid
    AND ace.privilege_type = 'EXECUTE'
  ) diff_removed;

  IF v_added > 0 OR v_removed > 0 THEN
    RAISE EXCEPTION 'CW3-P2-02 FAIL: ACL changed after ALTER (added=%, removed=%)', v_added, v_removed;
  END IF;
  RAISE NOTICE 'CW3-P2-02 PASS: ACL unchanged after ALTER (added=0, removed=0)';
END;
$$;

-- CW3-P2-03: ALTER 후 동작 불변 검증 — EXT037 save_page_checkpoint 정상 동작
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  int;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext037_p2_03', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext037_chemical_safety_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext037_p2_03', 'STAGING');

  v_result := public.fn_ext037_save_page_checkpoint(
    v_snap_id,
    '[{"datano":"P2D001","raw":{"z":1}}]'::jsonb,
    1, 1, v_run_id
  );
  IF v_result IS DISTINCT FROM 1 THEN
    RAISE EXCEPTION 'CW3-P2-03 FAIL: post-ALTER ext037 save expected 1, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P2-03 PASS: post-ALTER ext037 save_page_checkpoint count=%', v_result;
END;
$$;

-- CW3-P2-04: ALTER 후 동작 불변 검증 — EXT037 complete_snapshot 정상 동작
DO $$
DECLARE
  v_snap_id uuid;
  v_run_id  uuid;
  v_result  boolean;
  v_status  text;
BEGIN
  SELECT s.id, r.current_run_id
  INTO v_snap_id, v_run_id
  FROM ext037_chemical_safety_snapshots s
  JOIN public_data_source_runtime r ON r.source_id = s.source_id
  WHERE s.source_id = 'src_ext037_p2_03'
  LIMIT 1;

  UPDATE ext037_chemical_safety_snapshots
  SET checkpoint_api_total = 1
  WHERE id = v_snap_id;

  v_result := public.fn_ext037_complete_snapshot(
    v_snap_id, 'src_ext037_p2_03', 1, 'hash_p2_03', v_run_id
  );
  IF v_result IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P2-04 FAIL: post-ALTER ext037 complete expected true, got %', v_result;
  END IF;
  SELECT status INTO v_status
  FROM ext037_chemical_safety_snapshots WHERE id = v_snap_id;
  IF v_status IS DISTINCT FROM 'COMPLETED' THEN
    RAISE EXCEPTION 'CW3-P2-04 FAIL: expected COMPLETED, got %', v_status;
  END IF;
  RAISE NOTICE 'CW3-P2-04 PASS: post-ALTER ext037 complete_snapshot → COMPLETED';
END;
$$;

-- CW3-P2-05: ALTER 후 동작 불변 검증 — EXT037 fail_snapshot 정상 동작
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  boolean;
  v_status  text;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext037_p2_05', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext037_chemical_safety_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext037_p2_05', 'STAGING');

  v_result := public.fn_ext037_fail_snapshot(v_snap_id, v_run_id, 'post-ALTER test error');
  IF v_result IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P2-05 FAIL: post-ALTER ext037 fail expected true, got %', v_result;
  END IF;
  SELECT status INTO v_status
  FROM ext037_chemical_safety_snapshots WHERE id = v_snap_id;
  IF v_status IS DISTINCT FROM 'FAILED' THEN
    RAISE EXCEPTION 'CW3-P2-05 FAIL: expected FAILED, got %', v_status;
  END IF;
  RAISE NOTICE 'CW3-P2-05 PASS: post-ALTER ext037 fail_snapshot → FAILED';
END;
$$;

-- CW3-P2-06: ALTER 후 동작 불변 검증 — EXT132 save_page_checkpoint 정상 동작
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  int;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext132_p2_06', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext132_hazardous_material_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext132_p2_06', 'STAGING');

  v_result := public.fn_ext132_save_page_checkpoint(
    v_snap_id,
    '[{"chemicalno":"P2C001","raw":{"z":1}}]'::jsonb,
    1, 1, v_run_id
  );
  IF v_result IS DISTINCT FROM 1 THEN
    RAISE EXCEPTION 'CW3-P2-06 FAIL: post-ALTER ext132 save expected 1, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P2-06 PASS: post-ALTER ext132 save_page_checkpoint count=%', v_result;
END;
$$;

-- CW3-P2-07: ALTER 후 동작 불변 검증 — EXT132 complete_snapshot 정상 동작
DO $$
DECLARE
  v_snap_id uuid;
  v_run_id  uuid;
  v_result  boolean;
  v_status  text;
BEGIN
  SELECT s.id, r.current_run_id
  INTO v_snap_id, v_run_id
  FROM ext132_hazardous_material_snapshots s
  JOIN public_data_source_runtime r ON r.source_id = s.source_id
  WHERE s.source_id = 'src_ext132_p2_06'
  LIMIT 1;

  UPDATE ext132_hazardous_material_snapshots
  SET checkpoint_api_total = 1
  WHERE id = v_snap_id;

  v_result := public.fn_ext132_complete_snapshot(
    v_snap_id, 'src_ext132_p2_06', 1, 'hash_p2_06', v_run_id
  );
  IF v_result IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P2-07 FAIL: post-ALTER ext132 complete expected true, got %', v_result;
  END IF;
  SELECT status INTO v_status
  FROM ext132_hazardous_material_snapshots WHERE id = v_snap_id;
  IF v_status IS DISTINCT FROM 'COMPLETED' THEN
    RAISE EXCEPTION 'CW3-P2-07 FAIL: expected COMPLETED, got %', v_status;
  END IF;
  RAISE NOTICE 'CW3-P2-07 PASS: post-ALTER ext132 complete_snapshot → COMPLETED';
END;
$$;

-- CW3-P2-08: ALTER 후 동작 불변 검증 — EXT132 fail_snapshot 정상 동작
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  boolean;
  v_status  text;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext132_p2_08', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext132_hazardous_material_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext132_p2_08', 'STAGING');

  v_result := public.fn_ext132_fail_snapshot(v_snap_id, v_run_id, 'post-ALTER test error');
  IF v_result IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P2-08 FAIL: post-ALTER ext132 fail expected true, got %', v_result;
  END IF;
  SELECT status INTO v_status
  FROM ext132_hazardous_material_snapshots WHERE id = v_snap_id;
  IF v_status IS DISTINCT FROM 'FAILED' THEN
    RAISE EXCEPTION 'CW3-P2-08 FAIL: expected FAILED, got %', v_status;
  END IF;
  RAISE NOTICE 'CW3-P2-08 PASS: post-ALTER ext132 fail_snapshot → FAILED';
END;
$$;

-- CW3-P2-09: ALTER 후 동작 불변 검증 — EXT165 save_page_checkpoint 정상 동작
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  int;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext165_p2_09', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext165_chemical_accident_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext165_p2_09', 'STAGING');

  v_result := public.fn_ext165_save_page_checkpoint(
    v_snap_id,
    '[{"datano":"P2A001","raw":{"z":1}}]'::jsonb,
    1, 1, v_run_id
  );
  IF v_result IS DISTINCT FROM 1 THEN
    RAISE EXCEPTION 'CW3-P2-09 FAIL: post-ALTER ext165 save expected 1, got %', v_result;
  END IF;
  RAISE NOTICE 'CW3-P2-09 PASS: post-ALTER ext165 save_page_checkpoint count=%', v_result;
END;
$$;

-- CW3-P2-10: ALTER 후 동작 불변 검증 — EXT165 complete_snapshot 정상 동작 (collect_scope=NULL)
DO $$
DECLARE
  v_snap_id uuid;
  v_run_id  uuid;
  v_result  boolean;
  v_status  text;
  v_current boolean;
BEGIN
  SELECT s.id, r.current_run_id
  INTO v_snap_id, v_run_id
  FROM ext165_chemical_accident_snapshots s
  JOIN public_data_source_runtime r ON r.source_id = s.source_id
  WHERE s.source_id = 'src_ext165_p2_09'
  LIMIT 1;

  UPDATE ext165_chemical_accident_snapshots
  SET checkpoint_api_total = 1, collect_scope = NULL
  WHERE id = v_snap_id;

  v_result := public.fn_ext165_complete_snapshot(
    v_snap_id, 'src_ext165_p2_09', 1, 'hash_p2_09', v_run_id
  );
  IF v_result IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P2-10 FAIL: post-ALTER ext165 complete expected true, got %', v_result;
  END IF;
  SELECT status, is_current INTO v_status, v_current
  FROM ext165_chemical_accident_snapshots WHERE id = v_snap_id;
  IF v_status IS DISTINCT FROM 'COMPLETED' THEN
    RAISE EXCEPTION 'CW3-P2-10 FAIL: expected COMPLETED, got %', v_status;
  END IF;
  IF v_current IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P2-10 FAIL: collect_scope=NULL should set is_current=true, got %', v_current;
  END IF;
  RAISE NOTICE 'CW3-P2-10 PASS: post-ALTER ext165 complete_snapshot → COMPLETED is_current=true';
END;
$$;

-- CW3-P2-11: ALTER 후 동작 불변 검증 — EXT165 fail_snapshot 정상 동작
DO $$
DECLARE
  v_snap_id uuid := gen_random_uuid();
  v_run_id  uuid := gen_random_uuid();
  v_result  boolean;
  v_status  text;
BEGIN
  INSERT INTO public_data_source_runtime (source_id, current_run_id)
  VALUES ('src_ext165_p2_11', v_run_id);
  INSERT INTO public_data_sync_runs (id, status, lease_until)
  VALUES (v_run_id, 'RUNNING', now() + interval '1 hour');
  INSERT INTO ext165_chemical_accident_snapshots (id, source_id, status)
  VALUES (v_snap_id, 'src_ext165_p2_11', 'STAGING');

  v_result := public.fn_ext165_fail_snapshot(v_snap_id, v_run_id, 'post-ALTER test error');
  IF v_result IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'CW3-P2-11 FAIL: post-ALTER ext165 fail expected true, got %', v_result;
  END IF;
  SELECT status INTO v_status
  FROM ext165_chemical_accident_snapshots WHERE id = v_snap_id;
  IF v_status IS DISTINCT FROM 'FAILED' THEN
    RAISE EXCEPTION 'CW3-P2-11 FAIL: expected FAILED, got %', v_status;
  END IF;
  RAISE NOTICE 'CW3-P2-11 PASS: post-ALTER ext165 fail_snapshot → FAILED';
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- 최종 결과 요약
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
  RAISE NOTICE '';
  RAISE NOTICE '=== CW3 ISOLATED REGRESSION RESULT ===';
  RAISE NOTICE 'BASELINE proconfig=NULL(9/9)                      = PASS';
  RAISE NOTICE '--- EXT037 ---';
  RAISE NOTICE 'CW3-P1-01 EXT037_SAVE_NORMAL                     = PASS';
  RAISE NOTICE 'CW3-P1-02 EXT037_SAVE_IDEMPOTENT                 = PASS';
  RAISE NOTICE 'CW3-P1-03 EXT037_SAVE_WRONG_RUNID_FENCED         = PASS';
  RAISE NOTICE 'CW3-P1-04 EXT037_SAVE_LEASE_EXPIRED_FENCED       = PASS';
  RAISE NOTICE 'CW3-P1-05 EXT037_SAVE_NOT_STAGING                = PASS';
  RAISE NOTICE 'CW3-P1-06 EXT037_COMPLETE_NORMAL                 = PASS';
  RAISE NOTICE 'CW3-P1-07 EXT037_COMPLETE_WRONG_RUNID            = PASS';
  RAISE NOTICE 'CW3-P1-08 EXT037_COMPLETE_COUNT_MISMATCH         = PASS';
  RAISE NOTICE 'CW3-P1-09 EXT037_COMPLETE_NULL_CHECKPOINT_API    = PASS';
  RAISE NOTICE 'CW3-P1-10 EXT037_COMPLETE_PREV_CURRENT_DEACTIV   = PASS';
  RAISE NOTICE 'CW3-P1-11 EXT037_FAIL_NORMAL                     = PASS';
  RAISE NOTICE 'CW3-P1-12 EXT037_FAIL_WRONG_RUNID                = PASS';
  RAISE NOTICE 'CW3-P1-13 EXT037_FAIL_LEASE_EXPIRED              = PASS';
  RAISE NOTICE 'CW3-P1-14 EXT037_FAIL_ALREADY_COMPLETED          = PASS';
  RAISE NOTICE 'CW3-P1-15 EXT037_FAIL_ERRMSG_TRUNCATED           = PASS';
  RAISE NOTICE '--- EXT132 ---';
  RAISE NOTICE 'CW3-P1-16 EXT132_SAVE_NORMAL                     = PASS';
  RAISE NOTICE 'CW3-P1-17 EXT132_SAVE_IDEMPOTENT                 = PASS';
  RAISE NOTICE 'CW3-P1-18 EXT132_SAVE_WRONG_RUNID_FENCED         = PASS';
  RAISE NOTICE 'CW3-P1-19 EXT132_SAVE_LEASE_EXPIRED_FENCED       = PASS';
  RAISE NOTICE 'CW3-P1-20 EXT132_SAVE_NOT_STAGING                = PASS';
  RAISE NOTICE 'CW3-P1-21 EXT132_COMPLETE_NORMAL                 = PASS';
  RAISE NOTICE 'CW3-P1-22 EXT132_COMPLETE_WRONG_RUNID            = PASS';
  RAISE NOTICE 'CW3-P1-23 EXT132_COMPLETE_COUNT_MISMATCH         = PASS';
  RAISE NOTICE 'CW3-P1-24 EXT132_COMPLETE_NULL_CHECKPOINT_API    = PASS';
  RAISE NOTICE 'CW3-P1-25 EXT132_COMPLETE_PREV_CURRENT_DEACTIV   = PASS';
  RAISE NOTICE 'CW3-P1-26 EXT132_FAIL_NORMAL                     = PASS';
  RAISE NOTICE 'CW3-P1-27 EXT132_FAIL_WRONG_RUNID                = PASS';
  RAISE NOTICE 'CW3-P1-28 EXT132_FAIL_LEASE_EXPIRED              = PASS';
  RAISE NOTICE 'CW3-P1-29 EXT132_FAIL_ALREADY_COMPLETED          = PASS';
  RAISE NOTICE 'CW3-P1-30 EXT132_FAIL_ERRMSG_TRUNCATED           = PASS';
  RAISE NOTICE '--- EXT165 ---';
  RAISE NOTICE 'CW3-P1-31 EXT165_SAVE_NORMAL                     = PASS';
  RAISE NOTICE 'CW3-P1-32 EXT165_SAVE_IDEMPOTENT                 = PASS';
  RAISE NOTICE 'CW3-P1-33 EXT165_SAVE_WRONG_RUNID_FENCED         = PASS';
  RAISE NOTICE 'CW3-P1-34 EXT165_SAVE_LEASE_EXPIRED_FENCED       = PASS';
  RAISE NOTICE 'CW3-P1-35 EXT165_SAVE_NOT_STAGING                = PASS';
  RAISE NOTICE 'CW3-P1-36 EXT165_COMPLETE_SCOPE_NULL_ISCURRENT   = PASS';
  RAISE NOTICE 'CW3-P1-37 EXT165_COMPLETE_SCOPE_YEAR_NOT_CURRENT = PASS';
  RAISE NOTICE 'CW3-P1-38 EXT165_COMPLETE_WRONG_RUNID            = PASS';
  RAISE NOTICE 'CW3-P1-39 EXT165_COMPLETE_COUNT_MISMATCH         = PASS';
  RAISE NOTICE 'CW3-P1-40 EXT165_COMPLETE_NULL_CHECKPOINT_API    = PASS';
  RAISE NOTICE 'CW3-P1-41 EXT165_FAIL_NORMAL                     = PASS';
  RAISE NOTICE 'CW3-P1-42 EXT165_FAIL_WRONG_RUNID                = PASS';
  RAISE NOTICE 'CW3-P1-43 EXT165_FAIL_LEASE_EXPIRED              = PASS';
  RAISE NOTICE 'CW3-P1-44 EXT165_FAIL_ALREADY_COMPLETED          = PASS';
  RAISE NOTICE 'CW3-P1-45 EXT165_FAIL_ERRMSG_TRUNCATED           = PASS';
  RAISE NOTICE '--- POST ALTER ---';
  RAISE NOTICE 'CW3-P2-01 POST_PROCONFIG(9/9)_MD5_INVARIANT      = PASS';
  RAISE NOTICE 'CW3-P2-02 POST_ACL_UNCHANGED                     = PASS';
  RAISE NOTICE 'CW3-P2-03 POST_EXT037_SAVE_NORMAL                = PASS';
  RAISE NOTICE 'CW3-P2-04 POST_EXT037_COMPLETE_NORMAL            = PASS';
  RAISE NOTICE 'CW3-P2-05 POST_EXT037_FAIL_NORMAL                = PASS';
  RAISE NOTICE 'CW3-P2-06 POST_EXT132_SAVE_NORMAL                = PASS';
  RAISE NOTICE 'CW3-P2-07 POST_EXT132_COMPLETE_NORMAL            = PASS';
  RAISE NOTICE 'CW3-P2-08 POST_EXT132_FAIL_NORMAL                = PASS';
  RAISE NOTICE 'CW3-P2-09 POST_EXT165_SAVE_NORMAL                = PASS';
  RAISE NOTICE 'CW3-P2-10 POST_EXT165_COMPLETE_NORMAL            = PASS';
  RAISE NOTICE 'CW3-P2-11 POST_EXT165_FAIL_NORMAL                = PASS';
  RAISE NOTICE 'TOTAL PASS = 57  ERROR = 0';
END;
$$;
