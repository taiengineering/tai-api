-- WO-TAI-SEC-SEARCHPATH-REM97-CW1-C3-SOURCE-001
-- CW1 격리 회귀 실행: BASELINE → PHASE1(pre-ALTER) → ALTER → PHASE2(post-ALTER)
-- Run AFTER setup_cw1.sql

SET search_path = public;

-- 테이블 초기화 (격리 환경 시작 상태 보장)
TRUNCATE public.search_index_outbox;

-- ─────────────────────────────────────────────────────────────────────────────
-- 기준선 검증 (proconfig=NULL, MD5 5건)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_sigs  CONSTANT text[] := ARRAY[
    'public.enqueue_search_index_sync(text,text,text,text,text)',
    'public.claim_search_index_events(text,integer,integer)',
    'public.complete_search_index_event(bigint,text)',
    'public.fail_search_index_event(bigint,text,text,integer,integer)',
    'public.requeue_search_index_event(bigint,text,integer,text)'
  ];
  c_md5s  CONSTANT text[] := ARRAY[
    '7d8b51f36863d9db97c7ca7697698cfc',
    '3bf08de5bac6052dae0f3fa443c8848b',
    '93972b922b6586b1c08919cc440ff5e3',
    'bd91ea673e17a08dc2992eec23f7467f',
    'bce20988f05bf91251c0976e0e520629'
  ];
  v_oid       oid;
  v_body_md5  text;
  v_proconfig text[];
  i           int;
BEGIN
  FOR i IN 1..5 LOOP
    v_oid := to_regprocedure(c_sigs[i])::oid;
    IF v_oid IS NULL THEN
      RAISE EXCEPTION 'BASELINE FAILED: % not found', c_sigs[i];
    END IF;
    SELECT md5(p.prosrc), p.proconfig INTO v_body_md5, v_proconfig
    FROM pg_proc p WHERE p.oid = v_oid;
    IF v_body_md5 IS DISTINCT FROM c_md5s[i] THEN
      RAISE EXCEPTION 'BASELINE FAILED: % body_md5 mismatch (expected %, got %)', c_sigs[i], c_md5s[i], v_body_md5;
    END IF;
    IF v_proconfig IS NOT NULL THEN
      RAISE EXCEPTION 'BASELINE FAILED: % proconfig already set: %', c_sigs[i], v_proconfig;
    END IF;
    RAISE NOTICE 'BASELINE OK [%/5]: % MD5=% proconfig=NULL', i, c_sigs[i], c_md5s[i];
  END LOOP;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- PHASE 1: ALTER 전 상태 전이 테스트
-- ─────────────────────────────────────────────────────────────────────────────

-- CW1-P1-01: enqueue → PENDING 행 삽입 확인
DO $$
DECLARE
  v_id     bigint;
  v_status text;
BEGIN
  v_id := public.enqueue_search_index_sync(
    'test_domain', 'test_type', 'canonical_p1_01', 'event_key_p1_01', 'p1-01 enqueue test'
  );
  IF v_id IS NULL THEN
    RAISE EXCEPTION 'CW1-P1-01 FAILED: enqueue returned NULL';
  END IF;
  SELECT status INTO v_status FROM public.search_index_outbox WHERE id = v_id;
  IF v_status IS DISTINCT FROM 'PENDING' THEN
    RAISE EXCEPTION 'CW1-P1-01 FAILED: expected PENDING, got %', v_status;
  END IF;
  RAISE NOTICE 'CW1-P1-01: PASS — enqueue id=% status=PENDING', v_id;
END;
$$;

-- CW1-P1-02: 중복 event_key → ON CONFLICT DO NOTHING (NULL 반환)
DO $$
DECLARE
  v_id bigint;
BEGIN
  v_id := public.enqueue_search_index_sync(
    'test_domain', 'test_type', 'canonical_p1_01', 'event_key_p1_01', 'duplicate attempt'
  );
  IF v_id IS NOT NULL THEN
    RAISE EXCEPTION 'CW1-P1-02 FAILED: duplicate enqueue should return NULL, got %', v_id;
  END IF;
  -- 행 수 1개 유지 확인
  IF (SELECT COUNT(*) FROM public.search_index_outbox WHERE event_key = 'event_key_p1_01') IS DISTINCT FROM 1 THEN
    RAISE EXCEPTION 'CW1-P1-02 FAILED: duplicate event_key created extra row';
  END IF;
  RAISE NOTICE 'CW1-P1-02: PASS — duplicate event_key ON CONFLICT DO NOTHING (returned NULL, count=1)';
END;
$$;

-- CW1-P1-03: claim → CLAIMED 상태 전이
DO $$
DECLARE
  v_id2    bigint;
  v_count  int;
BEGIN
  -- 두 번째 이벤트 추가 (batch 테스트)
  v_id2 := public.enqueue_search_index_sync(
    'test_domain', 'test_type', 'canonical_p1_03', 'event_key_p1_03', 'p1-03 claim test'
  );
  SELECT COUNT(*) INTO v_count FROM public.claim_search_index_events('worker_A', 10, 60);
  IF v_count = 0 THEN
    RAISE EXCEPTION 'CW1-P1-03 FAILED: claim returned 0 rows';
  END IF;
  -- PENDING 행 0개 확인 (가용 행 전부 CLAIMED)
  IF EXISTS (
    SELECT 1 FROM public.search_index_outbox
    WHERE status = 'PENDING' AND available_at <= NOW()
  ) THEN
    RAISE EXCEPTION 'CW1-P1-03 FAILED: PENDING rows remain after claim';
  END IF;
  -- 반환된 행들이 CLAIMED인지 확인
  IF EXISTS (
    SELECT 1 FROM public.search_index_outbox
    WHERE worker_id = 'worker_A' AND status IS DISTINCT FROM 'CLAIMED'
  ) THEN
    RAISE EXCEPTION 'CW1-P1-03 FAILED: worker_A rows not all CLAIMED';
  END IF;
  RAISE NOTICE 'CW1-P1-03: PASS — claim % row(s) → CLAIMED (worker_A)', v_count;
END;
$$;

-- CW1-P1-04: complete → COMPLETED 상태 전이 (fence=FALSE)
DO $$
DECLARE
  v_id     bigint;
  v_result boolean;
  v_status text;
BEGIN
  SELECT id INTO v_id
  FROM public.search_index_outbox
  WHERE status = 'CLAIMED' AND worker_id = 'worker_A'
  LIMIT 1;
  IF v_id IS NULL THEN
    RAISE EXCEPTION 'CW1-P1-04 FAILED: no CLAIMED row for worker_A';
  END IF;
  v_result := public.complete_search_index_event(v_id, 'worker_A');
  IF v_result IS DISTINCT FROM TRUE THEN
    RAISE EXCEPTION 'CW1-P1-04 FAILED: complete returned % (expected TRUE)', v_result;
  END IF;
  SELECT status INTO v_status FROM public.search_index_outbox WHERE id = v_id;
  IF v_status IS DISTINCT FROM 'COMPLETED' THEN
    RAISE EXCEPTION 'CW1-P1-04 FAILED: expected COMPLETED, got %', v_status;
  END IF;
  RAISE NOTICE 'CW1-P1-04: PASS — complete id=% → COMPLETED (fence=FALSE)', v_id;
END;
$$;

-- CW1-P1-05: complete with fence=TRUE → FALSE 반환, 상태 불변
DO $$
DECLARE
  v_id     bigint;
  v_result boolean;
  v_status text;
BEGIN
  -- CLAIMED 상태 행 확인 (P1-03에서 2건 중 1건이 남아있음)
  SELECT id INTO v_id
  FROM public.search_index_outbox
  WHERE status = 'CLAIMED' AND worker_id = 'worker_A'
  LIMIT 1;
  IF v_id IS NULL THEN
    RAISE EXCEPTION 'CW1-P1-05 FAILED: no CLAIMED row available for fence test';
  END IF;

  -- fence 활성화
  UPDATE public.search_index_fence SET rebuild_active = TRUE WHERE id = 1;

  v_result := public.complete_search_index_event(v_id, 'worker_A');
  IF v_result IS DISTINCT FROM FALSE THEN
    UPDATE public.search_index_fence SET rebuild_active = FALSE WHERE id = 1;
    RAISE EXCEPTION 'CW1-P1-05 FAILED: expected FALSE when fence=TRUE, got %', v_result;
  END IF;
  SELECT status INTO v_status FROM public.search_index_outbox WHERE id = v_id;
  IF v_status IS DISTINCT FROM 'CLAIMED' THEN
    UPDATE public.search_index_fence SET rebuild_active = FALSE WHERE id = 1;
    RAISE EXCEPTION 'CW1-P1-05 FAILED: status changed to % when fence=TRUE', v_status;
  END IF;

  -- fence 복원
  UPDATE public.search_index_fence SET rebuild_active = FALSE WHERE id = 1;
  RAISE NOTICE 'CW1-P1-05: PASS — complete returns FALSE when fence=TRUE, status stays CLAIMED (id=%)', v_id;
END;
$$;

-- CW1-P1-06: fail (attempt < max) → PENDING + 재시도 지연
DO $$
DECLARE
  v_id      bigint;
  v_attempt int;
  v_status  text;
  v_avail   timestamptz;
BEGIN
  -- 전용 행 준비 (이전 테스트와 격리)
  PERFORM public.enqueue_search_index_sync(
    'test_domain', 'test_type', 'canonical_p1_06', 'event_key_p1_06', 'p1-06 fail retry test'
  );
  PERFORM * FROM public.claim_search_index_events('worker_B', 10, 60);

  SELECT id, attempt_no INTO v_id, v_attempt
  FROM public.search_index_outbox
  WHERE status = 'CLAIMED' AND worker_id = 'worker_B' AND event_key = 'event_key_p1_06';
  IF v_id IS NULL THEN
    RAISE EXCEPTION 'CW1-P1-06 FAILED: no CLAIMED row for worker_B/event_key_p1_06';
  END IF;

  PERFORM public.fail_search_index_event(v_id, 'transient error', 'worker_B', v_attempt, 5);
  SELECT status, available_at INTO v_status, v_avail
  FROM public.search_index_outbox WHERE id = v_id;
  IF v_status IS DISTINCT FROM 'PENDING' THEN
    RAISE EXCEPTION 'CW1-P1-06 FAILED: expected PENDING after fail retry, got %', v_status;
  END IF;
  -- available_at 미래로 설정 확인 (지수 지연)
  IF v_avail <= NOW() THEN
    RAISE EXCEPTION 'CW1-P1-06 FAILED: available_at not in future (got %)', v_avail;
  END IF;
  RAISE NOTICE 'CW1-P1-06: PASS — fail (attempt=% < max=5) → PENDING, available_at=%', v_attempt, v_avail;
END;
$$;

-- CW1-P1-07: fail (attempt >= max) → DEAD
DO $$
DECLARE
  v_id      bigint;
  v_attempt int;
  v_status  text;
  v_reason  text;
BEGIN
  PERFORM public.enqueue_search_index_sync(
    'test_domain', 'test_type', 'canonical_p1_07', 'event_key_p1_07', 'p1-07 fail dead test'
  );
  PERFORM * FROM public.claim_search_index_events('worker_C', 10, 60);

  SELECT id, attempt_no INTO v_id, v_attempt
  FROM public.search_index_outbox
  WHERE status = 'CLAIMED' AND worker_id = 'worker_C' AND event_key = 'event_key_p1_07';
  IF v_id IS NULL THEN
    RAISE EXCEPTION 'CW1-P1-07 FAILED: no CLAIMED row for worker_C/event_key_p1_07';
  END IF;

  -- max_attempts = attempt_no (현재 시도 횟수 = 한계)
  PERFORM public.fail_search_index_event(v_id, 'permanent failure', 'worker_C', v_attempt, v_attempt);
  SELECT status, failure_reason INTO v_status, v_reason
  FROM public.search_index_outbox WHERE id = v_id;
  IF v_status IS DISTINCT FROM 'DEAD' THEN
    RAISE EXCEPTION 'CW1-P1-07 FAILED: expected DEAD (attempt=max=%), got %', v_attempt, v_status;
  END IF;
  IF v_reason IS DISTINCT FROM 'permanent failure' THEN
    RAISE EXCEPTION 'CW1-P1-07 FAILED: failure_reason mismatch (got %)', v_reason;
  END IF;
  RAISE NOTICE 'CW1-P1-07: PASS — fail (attempt=% >= max=%) → DEAD', v_attempt, v_attempt;
END;
$$;

-- CW1-P1-08: requeue → PENDING + claimed_by/worker_id/lease_until 초기화
DO $$
DECLARE
  v_id          bigint;
  v_attempt     int;
  v_status      text;
  v_worker      text;
  v_claimed_by  text;
  v_lease_until timestamptz;
BEGIN
  PERFORM public.enqueue_search_index_sync(
    'test_domain', 'test_type', 'canonical_p1_08', 'event_key_p1_08', 'p1-08 requeue test'
  );
  PERFORM * FROM public.claim_search_index_events('worker_D', 10, 60);

  SELECT id, attempt_no INTO v_id, v_attempt
  FROM public.search_index_outbox
  WHERE status = 'CLAIMED' AND worker_id = 'worker_D' AND event_key = 'event_key_p1_08';
  IF v_id IS NULL THEN
    RAISE EXCEPTION 'CW1-P1-08 FAILED: no CLAIMED row for worker_D/event_key_p1_08';
  END IF;

  PERFORM public.requeue_search_index_event(v_id, 'worker_D', v_attempt, 'manual requeue');
  SELECT status, worker_id, claimed_by, lease_until
  INTO v_status, v_worker, v_claimed_by, v_lease_until
  FROM public.search_index_outbox WHERE id = v_id;

  IF v_status IS DISTINCT FROM 'PENDING' THEN
    RAISE EXCEPTION 'CW1-P1-08 FAILED: expected PENDING, got %', v_status;
  END IF;
  IF v_worker IS NOT NULL THEN
    RAISE EXCEPTION 'CW1-P1-08 FAILED: worker_id should be NULL, got %', v_worker;
  END IF;
  IF v_claimed_by IS NOT NULL THEN
    RAISE EXCEPTION 'CW1-P1-08 FAILED: claimed_by should be NULL, got %', v_claimed_by;
  END IF;
  IF v_lease_until IS NOT NULL THEN
    RAISE EXCEPTION 'CW1-P1-08 FAILED: lease_until should be NULL, got %', v_lease_until;
  END IF;
  RAISE NOTICE 'CW1-P1-08: PASS — requeue id=% → PENDING worker=NULL claimed_by=NULL lease_until=NULL', v_id;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- ALTER: search_path 고정 (Migration STEP 2 동일)
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
-- PHASE 2: ALTER 후 검증
-- ─────────────────────────────────────────────────────────────────────────────

-- CW1-P2-01: proconfig 설정 확인 + MD5/INVOKER/volatility/parallel 불변 (5건)
DO $$
DECLARE
  c_sigs        CONSTANT text[] := ARRAY[
    'public.enqueue_search_index_sync(text,text,text,text,text)',
    'public.claim_search_index_events(text,integer,integer)',
    'public.complete_search_index_event(bigint,text)',
    'public.fail_search_index_event(bigint,text,text,integer,integer)',
    'public.requeue_search_index_event(bigint,text,integer,text)'
  ];
  c_md5s        CONSTANT text[] := ARRAY[
    '7d8b51f36863d9db97c7ca7697698cfc',
    '3bf08de5bac6052dae0f3fa443c8848b',
    '93972b922b6586b1c08919cc440ff5e3',
    'bd91ea673e17a08dc2992eec23f7467f',
    'bce20988f05bf91251c0976e0e520629'
  ];
  c_search_path CONSTANT text := 'search_path=pg_catalog, public, pg_temp';
  v_oid       oid;
  v_body_md5  text;
  v_proconfig text[];
  v_secdef    bool;
  v_volat     char;
  v_parallel  char;
  i           int;
BEGIN
  FOR i IN 1..5 LOOP
    v_oid := to_regprocedure(c_sigs[i])::oid;
    IF v_oid IS NULL THEN
      RAISE EXCEPTION 'CW1-P2-01 FAILED: % not found', c_sigs[i];
    END IF;
    SELECT p.proconfig, md5(p.prosrc), p.prosecdef, p.provolatile, p.proparallel
    INTO v_proconfig, v_body_md5, v_secdef, v_volat, v_parallel
    FROM pg_proc p WHERE p.oid = v_oid;
    IF v_proconfig IS DISTINCT FROM ARRAY[c_search_path]::text[] THEN
      RAISE EXCEPTION 'CW1-P2-01 FAILED: % proconfig mismatch: %', c_sigs[i], v_proconfig;
    END IF;
    IF v_body_md5 IS DISTINCT FROM c_md5s[i] THEN
      RAISE EXCEPTION 'CW1-P2-01 FAILED: % prosrc_md5 changed (got %)', c_sigs[i], v_body_md5;
    END IF;
    IF v_secdef IS DISTINCT FROM false THEN
      RAISE EXCEPTION 'CW1-P2-01 FAILED: % prosecdef changed', c_sigs[i];
    END IF;
    IF v_volat IS DISTINCT FROM 'v' THEN
      RAISE EXCEPTION 'CW1-P2-01 FAILED: % volatility changed to %', c_sigs[i], v_volat;
    END IF;
    IF v_parallel IS DISTINCT FROM 'u' THEN
      RAISE EXCEPTION 'CW1-P2-01 FAILED: % proparallel changed to %', c_sigs[i], v_parallel;
    END IF;
    RAISE NOTICE 'CW1-P2-01 OK [%/5]: % proconfig=[%] MD5=%',
      i, c_sigs[i], c_search_path, c_md5s[i];
  END LOOP;
END;
$$;

-- CW1-P2-02: ALTER 후 enqueue → PENDING 동작 불변
DO $$
DECLARE
  v_id     bigint;
  v_status text;
BEGIN
  v_id := public.enqueue_search_index_sync(
    'test_post', 'test_type', 'canonical_p2_02', 'event_key_p2_02', 'post-ALTER enqueue test'
  );
  IF v_id IS NULL THEN
    RAISE EXCEPTION 'CW1-P2-02 FAILED: post-ALTER enqueue returned NULL';
  END IF;
  SELECT status INTO v_status FROM public.search_index_outbox WHERE id = v_id;
  IF v_status IS DISTINCT FROM 'PENDING' THEN
    RAISE EXCEPTION 'CW1-P2-02 FAILED: expected PENDING, got %', v_status;
  END IF;
  RAISE NOTICE 'CW1-P2-02: PASS — post-ALTER enqueue id=% status=PENDING', v_id;
END;
$$;

-- CW1-P2-03: ALTER 후 claim → CLAIMED 동작 불변
DO $$
DECLARE
  v_count int;
BEGIN
  SELECT COUNT(*) INTO v_count FROM public.claim_search_index_events('worker_E', 10, 60);
  IF v_count = 0 THEN
    RAISE EXCEPTION 'CW1-P2-03 FAILED: post-ALTER claim returned 0 rows';
  END IF;
  RAISE NOTICE 'CW1-P2-03: PASS — post-ALTER claim % row(s) → CLAIMED', v_count;
END;
$$;

-- CW1-P2-04: ALTER 후 complete → COMPLETED 동작 불변
DO $$
DECLARE
  v_id     bigint;
  v_result boolean;
  v_status text;
BEGIN
  SELECT id INTO v_id
  FROM public.search_index_outbox
  WHERE status = 'CLAIMED' AND worker_id = 'worker_E'
  LIMIT 1;
  IF v_id IS NULL THEN
    RAISE EXCEPTION 'CW1-P2-04 FAILED: no CLAIMED row for worker_E';
  END IF;
  v_result := public.complete_search_index_event(v_id, 'worker_E');
  IF v_result IS DISTINCT FROM TRUE THEN
    RAISE EXCEPTION 'CW1-P2-04 FAILED: post-ALTER complete returned % (expected TRUE)', v_result;
  END IF;
  SELECT status INTO v_status FROM public.search_index_outbox WHERE id = v_id;
  IF v_status IS DISTINCT FROM 'COMPLETED' THEN
    RAISE EXCEPTION 'CW1-P2-04 FAILED: expected COMPLETED, got %', v_status;
  END IF;
  RAISE NOTICE 'CW1-P2-04: PASS — post-ALTER complete id=% → COMPLETED', v_id;
END;
$$;

-- CW1-P2-05: ALTER 후 fail retry → PENDING 동작 불변
DO $$
DECLARE
  v_id      bigint;
  v_attempt int;
  v_status  text;
BEGIN
  PERFORM public.enqueue_search_index_sync(
    'test_post', 'test_type', 'canonical_p2_05', 'event_key_p2_05', 'post-ALTER fail retry'
  );
  PERFORM * FROM public.claim_search_index_events('worker_F', 10, 60);

  SELECT id, attempt_no INTO v_id, v_attempt
  FROM public.search_index_outbox
  WHERE status = 'CLAIMED' AND worker_id = 'worker_F' AND event_key = 'event_key_p2_05';
  IF v_id IS NULL THEN
    RAISE EXCEPTION 'CW1-P2-05 FAILED: no CLAIMED row for worker_F/event_key_p2_05';
  END IF;

  PERFORM public.fail_search_index_event(v_id, 'transient post-alter', 'worker_F', v_attempt, 5);
  SELECT status INTO v_status FROM public.search_index_outbox WHERE id = v_id;
  IF v_status IS DISTINCT FROM 'PENDING' THEN
    RAISE EXCEPTION 'CW1-P2-05 FAILED: expected PENDING after fail retry, got %', v_status;
  END IF;
  RAISE NOTICE 'CW1-P2-05: PASS — post-ALTER fail (attempt=% < max=5) → PENDING', v_attempt;
END;
$$;

-- CW1-P2-06: ALTER 후 requeue → PENDING + worker 정보 초기화 동작 불변
DO $$
DECLARE
  v_id          bigint;
  v_attempt     int;
  v_status      text;
  v_worker      text;
  v_claimed_by  text;
  v_lease_until timestamptz;
BEGIN
  PERFORM public.enqueue_search_index_sync(
    'test_post', 'test_type', 'canonical_p2_06', 'event_key_p2_06', 'post-ALTER requeue'
  );
  PERFORM * FROM public.claim_search_index_events('worker_G', 10, 60);

  SELECT id, attempt_no INTO v_id, v_attempt
  FROM public.search_index_outbox
  WHERE status = 'CLAIMED' AND worker_id = 'worker_G' AND event_key = 'event_key_p2_06';
  IF v_id IS NULL THEN
    RAISE EXCEPTION 'CW1-P2-06 FAILED: no CLAIMED row for worker_G/event_key_p2_06';
  END IF;

  PERFORM public.requeue_search_index_event(v_id, 'worker_G', v_attempt, 'post-ALTER requeue');
  SELECT status, worker_id, claimed_by, lease_until
  INTO v_status, v_worker, v_claimed_by, v_lease_until
  FROM public.search_index_outbox WHERE id = v_id;

  IF v_status IS DISTINCT FROM 'PENDING' THEN
    RAISE EXCEPTION 'CW1-P2-06 FAILED: expected PENDING, got %', v_status;
  END IF;
  IF v_worker IS NOT NULL THEN
    RAISE EXCEPTION 'CW1-P2-06 FAILED: worker_id should be NULL, got %', v_worker;
  END IF;
  IF v_claimed_by IS NOT NULL THEN
    RAISE EXCEPTION 'CW1-P2-06 FAILED: claimed_by should be NULL, got %', v_claimed_by;
  END IF;
  IF v_lease_until IS NOT NULL THEN
    RAISE EXCEPTION 'CW1-P2-06 FAILED: lease_until should be NULL, got %', v_lease_until;
  END IF;
  RAISE NOTICE 'CW1-P2-06: PASS — post-ALTER requeue id=% → PENDING worker=NULL', v_id;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- 최종 결과 요약
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
  RAISE NOTICE '';
  RAISE NOTICE '=== CW1 ISOLATED REGRESSION RESULT ===';
  RAISE NOTICE 'BASELINE MD5_MATCH(5/5)            = PASS';
  RAISE NOTICE 'CW1-P1-01 ENQUEUE_PENDING          = PASS';
  RAISE NOTICE 'CW1-P1-02 DUPLICATE_CONFLICT       = PASS';
  RAISE NOTICE 'CW1-P1-03 CLAIM_CLAIMED            = PASS';
  RAISE NOTICE 'CW1-P1-04 COMPLETE_COMPLETED       = PASS';
  RAISE NOTICE 'CW1-P1-05 COMPLETE_FENCE_BLOCKED   = PASS';
  RAISE NOTICE 'CW1-P1-06 FAIL_RETRY_PENDING       = PASS';
  RAISE NOTICE 'CW1-P1-07 FAIL_MAX_DEAD            = PASS';
  RAISE NOTICE 'CW1-P1-08 REQUEUE_PENDING_CLEARED  = PASS';
  RAISE NOTICE 'CW1-P2-01 POST_PROCONFIG(5/5)      = PASS';
  RAISE NOTICE 'CW1-P2-02 POST_ENQUEUE             = PASS';
  RAISE NOTICE 'CW1-P2-03 POST_CLAIM               = PASS';
  RAISE NOTICE 'CW1-P2-04 POST_COMPLETE            = PASS';
  RAISE NOTICE 'CW1-P2-05 POST_FAIL_RETRY          = PASS';
  RAISE NOTICE 'CW1-P2-06 POST_REQUEUE             = PASS';
  RAISE NOTICE 'ERROR = 0';
END;
$$;
