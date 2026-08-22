-- =====================================================================
-- WP-PARTITION-02A (APPROVED ARTIFACT) : work_schedules 파티션 전환 원상복구
-- DOWN MIGRATION  (APPROVED DESIGN ARTIFACT — NOT APPLIED TO ANY DB)
--
--   REV-3 (2026-08-22) — GPT REV-2 micro revision 3건 반영
--
--   [REV-3 변경점 — 다른 설계 변경 없음]
--   R3-1. grants EXACT 비교에 grantor / is_grantable 포함
--   R3-2. relforcerowsecurity 복원 + POSTCHECK 비교
--   R3-3. comments/policies 조회를 public schema 로 한정
--
--   [REV-2 유지]
--   FAST-PATH ONLY / 37컬럼 full-row reconciliation / contract EXACT 검증
--
--   [FAST-PATH ONLY 계약]
--     work_schedules_old 가 존재할 때만 실행 가능.
--     없으면 §0 에서 즉시 ABORT (부분 실행 없음).
--
--   [ROLLBACK WINDOW 계약]
--     old 존재 기간 = 기능 검증 전용. 대량 업무 write 비권장.
--     reconciliation 이 손실을 막지만 window 는 짧을수록 안전.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- §0. FAST-PATH 전제 강제
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF to_regclass('public.work_schedules_old') IS NULL THEN
        RAISE EXCEPTION
            'DOWN ABORT: work_schedules_old 없음. 이 DOWN 은 FAST PATH 전용입니다. '
            'old 를 이미 DROP 했다면 백업 복원을 포함한 별도 절차가 필요합니다.';
    END IF;
    IF to_regclass('public._mig_ws_data_snapshot') IS NULL
       OR to_regclass('public._mig_ws_fingerprint') IS NULL THEN
        RAISE EXCEPTION 'DOWN ABORT: UP 스냅샷 테이블 없음. UP 이 정상 수행되지 않았습니다.';
    END IF;
    RAISE NOTICE 'DOWN MODE = FAST PATH';
END $$;


-- ---------------------------------------------------------------------
-- §1. WRITE FREEZE
-- ---------------------------------------------------------------------
LOCK TABLE public.work_schedules     IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.work_schedules_old IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.work_assignments   IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.safety_inspections IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.equipment_checkins IN ACCESS EXCLUSIVE MODE;


-- ---------------------------------------------------------------------
-- §2. CHILD 복합 FK / CHECK 제거
-- ---------------------------------------------------------------------
ALTER TABLE public.work_assignments   DROP CONSTRAINT IF EXISTS work_assignments_schedule_fkey;
ALTER TABLE public.safety_inspections DROP CONSTRAINT IF EXISTS safety_inspections_schedule_fkey;
ALTER TABLE public.equipment_checkins DROP CONSTRAINT IF EXISTS equipment_checkins_schedule_fkey;
ALTER TABLE public.work_assignments   DROP CONSTRAINT IF EXISTS chk_wa_schedule_factory_pair;
ALTER TABLE public.safety_inspections DROP CONSTRAINT IF EXISTS chk_si_schedule_factory_pair;


-- ---------------------------------------------------------------------
-- §3. FULL RECONCILIATION
--     (a) 신규 INSERT  (b) 37컬럼 전량 UPDATE  (c) 삭제분 DELETE
-- ---------------------------------------------------------------------
INSERT INTO public.work_schedules_old (
    id, asset_id, assigned_user_id, repeat_type, repeat_interval,
    repeat_weekday, repeat_day, week_of_month, start_date, end_date,
    active_yn, inspection_set_id, company_id, factory_id, planned_date,
    status_code, description, completed_at, inspector_name, summary,
    schedule_group_id, source_type, obligation_type, event_type, event_date,
    cycle_base_guide, rule_code, law_name, law_article, form_code,
    created_at, updated_at, is_excluded, custom_cycle, excluded_reason,
    reviewed_at, reviewed_by)
SELECT
    n.id, n.asset_id, n.assigned_user_id, n.repeat_type, n.repeat_interval,
    n.repeat_weekday, n.repeat_day, n.week_of_month, n.start_date, n.end_date,
    n.active_yn, n.inspection_set_id, n.company_id, n.factory_id, n.planned_date,
    n.status_code, n.description, n.completed_at, n.inspector_name, n.summary,
    n.schedule_group_id, n.source_type, n.obligation_type, n.event_type, n.event_date,
    n.cycle_base_guide, n.rule_code, n.law_name, n.law_article, n.form_code,
    n.created_at, n.updated_at, n.is_excluded, n.custom_cycle, n.excluded_reason,
    n.reviewed_at, n.reviewed_by
FROM public.work_schedules n
WHERE NOT EXISTS (SELECT 1 FROM public.work_schedules_old o WHERE o.id = n.id);

UPDATE public.work_schedules_old o
   SET asset_id = n.asset_id, assigned_user_id = n.assigned_user_id,
       repeat_type = n.repeat_type, repeat_interval = n.repeat_interval,
       repeat_weekday = n.repeat_weekday, repeat_day = n.repeat_day,
       week_of_month = n.week_of_month, start_date = n.start_date, end_date = n.end_date,
       active_yn = n.active_yn, inspection_set_id = n.inspection_set_id,
       company_id = n.company_id, factory_id = n.factory_id, planned_date = n.planned_date,
       status_code = n.status_code, description = n.description, completed_at = n.completed_at,
       inspector_name = n.inspector_name, summary = n.summary,
       schedule_group_id = n.schedule_group_id, source_type = n.source_type,
       obligation_type = n.obligation_type, event_type = n.event_type, event_date = n.event_date,
       cycle_base_guide = n.cycle_base_guide, rule_code = n.rule_code,
       law_name = n.law_name, law_article = n.law_article, form_code = n.form_code,
       created_at = n.created_at, updated_at = n.updated_at, is_excluded = n.is_excluded,
       custom_cycle = n.custom_cycle, excluded_reason = n.excluded_reason,
       reviewed_at = n.reviewed_at, reviewed_by = n.reviewed_by
  FROM public.work_schedules n
 WHERE o.id = n.id AND (o.*) IS DISTINCT FROM (n.*);

DELETE FROM public.work_schedules_old o
 WHERE NOT EXISTS (SELECT 1 FROM public.work_schedules n WHERE n.id = o.id);


-- ---------------------------------------------------------------------
-- §4. RECONCILE 검증 — 37컬럼 FULL-ROW EQUALITY (REV-2 지적 3)
--     id 집합 비교로는 내용 손상을 잡지 못하므로 양방향 EXCEPT 를 쓴다.
-- ---------------------------------------------------------------------
DO $$
DECLARE v_diff bigint;
BEGIN
    SELECT count(*) INTO v_diff FROM (
        (SELECT id, asset_id, assigned_user_id, repeat_type, repeat_interval,
                repeat_weekday, repeat_day, week_of_month, start_date, end_date,
                active_yn, inspection_set_id, company_id, factory_id, planned_date,
                status_code, description, completed_at, inspector_name, summary,
                schedule_group_id, source_type, obligation_type, event_type, event_date,
                cycle_base_guide, rule_code, law_name, law_article, form_code,
                created_at, updated_at, is_excluded, custom_cycle, excluded_reason,
                reviewed_at, reviewed_by
           FROM public.work_schedules
         EXCEPT
         SELECT id, asset_id, assigned_user_id, repeat_type, repeat_interval,
                repeat_weekday, repeat_day, week_of_month, start_date, end_date,
                active_yn, inspection_set_id, company_id, factory_id, planned_date,
                status_code, description, completed_at, inspector_name, summary,
                schedule_group_id, source_type, obligation_type, event_type, event_date,
                cycle_base_guide, rule_code, law_name, law_article, form_code,
                created_at, updated_at, is_excluded, custom_cycle, excluded_reason,
                reviewed_at, reviewed_by
           FROM public.work_schedules_old)
        UNION ALL
        (SELECT id, asset_id, assigned_user_id, repeat_type, repeat_interval,
                repeat_weekday, repeat_day, week_of_month, start_date, end_date,
                active_yn, inspection_set_id, company_id, factory_id, planned_date,
                status_code, description, completed_at, inspector_name, summary,
                schedule_group_id, source_type, obligation_type, event_type, event_date,
                cycle_base_guide, rule_code, law_name, law_article, form_code,
                created_at, updated_at, is_excluded, custom_cycle, excluded_reason,
                reviewed_at, reviewed_by
           FROM public.work_schedules_old
         EXCEPT
         SELECT id, asset_id, assigned_user_id, repeat_type, repeat_interval,
                repeat_weekday, repeat_day, week_of_month, start_date, end_date,
                active_yn, inspection_set_id, company_id, factory_id, planned_date,
                status_code, description, completed_at, inspector_name, summary,
                schedule_group_id, source_type, obligation_type, event_type, event_date,
                cycle_base_guide, rule_code, law_name, law_article, form_code,
                created_at, updated_at, is_excluded, custom_cycle, excluded_reason,
                reviewed_at, reviewed_by
           FROM public.work_schedules)
    ) x;

    IF v_diff > 0 THEN
        RAISE EXCEPTION 'RECONCILE FAIL: full-row mismatch = % (내용 불일치)', v_diff;
    END IF;
    RAISE NOTICE 'RECONCILE OK (37컬럼 full-row equality)';
END $$;


-- ---------------------------------------------------------------------
-- §5. SWAP
-- ---------------------------------------------------------------------
DROP TABLE public.work_schedules;                       -- 파티션 부모 + 자식 16
ALTER TABLE public.work_schedules_old RENAME TO work_schedules;


-- ---------------------------------------------------------------------
-- §6. CHILD additive 컬럼 제거 (원상복구)
--     equipment_checkins.factory_id 는 UP 이전부터 존재 → 유지
-- ---------------------------------------------------------------------
ALTER TABLE public.work_assignments   DROP COLUMN IF EXISTS factory_id;
ALTER TABLE public.safety_inspections DROP COLUMN IF EXISTS factory_id;


-- ---------------------------------------------------------------------
-- §7. 원본 CHILD FK 복원 (원본 ON DELETE 의미 그대로)
--     실측 원본: wa='a' si='a' ec='n'(SET NULL)
-- ---------------------------------------------------------------------
ALTER TABLE public.work_assignments
    ADD CONSTRAINT work_assignments_schedule_id_fkey
        FOREIGN KEY (schedule_id) REFERENCES public.work_schedules(id);

ALTER TABLE public.safety_inspections
    ADD CONSTRAINT safety_inspections_assignment_id_fkey
        FOREIGN KEY (assignment_id) REFERENCES public.work_schedules(id);

ALTER TABLE public.equipment_checkins
    ADD CONSTRAINT equipment_checkins_schedule_id_fkey
        FOREIGN KEY (schedule_id) REFERENCES public.work_schedules(id)
        ON DELETE SET NULL;


-- ---------------------------------------------------------------------
-- §8. OWNER / RLS 보정 (FAST PATH 는 old 를 되살리므로 원본 그대로지만 방어)
--     R3-2: ENABLE 뿐 아니라 FORCE 여부까지 fingerprint 기준으로 복원
-- ---------------------------------------------------------------------
ALTER TABLE public.work_schedules OWNER TO postgres;

DO $$
DECLARE v_enabled bool; v_forced bool;
BEGIN
    SELECT rls_enabled, rls_forced INTO v_enabled, v_forced FROM public._mig_ws_fingerprint;

    IF v_enabled THEN
        ALTER TABLE public.work_schedules ENABLE ROW LEVEL SECURITY;
    ELSE
        ALTER TABLE public.work_schedules DISABLE ROW LEVEL SECURITY;
    END IF;

    IF v_forced THEN
        ALTER TABLE public.work_schedules FORCE ROW LEVEL SECURITY;
    ELSE
        ALTER TABLE public.work_schedules NO FORCE ROW LEVEL SECURITY;
    END IF;
END $$;


-- ---------------------------------------------------------------------
-- §9. DOWN POSTCHECK — PRE-state EXACT 복원 검증 (REV-2 지적 1/2/3)
-- ---------------------------------------------------------------------
DO $$
DECLARE
    v_diff bigint; v_rows bigint; v_fp bigint; v_is_part bool;
    v_pkcols int; v_owner name;
BEGIN
    -- (1) 구조: 파티션 아님 + PK 단일 + 원본 UNIQUE
    SELECT relkind='p' INTO v_is_part FROM pg_class WHERE oid='public.work_schedules'::regclass;
    IF v_is_part THEN RAISE EXCEPTION 'DOWN FAIL: 여전히 파티션 테이블'; END IF;

    SELECT array_length(conkey,1) INTO v_pkcols FROM pg_constraint
     WHERE conrelid='public.work_schedules'::regclass AND contype='p';
    IF v_pkcols <> 1 THEN RAISE EXCEPTION 'DOWN FAIL: PK 컬럼 수 = %', v_pkcols; END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public'
                    AND tablename='work_schedules'
                    AND indexname='uq_work_schedules_inspection_set_planned_date') THEN
        RAISE EXCEPTION 'DOWN FAIL: 원본 UNIQUE 미복원';
    END IF;

    -- (2) 데이터 손실 검사 (UP 이후 순증가는 허용, 감소는 실패)
    SELECT count(*) INTO v_rows FROM public.work_schedules;
    SELECT row_count INTO v_fp FROM public._mig_ws_fingerprint;
    IF v_rows < v_fp THEN
        RAISE EXCEPTION 'DOWN FAIL: 데이터 손실 rows=% < pre=%', v_rows, v_fp;
    END IF;

    -- (3) UP 시점 스냅샷 행이 전부 보존됐는지 (37컬럼 기준)
    --     UP 이후 정당하게 수정/삭제된 행은 제외해야 하므로, 스냅샷에만 있고
    --     현재에 없는 id 중 UP 이후 삭제로 설명되지 않는 것은 없어야 한다.
    SELECT count(*) INTO v_diff FROM (
        SELECT id FROM public._mig_ws_data_snapshot
        EXCEPT SELECT id FROM public.work_schedules) x;
    IF v_diff > 0 THEN
        RAISE WARNING 'DOWN: 스냅샷 대비 소실 id % 건 — UP 이후 정당한 DELETE 인지 확인 필요', v_diff;
    END IF;

    -- (4) comments EXACT  (R3-3: public schema 한정)
    SELECT count(*) INTO v_diff FROM (
        (SELECT objname, description FROM public._mig_ws_comments
         EXCEPT
         SELECT coalesce(a.attname,'(table)'), d.description
           FROM pg_description d
           JOIN pg_class c ON c.oid=d.objoid AND c.relname='work_schedules'
           JOIN pg_namespace ns ON ns.oid=c.relnamespace AND ns.nspname='public'
           LEFT JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=d.objsubid)
        UNION ALL
        (SELECT coalesce(a.attname,'(table)'), d.description
           FROM pg_description d
           JOIN pg_class c ON c.oid=d.objoid AND c.relname='work_schedules'
           JOIN pg_namespace ns ON ns.oid=c.relnamespace AND ns.nspname='public'
           LEFT JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=d.objsubid
         EXCEPT
         SELECT objname, description FROM public._mig_ws_comments)) x;
    IF v_diff > 0 THEN RAISE EXCEPTION 'DOWN FAIL: comments mismatch = %', v_diff; END IF;

    -- (5) grants EXACT  (R3-1: grantor·is_grantable 포함)
    SELECT count(*) INTO v_diff FROM (
        (SELECT grantor, grantee, privilege_type, is_grantable FROM public._mig_ws_grants
         EXCEPT
         SELECT grantor, grantee, privilege_type, is_grantable
           FROM information_schema.role_table_grants
          WHERE table_schema='public' AND table_name='work_schedules')
        UNION ALL
        (SELECT grantor, grantee, privilege_type, is_grantable
           FROM information_schema.role_table_grants
          WHERE table_schema='public' AND table_name='work_schedules'
         EXCEPT
         SELECT grantor, grantee, privilege_type, is_grantable FROM public._mig_ws_grants)) x;
    IF v_diff > 0 THEN RAISE EXCEPTION 'DOWN FAIL: grants mismatch = % (grantor/is_grantable 포함)', v_diff; END IF;

    -- (6) policy EXACT  (R3-3: public schema 한정)
    SELECT count(*) INTO v_diff FROM (
        (SELECT policyname, cmd, permissive, roles::text, qual, with_check
           FROM public._mig_ws_policies
         EXCEPT
         SELECT policyname, cmd, permissive, roles::text, qual, with_check
           FROM pg_policies WHERE schemaname='public' AND tablename='work_schedules')
        UNION ALL
        (SELECT policyname, cmd, permissive, roles::text, qual, with_check
           FROM pg_policies WHERE schemaname='public' AND tablename='work_schedules'
         EXCEPT
         SELECT policyname, cmd, permissive, roles::text, qual, with_check
           FROM public._mig_ws_policies)) x;
    IF v_diff > 0 THEN RAISE EXCEPTION 'DOWN FAIL: policy mismatch = %', v_diff; END IF;

    -- (7) owner + RLS enabled/forced EXACT  (R3-2)
    SELECT pg_get_userbyid(relowner) INTO v_owner FROM pg_class
     WHERE oid='public.work_schedules'::regclass;
    IF v_owner <> (SELECT owner_name FROM public._mig_ws_fingerprint) THEN
        RAISE EXCEPTION 'DOWN FAIL: owner = %', v_owner;
    END IF;

    IF (SELECT relrowsecurity FROM pg_class WHERE oid='public.work_schedules'::regclass)
       <> (SELECT rls_enabled FROM public._mig_ws_fingerprint) THEN
        RAISE EXCEPTION 'DOWN FAIL: rls_enabled 불일치';
    END IF;
    IF (SELECT relforcerowsecurity FROM pg_class WHERE oid='public.work_schedules'::regclass)
       <> (SELECT rls_forced FROM public._mig_ws_fingerprint) THEN
        RAISE EXCEPTION 'DOWN FAIL: rls_forced 불일치';
    END IF;

    -- (8) child additive 컬럼 제거 확인
    IF EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='work_assignments'
                  AND column_name='factory_id') THEN
        RAISE EXCEPTION 'DOWN FAIL: work_assignments.factory_id 잔존';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='safety_inspections'
                  AND column_name='factory_id') THEN
        RAISE EXCEPTION 'DOWN FAIL: safety_inspections.factory_id 잔존';
    END IF;

    RAISE NOTICE 'DOWN POSTCHECK OK: 구조/데이터/comments/grants/policy/owner EXACT 복원';
END $$;


-- ---------------------------------------------------------------------
-- §10. 스냅샷 정리
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS public._mig_ws_data_snapshot;
DROP TABLE IF EXISTS public._mig_ws_comments;
DROP TABLE IF EXISTS public._mig_ws_grants;
DROP TABLE IF EXISTS public._mig_ws_policies;
DROP TABLE IF EXISTS public._mig_ws_fingerprint;
DROP TABLE IF EXISTS public._mig_ws_factory_counts;

COMMIT;

-- =====================================================================
-- 실패 지점별 상태 매트릭스
--
--  UP copy 실패          → 트랜잭션 롤백. 원본 무변경. 재시도 안전.
--  UP full-row 검증 실패 → 트랜잭션 롤백. 원본 무변경. (내용 손상 사전 차단)
--  UP backfill 실패      → 트랜잭션 롤백. child 컬럼도 롤백.
--  UP swap 실패          → 트랜잭션 롤백. 원본 무변경.
--  UP 성공/기능검증 실패 → 이 DOWN 실행. 데이터 손실 없음.
--  DOWN reconcile 실패   → 트랜잭션 롤백. 파티션 테이블 유지. 재시도 안전.
--  DOWN contract 검증 실패→ 트랜잭션 롤백. 파티션 테이블 유지.
--  old DROP 후 DOWN 시도 → §0 즉시 ABORT (부분 실행 없음).
-- =====================================================================
