-- =====================================================================
-- WP-PARTITION-02B-R1 : work_schedules 파티션 전환 원상복구
-- DOWN MIGRATION  (CURRENT-STATE REBASE of 20260822 REV-3 — NOT APPLIED)
--
--   REBASE BASE API HEAD = 6874bb85f5a9519d0f3c052f31492873a1a388bd (04E deployed)
--
--   [OLD PACKAGE 대비 REBASE 변경점 — ★가장 중요]
--   REBASE-1 (§6): OLD DOWN §6 은 rollback 시 work_assignments.factory_id / safety_inspections.factory_id 를
--                  DROP COLUMN 했다. 이 두 컬럼은 04C/04D 의 독립 LIVE 자산이므로 절대 DROP 금지.
--                  → 새 DOWN 은 이 컬럼들을 PRESERVE 한다. HASH rollback ≠ 04C/04D rollback.
--   REBASE-2 (§9): OLD DOWN POSTCHECK §9-(8) 은 factory_id 가 "잔존하면 FAIL" 이었다(제거를 성공조건으로 강제).
--                  → 반전: factory_id 가 "존재하고 값 보존" 을 성공조건으로 강제.
--   REBASE-3     : rollback target = 2026-08-22 상태가 아니라 04C/04D/04E 완료 후의 현재(HASH 실행 직전) 상태.
--                  child 단일 FK 복원 + pair CHECK 제거 + companion 컬럼/값 보존.
--                  ec 단일 FK 는 ON DELETE SET NULL 로 복원(원본 동작).
--
--   [REV-2 CRITICAL 추가]
--   CRITICAL-1 (§5): partitioned current DROP 전 dashboard_stats DROP → old rename → restored 에 재결합 + §9-(10) 검증.
--   CRITICAL-2 (§5): old→canonical 후 _mig_ws_grants 스냅샷으로 PRE grants EXACT 재생성 + §9-(11) 검증.
--
--   [FAST-PATH ONLY 계약] work_schedules_old 존재 시에만 실행. 없으면 §0 즉시 ABORT.
--   [ROLLBACK WINDOW] old 존재 기간 = 기능 검증 전용. 대량 write 비권장.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- §0. FAST-PATH 전제 강제
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF to_regclass('public.work_schedules_old') IS NULL THEN
        RAISE EXCEPTION
            'DOWN ABORT: work_schedules_old 없음. FAST PATH 전용. old 를 DROP 했다면 백업 복원 별도 절차 필요.';
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
-- §2. CHILD 복합 FK / pair CHECK 제거 (HASH 가 새로 만든 것만)
-- ---------------------------------------------------------------------
ALTER TABLE public.work_assignments   DROP CONSTRAINT IF EXISTS work_assignments_schedule_fkey;
ALTER TABLE public.safety_inspections DROP CONSTRAINT IF EXISTS safety_inspections_schedule_fkey;
ALTER TABLE public.equipment_checkins DROP CONSTRAINT IF EXISTS equipment_checkins_schedule_fkey;
ALTER TABLE public.work_assignments   DROP CONSTRAINT IF EXISTS chk_wa_schedule_factory_pair;
ALTER TABLE public.safety_inspections DROP CONSTRAINT IF EXISTS chk_si_schedule_factory_pair;


-- ---------------------------------------------------------------------
-- §3. FULL RECONCILIATION (new→old : INSERT/UPDATE/DELETE)
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
-- §4. RECONCILE 검증 — 37컬럼 FULL-ROW EQUALITY
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
    IF v_diff > 0 THEN RAISE EXCEPTION 'RECONCILE FAIL: full-row mismatch = %', v_diff; END IF;
    RAISE NOTICE 'RECONCILE OK (37컬럼 full-row equality)';
END $$;


-- ---------------------------------------------------------------------
-- §5. SWAP  (+ REV-2 CRITICAL-1: matview 를 partitioned current 에서 분리 후 old 에 재결합)
-- ---------------------------------------------------------------------
-- partitioned current(work_schedules) 를 DROP 하려면 그에 결합된 dashboard_stats 를 먼저 DROP 해야 한다.
DROP MATERIALIZED VIEW IF EXISTS public.dashboard_stats;

DROP TABLE public.work_schedules;                       -- 파티션 부모 + 자식 16
ALTER TABLE public.work_schedules_old RENAME TO work_schedules;

-- [REV-2 CRITICAL-2] old→canonical 복원 후 PRE grants 정확 재생성.
--   UP 에서 old 의 anon/authenticated/service_role 권한을 회수했으므로, 복원 시 _mig_ws_grants 스냅샷으로 원복.
--   (old 가 grants 를 그대로 들고 있다는 기존 가정은 anchor lockdown 이후 더 이상 성립하지 않음.)
REVOKE ALL PRIVILEGES ON TABLE public.work_schedules FROM PUBLIC;
REVOKE ALL PRIVILEGES ON TABLE public.work_schedules FROM anon, authenticated, service_role;
DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT DISTINCT grantee, privilege_type, is_grantable FROM public._mig_ws_grants LOOP
        IF r.is_grantable = 'YES' THEN
            EXECUTE format('GRANT %s ON public.work_schedules TO %I WITH GRANT OPTION', r.privilege_type, r.grantee);
        ELSE
            EXECUTE format('GRANT %s ON public.work_schedules TO %I', r.privilege_type, r.grantee);
        END IF;
    END LOOP;
END $$;

-- [REV-2 CRITICAL-1] dashboard_stats 를 restored regular work_schedules 에 재결합 (스냅샷 definition/owner/index/comment/grants).
DO $$
DECLARE
    v_def text; v_owner name; v_populated bool; v_comment text; r record;
BEGIN
    SELECT definition, owner_name, populated, comment_text
      INTO v_def, v_owner, v_populated, v_comment FROM public._mig_ws_matview LIMIT 1;
    EXECUTE format('CREATE MATERIALIZED VIEW public.dashboard_stats AS %s WITH %s DATA',
                   v_def, CASE WHEN v_populated THEN '' ELSE 'NO' END);
    EXECUTE format('ALTER MATERIALIZED VIEW public.dashboard_stats OWNER TO %I', v_owner);
    FOR r IN SELECT indexdef FROM public._mig_ws_matview_idx LOOP EXECUTE r.indexdef; END LOOP;
    IF v_comment IS NOT NULL THEN
        EXECUTE format('COMMENT ON MATERIALIZED VIEW public.dashboard_stats IS %L', v_comment);
    END IF;
    FOR r IN SELECT grantee, privilege_type, is_grantable FROM public._mig_ws_matview_grants LOOP
        IF r.is_grantable = 'YES' THEN
            EXECUTE format('GRANT %s ON public.dashboard_stats TO %I WITH GRANT OPTION', r.privilege_type, r.grantee);
        ELSE
            EXECUTE format('GRANT %s ON public.dashboard_stats TO %I', r.privilege_type, r.grantee);
        END IF;
    END LOOP;
END $$;


-- ---------------------------------------------------------------------
-- §6. [REBASE ★] CHILD companion factory_id 는 04C/04D 자산 → PRESERVE (DROP 금지)
--   OLD DOWN §6 의 "ALTER TABLE ... DROP COLUMN factory_id" (wa/si) 는 완전히 제거됨.
--   HASH rollback 은 04C/04D rollback 이 아니다. companion 컬럼과 값 전부 유지한다.
--   (아무 것도 하지 않는 것이 정답 — 컬럼 보존)
-- ---------------------------------------------------------------------


-- ---------------------------------------------------------------------
-- §7. 원본 CHILD 단일 FK 복원 (HASH 실행 직전 상태 = 04C/04D/04E 완료 상태)
--   실측 원본 이름/동작: wa=work_assignments_schedule_id_fkey (ON DELETE 기본 'a')
--                        si=safety_inspections_assignment_id_fkey (기본 'a')
--                        ec=equipment_checkins_schedule_id_fkey ON DELETE SET NULL
--   ※ 단일 FK 는 schedule_id/assignment_id 만 참조 (factory_id 는 참조 안 함) → companion 컬럼 그대로 둔다.
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
-- §8. OWNER / RLS 보정
-- ---------------------------------------------------------------------
ALTER TABLE public.work_schedules OWNER TO postgres;

DO $$
DECLARE v_enabled bool; v_forced bool;
BEGIN
    SELECT rls_enabled, rls_forced INTO v_enabled, v_forced FROM public._mig_ws_fingerprint;
    IF v_enabled THEN ALTER TABLE public.work_schedules ENABLE ROW LEVEL SECURITY;
    ELSE ALTER TABLE public.work_schedules DISABLE ROW LEVEL SECURITY; END IF;
    IF v_forced THEN ALTER TABLE public.work_schedules FORCE ROW LEVEL SECURITY;
    ELSE ALTER TABLE public.work_schedules NO FORCE ROW LEVEL SECURITY; END IF;
END $$;


-- ---------------------------------------------------------------------
-- §9. DOWN POSTCHECK — HASH 실행 직전(04C/04D/04E 완료) 상태 EXACT 복원 검증
--   [REBASE ★] child factory_id = "존재+보존" 을 성공조건으로 강제 (OLD 의 "제거" 조건 반전)
-- ---------------------------------------------------------------------
DO $$
DECLARE
    v_diff bigint; v_rows bigint; v_fp bigint; v_is_part bool;
    v_pkcols int; v_owner name;
    v_wa_fac bool; v_si_fac bool; v_wa_null bigint; v_si_null bigint;
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
    IF v_rows < v_fp THEN RAISE EXCEPTION 'DOWN FAIL: 데이터 손실 rows=% < pre=%', v_rows, v_fp; END IF;

    -- (3) 스냅샷 id 보존 (UP 이후 정당 DELETE 는 WARNING)
    SELECT count(*) INTO v_diff FROM (
        SELECT id FROM public._mig_ws_data_snapshot EXCEPT SELECT id FROM public.work_schedules) x;
    IF v_diff > 0 THEN
        RAISE WARNING 'DOWN: 스냅샷 대비 소실 id % 건 — UP 이후 정당한 DELETE 인지 확인 필요', v_diff;
    END IF;

    -- (4) comments EXACT
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

    -- (5) grants EXACT
    SELECT count(*) INTO v_diff FROM (
        (SELECT grantor, grantee, privilege_type, is_grantable FROM public._mig_ws_grants
         EXCEPT
         SELECT grantor, grantee, privilege_type, is_grantable
           FROM information_schema.role_table_grants WHERE table_schema='public' AND table_name='work_schedules')
        UNION ALL
        (SELECT grantor, grantee, privilege_type, is_grantable
           FROM information_schema.role_table_grants WHERE table_schema='public' AND table_name='work_schedules'
         EXCEPT
         SELECT grantor, grantee, privilege_type, is_grantable FROM public._mig_ws_grants)) x;
    IF v_diff > 0 THEN RAISE EXCEPTION 'DOWN FAIL: grants mismatch = %', v_diff; END IF;

    -- (6) policy EXACT
    SELECT count(*) INTO v_diff FROM (
        (SELECT policyname, cmd, permissive, roles::text, qual, with_check FROM public._mig_ws_policies
         EXCEPT
         SELECT policyname, cmd, permissive, roles::text, qual, with_check
           FROM pg_policies WHERE schemaname='public' AND tablename='work_schedules')
        UNION ALL
        (SELECT policyname, cmd, permissive, roles::text, qual, with_check
           FROM pg_policies WHERE schemaname='public' AND tablename='work_schedules'
         EXCEPT
         SELECT policyname, cmd, permissive, roles::text, qual, with_check FROM public._mig_ws_policies)) x;
    IF v_diff > 0 THEN RAISE EXCEPTION 'DOWN FAIL: policy mismatch = %', v_diff; END IF;

    -- (7) owner + RLS enabled/forced EXACT
    SELECT pg_get_userbyid(relowner) INTO v_owner FROM pg_class WHERE oid='public.work_schedules'::regclass;
    IF v_owner <> (SELECT owner_name FROM public._mig_ws_fingerprint) THEN RAISE EXCEPTION 'DOWN FAIL: owner = %', v_owner; END IF;
    IF (SELECT relrowsecurity FROM pg_class WHERE oid='public.work_schedules'::regclass)
       <> (SELECT rls_enabled FROM public._mig_ws_fingerprint) THEN RAISE EXCEPTION 'DOWN FAIL: rls_enabled 불일치'; END IF;
    IF (SELECT relforcerowsecurity FROM pg_class WHERE oid='public.work_schedules'::regclass)
       <> (SELECT rls_forced FROM public._mig_ws_fingerprint) THEN RAISE EXCEPTION 'DOWN FAIL: rls_forced 불일치'; END IF;

    -- (8) [REBASE ★ 반전] child companion factory_id = 존재 + 값 보존 (제거가 아니라 보존이 성공조건)
    SELECT EXISTS(SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='work_assignments' AND column_name='factory_id') INTO v_wa_fac;
    SELECT EXISTS(SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='safety_inspections' AND column_name='factory_id') INTO v_si_fac;
    IF NOT v_wa_fac THEN RAISE EXCEPTION 'DOWN FAIL: work_assignments.factory_id 소실(04C 자산이 DROP됨 — 금지)'; END IF;
    IF NOT v_si_fac THEN RAISE EXCEPTION 'DOWN FAIL: safety_inspections.factory_id 소실(04D 자산이 DROP됨 — 금지)'; END IF;

    -- companion 정합도 HASH 직전과 동일해야 함 (linked null 0). legacy si standalone 은 허용.
    SELECT count(*) INTO v_wa_null FROM public.work_assignments WHERE schedule_id IS NOT NULL AND factory_id IS NULL;
    SELECT count(*) INTO v_si_null FROM public.safety_inspections WHERE assignment_id IS NOT NULL AND factory_id IS NULL;
    IF v_wa_null > 0 THEN RAISE EXCEPTION 'DOWN FAIL: wa linked factory NULL = % (companion 손상)', v_wa_null; END IF;
    IF v_si_null > 0 THEN RAISE EXCEPTION 'DOWN FAIL: si linked factory NULL = % (companion 손상)', v_si_null; END IF;

    -- (9) child 단일 FK 복원 확인 (composite FK / pair CHECK 부재)
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='work_assignments_schedule_id_fkey') THEN
        RAISE EXCEPTION 'DOWN FAIL: wa 단일 FK 미복원'; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='safety_inspections_assignment_id_fkey') THEN
        RAISE EXCEPTION 'DOWN FAIL: si 단일 FK 미복원'; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='equipment_checkins_schedule_id_fkey') THEN
        RAISE EXCEPTION 'DOWN FAIL: ec 단일 FK 미복원'; END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname IN
                ('work_assignments_schedule_fkey','safety_inspections_schedule_fkey','equipment_checkins_schedule_fkey',
                 'chk_wa_schedule_factory_pair','chk_si_schedule_factory_pair')) THEN
        RAISE EXCEPTION 'DOWN FAIL: HASH composite FK/pair CHECK 잔존'; END IF;

    -- (10) [REV-2 CRITICAL-1] dashboard_stats 가 restored regular work_schedules 에 재결합 + populated
    IF to_regclass('public.dashboard_stats') IS NULL THEN
        RAISE EXCEPTION 'DOWN FAIL: dashboard_stats 미복원'; END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_depend d
          JOIN pg_rewrite rw ON rw.oid = d.objid
          JOIN pg_class mv ON mv.oid = rw.ev_class AND mv.relname='dashboard_stats' AND mv.relkind='m'
         WHERE d.refobjid = 'public.work_schedules'::regclass) THEN
        RAISE EXCEPTION 'DOWN FAIL: dashboard_stats 가 restored work_schedules 에 미결합'; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_matviews WHERE schemaname='public' AND matviewname='dashboard_stats'
                    AND ispopulated = (SELECT populated FROM public._mig_ws_matview LIMIT 1)) THEN
        RAISE EXCEPTION 'DOWN FAIL: dashboard_stats populated 상태 불일치'; END IF;

    -- (11) [REV-2 CRITICAL-2] canonical grants = _mig_ws_grants 스냅샷 EXACT 복원
    SELECT count(*) INTO v_diff FROM (
        (SELECT grantee, privilege_type, is_grantable FROM public._mig_ws_grants
         EXCEPT
         SELECT grantee, privilege_type, is_grantable FROM information_schema.role_table_grants
          WHERE table_schema='public' AND table_name='work_schedules')
        UNION ALL
        (SELECT grantee, privilege_type, is_grantable FROM information_schema.role_table_grants
          WHERE table_schema='public' AND table_name='work_schedules'
         EXCEPT
         SELECT grantee, privilege_type, is_grantable FROM public._mig_ws_grants)) x;
    IF v_diff > 0 THEN RAISE EXCEPTION 'DOWN FAIL: canonical grants 스냅샷 불일치 = %', v_diff; END IF;

    RAISE NOTICE 'DOWN POSTCHECK OK: 구조/데이터/메타 EXACT + 04C/04D companion 보존 + 단일 FK 복원 + matview restored + grants exact';
END $$;


-- ---------------------------------------------------------------------
-- §10. 스냅샷 정리
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS public._mig_ws_data_snapshot;
DROP TABLE IF EXISTS public._mig_ws_comments;
DROP TABLE IF EXISTS public._mig_ws_grants;
DROP TABLE IF EXISTS public._mig_ws_policies;
DROP TABLE IF EXISTS public._mig_ws_fingerprint;
DROP TABLE IF EXISTS public._mig_ws_matview;
DROP TABLE IF EXISTS public._mig_ws_matview_idx;
DROP TABLE IF EXISTS public._mig_ws_matview_grants;

COMMIT;

-- =====================================================================
-- 실패 지점별 상태 매트릭스
--  UP copy/full-row/backfill/swap 실패 → 트랜잭션 롤백. 원본 무변경.
--  UP 성공/기능검증 실패 → 이 DOWN 실행. 데이터 손실 없음. 04C/04D companion 보존.
--  DOWN reconcile/contract 실패 → 트랜잭션 롤백. 파티션 테이블 유지. 재시도 안전.
--  old DROP 후 DOWN 시도 → §0 즉시 ABORT.
--  ★ HASH rollback 은 04C/04D rollback 이 아니다: wa/si.factory_id 는 항상 보존.
-- =====================================================================
