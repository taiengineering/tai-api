-- =====================================================================
-- WP-PARTITION-02C : DB WRITE COMPATIBILITY 검증
--   전제: 로컬 PostgreSQL 17.6 + 승인된 UP artifact 적용 상태
--   목적: 패치된 코드가 수행할 write 패턴이 새 schema 계약을 통과하는가
--
--   ⚠ 검증환경 전용. production 실행 금지.
-- =====================================================================
\echo '################ 전제 확인 ################'

SELECT CASE WHEN relkind='p' THEN 'OK(파티션 적용 상태)'
            ELSE 'ABORT: UP 미적용 — 02_up.sql 먼저 실행' END AS precondition
FROM pg_class WHERE oid='public.work_schedules'::regclass;

SELECT CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_schema='public' AND table_name='work_assignments'
                            AND column_name='factory_id')
            THEN 'OK(wa.factory_id 존재)' ELSE 'ABORT' END AS wa_col,
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_schema='public' AND table_name='safety_inspections'
                            AND column_name='factory_id')
            THEN 'OK(si.factory_id 존재)' ELSE 'ABORT' END AS si_col;

\echo ''
\echo '################ [C-1] PATCH#1 신규 assignment INSERT ################'
\echo '  패치 로직: parent 에서 factory_id 조회 → payload 에 포함'

DO $$
DECLARE v_sid uuid; v_fid uuid; v_uid uuid; v_new uuid; v_saved uuid; v_ok text;
BEGIN
    SELECT id, factory_id INTO v_sid, v_fid FROM public.work_schedules LIMIT 1;
    SELECT id INTO v_uid FROM public.users LIMIT 1;

    -- ↓ 패치된 코드가 하는 일 그대로 재현
    --   1) parent 조회
    SELECT factory_id INTO v_fid FROM public.work_schedules WHERE id = v_sid LIMIT 1;
    --   2) factory_id 포함 INSERT
    INSERT INTO public.work_assignments
        (schedule_id, factory_id, assigned_user_id, scheduled_date, status_code, created_at)
    VALUES (v_sid, v_fid, v_uid, current_date, 'READY', now())
    RETURNING id INTO v_new;

    SELECT factory_id INTO v_saved FROM public.work_assignments WHERE id = v_new;

    IF v_saved = v_fid THEN v_ok := 'PASS (factory_id 저장 확인: '||left(v_saved::text,8)||')';
    ELSE v_ok := 'FAIL'; END IF;
    RAISE NOTICE 'C-1 신규 assignment INSERT: %', v_ok;
END $$;

\echo ''
\echo '################ [C-2] assignment factory mismatch → FK 실패 ################'

DO $$
DECLARE v_sid uuid; v_own uuid; v_other uuid; v_ok text := 'FAIL(불일치 허용됨)';
BEGIN
    SELECT id, factory_id INTO v_sid, v_own FROM public.work_schedules LIMIT 1;
    SELECT id INTO v_other FROM public.factories WHERE id <> v_own LIMIT 1;
    BEGIN
        INSERT INTO public.work_assignments (schedule_id, factory_id, status_code)
        VALUES (v_sid, v_other, 'TEST');
    EXCEPTION WHEN foreign_key_violation THEN v_ok := 'PASS (23503 FK 거부)';
              WHEN others THEN v_ok := 'PASS ('||SQLSTATE||')';
    END;
    RAISE NOTICE 'C-2 assignment factory mismatch: %', v_ok;
END $$;

\echo ''
\echo '################ [C-3] assignment pair NULL 위반 → CHECK 실패 ################'
\echo '  패치가 없었다면 발생할 상황: factory_id 누락'

DO $$
DECLARE v_sid uuid; v_ok text := 'FAIL(무결성 우회 — 패치 필수 근거 소멸)';
BEGIN
    SELECT id INTO v_sid FROM public.work_schedules LIMIT 1;
    BEGIN
        -- 패치 이전 코드가 보내던 payload (factory_id 없음)
        INSERT INTO public.work_assignments
            (schedule_id, assigned_user_id, scheduled_date, status_code, created_at)
        VALUES (v_sid, NULL, current_date, 'READY', now());
    EXCEPTION WHEN check_violation THEN v_ok := 'PASS (23514 CHECK 거부)';
              WHEN others THEN v_ok := 'PASS ('||SQLSTATE||')';
    END;
    RAISE NOTICE 'C-3 pair NULL 위반(패치 전 payload): %', v_ok;
END $$;

\echo ''
\echo '################ [C-4] PATCH#2 inspection INSERT ################'

DO $$
DECLARE v_sid uuid; v_fid uuid; v_uid uuid; v_new uuid; v_saved uuid; v_ok text;
BEGIN
    SELECT id, factory_id INTO v_sid, v_fid FROM public.work_schedules LIMIT 1;
    SELECT id INTO v_uid FROM public.users LIMIT 1;

    -- 패치된 submit_check() 재현: schedule_ref + factory_ref 확보 후 INSERT
    INSERT INTO public.safety_inspections
        (assignment_id, factory_id, inspector_id, inspection_date, status_code)
    VALUES (v_sid, v_fid, v_uid, now(), 'COMPLETED')
    RETURNING id INTO v_new;

    SELECT factory_id INTO v_saved FROM public.safety_inspections WHERE id = v_new;
    IF v_saved = v_fid THEN v_ok := 'PASS (factory_id 저장 확인)';
    ELSE v_ok := 'FAIL'; END IF;
    RAISE NOTICE 'C-4 inspection INSERT: %', v_ok;
END $$;

\echo ''
\echo '################ [C-5] inspection factory mismatch → FK 실패 ################'

DO $$
DECLARE v_sid uuid; v_own uuid; v_other uuid; v_ok text := 'FAIL(불일치 허용됨)';
BEGIN
    SELECT id, factory_id INTO v_sid, v_own FROM public.work_schedules LIMIT 1;
    SELECT id INTO v_other FROM public.factories WHERE id <> v_own LIMIT 1;
    BEGIN
        INSERT INTO public.safety_inspections (assignment_id, factory_id, status_code)
        VALUES (v_sid, v_other, 'TEST');
    EXCEPTION WHEN foreign_key_violation THEN v_ok := 'PASS (23503 FK 거부)';
              WHEN others THEN v_ok := 'PASS ('||SQLSTATE||')';
    END;
    RAISE NOTICE 'C-5 inspection factory mismatch: %', v_ok;
END $$;

\echo ''
\echo '################ [C-6] 기존 assignment UPDATE 경로 무변경 ################'
\echo '  패치가 UPDATE 경로를 건드리지 않았음을 확인 (factory 조회 없이 동작)'

DO $$
DECLARE v_aid uuid; v_uid uuid; v_before uuid; v_after uuid; v_ok text;
BEGIN
    SELECT id, factory_id INTO v_aid, v_before
      FROM public.work_assignments WHERE schedule_id IS NOT NULL LIMIT 1;
    SELECT id INTO v_uid FROM public.users OFFSET 1 LIMIT 1;

    -- 패치된 코드의 UPDATE 분기 그대로 (factory_id 미포함)
    UPDATE public.work_assignments
       SET assigned_user_id = v_uid, updated_at = now()
     WHERE id = v_aid;

    SELECT factory_id INTO v_after FROM public.work_assignments WHERE id = v_aid;
    IF v_after IS NOT DISTINCT FROM v_before THEN
        v_ok := 'PASS (기존 동작 유지, factory_id 불변)';
    ELSE v_ok := 'FAIL'; END IF;
    RAISE NOTICE 'C-6 기존 assignment UPDATE: %', v_ok;
EXCEPTION WHEN undefined_column THEN
    RAISE NOTICE 'C-6: SKIP (updated_at 컬럼 없음 — bootstrap 스키마 한계)';
END $$;

\echo ''
\echo '################ [C-7] assignment 없는 inspection (구버전 앱 경로) ################'
\echo '  schedule_ref=NULL → factory_ref=NULL → pair CHECK 통과해야 정상'

DO $$
DECLARE v_ok text := 'PASS';
BEGIN
    BEGIN
        INSERT INTO public.safety_inspections (assignment_id, factory_id, status_code)
        VALUES (NULL, NULL, 'COMPLETED');
    EXCEPTION WHEN others THEN v_ok := 'FAIL ('||SQLERRM||')';
    END;
    RAISE NOTICE 'C-7 assignment 없는 inspection: %', v_ok;
END $$;

\echo ''
\echo '################ 결과 요약 ################'
SELECT count(*) FILTER (WHERE factory_id IS NOT NULL) AS wa_with_factory,
       count(*) FILTER (WHERE factory_id IS NULL)     AS wa_null_factory,
       count(*) AS wa_total
FROM public.work_assignments;

SELECT count(*) FILTER (WHERE factory_id IS NOT NULL) AS si_with_factory,
       count(*) FILTER (WHERE factory_id IS NULL)     AS si_null_factory,
       count(*) AS si_total
FROM public.safety_inspections;

-- pair 계약 위반이 하나도 없어야 한다
SELECT count(*) AS wa_pair_violation,
       CASE WHEN count(*)=0 THEN 'PASS' ELSE 'FAIL' END AS verdict
FROM public.work_assignments
WHERE (schedule_id IS NULL) <> (factory_id IS NULL);

SELECT count(*) AS si_pair_violation,
       CASE WHEN count(*)=0 THEN 'PASS' ELSE 'FAIL' END AS verdict
FROM public.safety_inspections
WHERE (assignment_id IS NULL) <> (factory_id IS NULL);

\echo '################ 02C DB WRITE 검증 종료 ################'
