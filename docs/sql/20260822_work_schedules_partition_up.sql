-- =====================================================================
-- WP-PARTITION-02A (APPROVED ARTIFACT) : work_schedules → PARTITION BY HASH (factory_id)
-- UP MIGRATION  (APPROVED DESIGN ARTIFACT — NOT APPLIED TO ANY DB)
--
--   PostgreSQL 17.6 / Supabase project vwlahtguyggrhvslabax
--   REV-3 (2026-08-22) — GPT REV-2 검증 micro revision 3건 반영
--
--   [REV-3 변경점 — 다른 설계 변경 없음]
--   R3-1. grants: grantor/grantee/privilege_type/is_grantable 로 snapshot 확장.
--         is_grantable='YES' 는 WITH GRANT OPTION 으로 재생성.
--         [실측] postgres grantee 7권한이 전부 is_grantable=YES →
--                REV-2 의 단순 GRANT 는 재위임 권한을 잃었다. 실제 결함이었음.
--   R3-2. RLS: relforcerowsecurity 를 fingerprint 기준으로 복원 + POSTCHECK 비교.
--   R3-3. catalog 조회 전부 public schema 로 한정 (동명 테이블 혼입 차단).
--
--   [REV-2 유지 사항]
--   owner exact / comments·policies exact / 37컬럼 full-row equality /
--   MATCH FULL + pair CHECK / ON DELETE SET NULL (schedule_id) /
--   ACCESS EXCLUSIVE write freeze / cutover ordering / index 확정
--
--   [PRE-STATE 실측 2026-08-22]
--     owner=postgres / CHECK 0 / trigger 0 / view 0
--     comments 26 (table 1 + column 25)
--     grants: anon·authenticated·postgres·service_role × 7권한
--     RLS enabled=true force=false, policy 6 (전부 qual=true)
--     ON DELETE: wa='a' si='a' ec='n'(SET NULL)
--
--   ⚠ 실행 전 GPT 재검증 + 운영자 승인 필요. DB 미적용 상태.
-- =====================================================================

-- ---------------------------------------------------------------------
-- §0-A. CUTOVER ORDERING 계약  (REV-2 — 지적 5, CRITICAL)
--
--   [코드 호환성 판정]
--   patch 대상 2건은 INSERT payload 에 factory_id 를 "추가"하는 변경이다.
--     · routers/work_schedules.py  _apply_one_update()  → work_assignments INSERT
--     · routers/worker_check.py    submit_check()       → safety_inspections INSERT
--   구 schema(=factory_id 컬럼 없음)에서 이 payload 를 보내면 컬럼 부재로 실패한다.
--   → 따라서 patched code 는 backward-compatible 이 아니다.
--   → "코드 선배포" 방식은 사용할 수 없다.
--
--   [확정 순서 — 반드시 이 순서로]
--     1. maintenance ON  (API/worker 트래픽 차단)
--     2. 활성 write 세션 0 확인:
--          SELECT count(*) FROM pg_stat_activity
--           WHERE state='active' AND query ILIKE '%work_schedules%';
--     3. 이 UP 스크립트 실행 (내부 ACCESS EXCLUSIVE LOCK 이 2차 방어)
--     4. patched code 배포
--     5. smoke test (§17 목록)
--     6. maintenance OFF
--
--   3과 4 사이에 구버전 코드가 write 하면 CHECK 제약으로 실패한다(조용한 우회 아님).
--   이 구간을 짧게 유지하는 것이 운영 계약이다.
-- ---------------------------------------------------------------------

BEGIN;

-- ---------------------------------------------------------------------
-- §0-B. WRITE FREEZE
-- ---------------------------------------------------------------------
LOCK TABLE public.work_schedules     IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.work_assignments   IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.safety_inspections IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.equipment_checkins IN ACCESS EXCLUSIVE MODE;


-- ---------------------------------------------------------------------
-- §1. HARD PRECHECKS
-- ---------------------------------------------------------------------
DO $$
DECLARE
    v_factory_null bigint; v_set_mismatch bigint; v_dup_unique bigint;
    v_wa_orphan bigint; v_si_orphan bigint; v_ec_mismatch bigint;
    v_checks bigint; v_triggers bigint; v_owner name;
BEGIN
    SELECT count(*) INTO v_factory_null FROM public.work_schedules WHERE factory_id IS NULL;

    SELECT count(*) INTO v_set_mismatch
      FROM public.work_schedules ws JOIN public.inspection_sets s ON s.id = ws.inspection_set_id
     WHERE ws.factory_id IS DISTINCT FROM s.factory_id;

    SELECT count(*) INTO v_dup_unique FROM (
        SELECT inspection_set_id, planned_date, factory_id FROM public.work_schedules
         WHERE inspection_set_id IS NOT NULL AND planned_date IS NOT NULL
         GROUP BY 1,2,3 HAVING count(*) > 1) d;

    SELECT count(*) INTO v_wa_orphan FROM public.work_assignments wa
     WHERE wa.schedule_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM public.work_schedules ws WHERE ws.id = wa.schedule_id);

    SELECT count(*) INTO v_si_orphan FROM public.safety_inspections si
     WHERE si.assignment_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM public.work_schedules ws WHERE ws.id = si.assignment_id);

    SELECT count(*) INTO v_ec_mismatch
      FROM public.equipment_checkins ec JOIN public.work_schedules ws ON ws.id = ec.schedule_id
     WHERE ec.factory_id IS DISTINCT FROM ws.factory_id;

    SELECT count(*) INTO v_checks   FROM pg_constraint
     WHERE conrelid='public.work_schedules'::regclass AND contype='c';
    SELECT count(*) INTO v_triggers FROM pg_trigger
     WHERE tgrelid='public.work_schedules'::regclass AND NOT tgisinternal;
    SELECT pg_get_userbyid(relowner) INTO v_owner FROM pg_class
     WHERE oid='public.work_schedules'::regclass;

    IF v_factory_null > 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: factory_id NULL = %', v_factory_null; END IF;
    IF v_set_mismatch > 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: set/factory mismatch = %', v_set_mismatch; END IF;
    IF v_dup_unique   > 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: dup unique candidate = %', v_dup_unique; END IF;
    IF v_wa_orphan    > 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: wa orphan = %', v_wa_orphan; END IF;
    IF v_si_orphan    > 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: si orphan = %', v_si_orphan; END IF;
    IF v_ec_mismatch  > 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: ec factory mismatch = %', v_ec_mismatch; END IF;
    IF v_checks      <> 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: CHECK 제약 % (설계 0)', v_checks; END IF;
    IF v_triggers    <> 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: trigger % (설계 0)', v_triggers; END IF;
    IF v_owner  <> 'postgres' THEN RAISE EXCEPTION 'PRECHECK FAIL: owner=% (설계 postgres)', v_owner; END IF;

    RAISE NOTICE 'PRECHECK OK';
END $$;


-- ---------------------------------------------------------------------
-- §2. PRE-STATE CONTRACT 캡처  (REV-2 — 지적 2)
--     개수가 아니라 "내용"을 저장해 DOWN 후 exact 비교에 사용한다.
-- ---------------------------------------------------------------------
CREATE TABLE public._mig_ws_fingerprint AS
SELECT
    (SELECT count(*)                   FROM public.work_schedules) AS row_count,
    (SELECT count(DISTINCT factory_id) FROM public.work_schedules) AS distinct_factory,
    (SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='public.work_schedules'::regclass) AS owner_name,
    (SELECT relrowsecurity FROM pg_class WHERE oid='public.work_schedules'::regclass) AS rls_enabled,
    (SELECT relforcerowsecurity FROM pg_class WHERE oid='public.work_schedules'::regclass) AS rls_forced,
    now() AS captured_at;

-- 데이터 원본 스냅샷 (37컬럼 full-row 비교용)
CREATE TABLE public._mig_ws_data_snapshot AS
SELECT * FROM public.work_schedules;

-- comments 내용 (R3-3: public schema 한정)
CREATE TABLE public._mig_ws_comments AS
SELECT coalesce(a.attname, '(table)') AS objname, d.description
  FROM pg_description d
  JOIN pg_class c ON c.oid = d.objoid AND c.relname='work_schedules'
  JOIN pg_namespace ns ON ns.oid = c.relnamespace AND ns.nspname='public'
  LEFT JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.objsubid;

-- grants 내용 (R3-1: grantor/is_grantable 포함 — 재위임 권한 보존)
CREATE TABLE public._mig_ws_grants AS
SELECT grantor, grantee, privilege_type, is_grantable
  FROM information_schema.role_table_grants
 WHERE table_schema='public' AND table_name='work_schedules';

-- policy 내용 (R3-3: public schema 한정)
CREATE TABLE public._mig_ws_policies AS
SELECT policyname, cmd, permissive, roles::text AS roles, qual, with_check
  FROM pg_policies WHERE schemaname='public' AND tablename='work_schedules';


-- ---------------------------------------------------------------------
-- §3. SHADOW PARTITIONED TABLE
--     factory_id NOT NULL 사유: HASH 파티션키 요건이 아니라
--     PRIMARY KEY (id, factory_id) 계약 때문이다.
-- ---------------------------------------------------------------------
CREATE TABLE public.work_schedules_new (
    id                 uuid        NOT NULL DEFAULT gen_random_uuid(),
    asset_id           uuid,
    assigned_user_id   uuid,
    repeat_type        text,
    repeat_interval    integer,
    repeat_weekday     text,
    repeat_day         integer,
    week_of_month      text,
    start_date         date,
    end_date           date,
    active_yn          boolean     DEFAULT true,
    inspection_set_id  uuid,
    company_id         uuid,
    factory_id         uuid        NOT NULL,
    planned_date       date,
    status_code        text,
    description        text,
    completed_at       date,
    inspector_name     text,
    summary            text,
    schedule_group_id  uuid,
    source_type        text        DEFAULT 'MANUAL'::text,
    obligation_type    text,
    event_type         text,
    event_date         date,
    cycle_base_guide   text,
    rule_code          text,
    law_name           text,
    law_article        text,
    form_code          text,
    created_at         timestamptz DEFAULT now(),
    updated_at         timestamptz DEFAULT now(),
    is_excluded        boolean     DEFAULT false,
    custom_cycle       text,
    excluded_reason    text,
    reviewed_at        timestamp,
    reviewed_by        uuid,
    CONSTRAINT work_schedules_new_pkey
        PRIMARY KEY (id, factory_id),
    CONSTRAINT uq_work_schedules_new_set_planned_factory
        UNIQUE (inspection_set_id, planned_date, factory_id)
) PARTITION BY HASH (factory_id);

-- §3-B. OWNER 복원 (REV-2 — 지적 1)
ALTER TABLE public.work_schedules_new OWNER TO postgres;


-- ---------------------------------------------------------------------
-- §4. HASH PARTITIONS (MODULUS 16) + owner
--     파티션 자식은 부모 owner 를 상속하지만 명시적으로 고정한다.
-- ---------------------------------------------------------------------
CREATE TABLE public.work_schedules_p00 PARTITION OF public.work_schedules_new FOR VALUES WITH (MODULUS 16, REMAINDER 0);
CREATE TABLE public.work_schedules_p01 PARTITION OF public.work_schedules_new FOR VALUES WITH (MODULUS 16, REMAINDER 1);
CREATE TABLE public.work_schedules_p02 PARTITION OF public.work_schedules_new FOR VALUES WITH (MODULUS 16, REMAINDER 2);
CREATE TABLE public.work_schedules_p03 PARTITION OF public.work_schedules_new FOR VALUES WITH (MODULUS 16, REMAINDER 3);
CREATE TABLE public.work_schedules_p04 PARTITION OF public.work_schedules_new FOR VALUES WITH (MODULUS 16, REMAINDER 4);
CREATE TABLE public.work_schedules_p05 PARTITION OF public.work_schedules_new FOR VALUES WITH (MODULUS 16, REMAINDER 5);
CREATE TABLE public.work_schedules_p06 PARTITION OF public.work_schedules_new FOR VALUES WITH (MODULUS 16, REMAINDER 6);
CREATE TABLE public.work_schedules_p07 PARTITION OF public.work_schedules_new FOR VALUES WITH (MODULUS 16, REMAINDER 7);
CREATE TABLE public.work_schedules_p08 PARTITION OF public.work_schedules_new FOR VALUES WITH (MODULUS 16, REMAINDER 8);
CREATE TABLE public.work_schedules_p09 PARTITION OF public.work_schedules_new FOR VALUES WITH (MODULUS 16, REMAINDER 9);
CREATE TABLE public.work_schedules_p10 PARTITION OF public.work_schedules_new FOR VALUES WITH (MODULUS 16, REMAINDER 10);
CREATE TABLE public.work_schedules_p11 PARTITION OF public.work_schedules_new FOR VALUES WITH (MODULUS 16, REMAINDER 11);
CREATE TABLE public.work_schedules_p12 PARTITION OF public.work_schedules_new FOR VALUES WITH (MODULUS 16, REMAINDER 12);
CREATE TABLE public.work_schedules_p13 PARTITION OF public.work_schedules_new FOR VALUES WITH (MODULUS 16, REMAINDER 13);
CREATE TABLE public.work_schedules_p14 PARTITION OF public.work_schedules_new FOR VALUES WITH (MODULUS 16, REMAINDER 14);
CREATE TABLE public.work_schedules_p15 PARTITION OF public.work_schedules_new FOR VALUES WITH (MODULUS 16, REMAINDER 15);

DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT c.relname FROM pg_inherits i
               JOIN pg_class c ON c.oid = i.inhrelid
              WHERE i.inhparent = 'public.work_schedules_new'::regclass
    LOOP
        EXECUTE format('ALTER TABLE public.%I OWNER TO postgres', r.relname);
    END LOOP;
END $$;


-- ---------------------------------------------------------------------
-- §5. COPY DATA — 37컬럼 전체 명시
-- ---------------------------------------------------------------------
INSERT INTO public.work_schedules_new (
    id, asset_id, assigned_user_id, repeat_type, repeat_interval,
    repeat_weekday, repeat_day, week_of_month, start_date, end_date,
    active_yn, inspection_set_id, company_id, factory_id, planned_date,
    status_code, description, completed_at, inspector_name, summary,
    schedule_group_id, source_type, obligation_type, event_type, event_date,
    cycle_base_guide, rule_code, law_name, law_article, form_code,
    created_at, updated_at, is_excluded, custom_cycle, excluded_reason,
    reviewed_at, reviewed_by)
SELECT
    id, asset_id, assigned_user_id, repeat_type, repeat_interval,
    repeat_weekday, repeat_day, week_of_month, start_date, end_date,
    active_yn, inspection_set_id, company_id, factory_id, planned_date,
    status_code, description, completed_at, inspector_name, summary,
    schedule_group_id, source_type, obligation_type, event_type, event_date,
    cycle_base_guide, rule_code, law_name, law_article, form_code,
    created_at, updated_at, is_excluded, custom_cycle, excluded_reason,
    reviewed_at, reviewed_by
FROM public.work_schedules;


-- ---------------------------------------------------------------------
-- §6. COPY VALIDATION — 37컬럼 FULL-ROW EQUALITY  (REV-2 — 지적 3/4)
--     id checksum 은 내용 손상을 못 잡으므로 폐기하고 양방향 EXCEPT 를 쓴다.
-- ---------------------------------------------------------------------
DO $$
DECLARE v_old bigint; v_new bigint; v_diff bigint;
BEGIN
    SELECT count(*) INTO v_old FROM public.work_schedules;
    SELECT count(*) INTO v_new FROM public.work_schedules_new;
    IF v_old <> v_new THEN
        RAISE EXCEPTION 'COPY FAIL: row count old=% new=%', v_old, v_new;
    END IF;

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
           FROM public.work_schedules_new)
        UNION ALL
        (SELECT id, asset_id, assigned_user_id, repeat_type, repeat_interval,
                repeat_weekday, repeat_day, week_of_month, start_date, end_date,
                active_yn, inspection_set_id, company_id, factory_id, planned_date,
                status_code, description, completed_at, inspector_name, summary,
                schedule_group_id, source_type, obligation_type, event_type, event_date,
                cycle_base_guide, rule_code, law_name, law_article, form_code,
                created_at, updated_at, is_excluded, custom_cycle, excluded_reason,
                reviewed_at, reviewed_by
           FROM public.work_schedules_new
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
        RAISE EXCEPTION 'COPY FAIL: full-row mismatch = % (37컬럼 내용 불일치)', v_diff;
    END IF;

    RAISE NOTICE 'COPY VALIDATED (full-row equality): % rows', v_new;
END $$;


-- ---------------------------------------------------------------------
-- §7. INDEXES  (REV-2 — 지적 6, 처리 확정)
--
--   event_type  = DROP   : 코드 predicate 부재(전수 검색 0건). 복원 SQL §19.
--   is_excluded = MERGE  : routers/work_schedules.py confirm_schedules() 가
--                          .eq("factory_id").eq("is_excluded") 로 함께 쓴다
--                          → (factory_id, is_excluded) 복합으로 흡수.
--   status_date = MERGE  : status_code + planned_date 조합은 항상 factory 스코프와
--                          함께 조회된다(GET /work-schedules)
--                          → (factory_id, status_code, planned_date) 로 흡수.
--   idx_ws_new_id 없음   : PK(id, factory_id) 의 leading id 로 대체.
-- ---------------------------------------------------------------------
CREATE INDEX idx_ws_new_factory_planned  ON public.work_schedules_new (factory_id, planned_date);
CREATE INDEX idx_ws_new_factory_status_p ON public.work_schedules_new (factory_id, status_code, planned_date);  -- status_date MERGE
CREATE INDEX idx_ws_new_factory_excluded ON public.work_schedules_new (factory_id, is_excluded);                -- is_excluded MERGE
CREATE INDEX idx_ws_new_factory_created  ON public.work_schedules_new (factory_id, created_at DESC);
CREATE INDEX idx_ws_new_company          ON public.work_schedules_new (company_id);
CREATE INDEX idx_ws_new_inspection_set   ON public.work_schedules_new (inspection_set_id);
CREATE INDEX idx_ws_new_source_type      ON public.work_schedules_new (source_type);
CREATE INDEX idx_ws_new_assigned_user    ON public.work_schedules_new (assigned_user_id);


-- ---------------------------------------------------------------------
-- §8. OUTBOUND FK
-- ---------------------------------------------------------------------
ALTER TABLE public.work_schedules_new
    ADD CONSTRAINT work_schedules_new_company_fkey FOREIGN KEY (company_id)        REFERENCES public.companies(id),
    ADD CONSTRAINT work_schedules_new_factory_fkey FOREIGN KEY (factory_id)        REFERENCES public.factories(id),
    ADD CONSTRAINT work_schedules_new_asset_fkey   FOREIGN KEY (asset_id)          REFERENCES public.equipment_assets(id),
    ADD CONSTRAINT work_schedules_new_set_fkey     FOREIGN KEY (inspection_set_id) REFERENCES public.inspection_sets(id),
    ADD CONSTRAINT work_schedules_new_user_fkey    FOREIGN KEY (assigned_user_id)  REFERENCES public.users(id),
    ADD CONSTRAINT work_schedules_new_group_fkey   FOREIGN KEY (schedule_group_id) REFERENCES public.work_schedule_groups(id);


-- ---------------------------------------------------------------------
-- §9. COMMENTS 복제 — 스냅샷에서 동적 재생성 (하드코딩 아님)
--     원본 문자열을 그대로 옮기므로 exact equality 가 보장된다.
-- ---------------------------------------------------------------------
DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT objname, description FROM public._mig_ws_comments LOOP
        IF r.objname = '(table)' THEN
            EXECUTE format('COMMENT ON TABLE public.work_schedules_new IS %L', r.description);
        ELSE
            EXECUTE format('COMMENT ON COLUMN public.work_schedules_new.%I IS %L', r.objname, r.description);
        END IF;
    END LOOP;
END $$;


-- ---------------------------------------------------------------------
-- §10. CHILD factory_id additive + backfill
--
--   [의미 계약 — REV-2 지적 6-b]
--   safety_inspections.factory_id / work_assignments.factory_id 는
--     · 해당 테이블의 canonical tenant key 가 아니다
--     · assignment_id / schedule_id 가 있을 때만 존재하는 FK companion 이다
--     · 업무 로직에서 tenant 필터로 사용 금지 (parent 를 경유해야 한다)
--   이 계약은 DOWN 에서 컬럼이 DROP 되는 근거이기도 하다.
-- ---------------------------------------------------------------------
ALTER TABLE public.work_assignments   ADD COLUMN IF NOT EXISTS factory_id uuid;
ALTER TABLE public.safety_inspections ADD COLUMN IF NOT EXISTS factory_id uuid;

COMMENT ON COLUMN public.work_assignments.factory_id IS
    'WP-PARTITION-02A: work_schedules 복합 FK companion. canonical tenant key 아님. 업무 필터 사용 금지.';
COMMENT ON COLUMN public.safety_inspections.factory_id IS
    'WP-PARTITION-02A: work_schedules 복합 FK companion. canonical tenant key 아님. 업무 필터 사용 금지.';

UPDATE public.work_assignments wa
   SET factory_id = ws.factory_id
  FROM public.work_schedules ws
 WHERE ws.id = wa.schedule_id AND wa.factory_id IS DISTINCT FROM ws.factory_id;

-- safety_inspections.assignment_id 는 컬럼명과 달리 work_schedules(id) 를 참조한다
-- (worker_check.py v1.4.1 확인. 명명 정리는 별건.)
UPDATE public.safety_inspections si
   SET factory_id = ws.factory_id
  FROM public.work_schedules ws
 WHERE ws.id = si.assignment_id AND si.factory_id IS DISTINCT FROM ws.factory_id;

DO $$
DECLARE v_wa bigint; v_si bigint;
BEGIN
    SELECT count(*) INTO v_wa FROM public.work_assignments
     WHERE schedule_id IS NOT NULL AND factory_id IS NULL;
    SELECT count(*) INTO v_si FROM public.safety_inspections
     WHERE assignment_id IS NOT NULL AND factory_id IS NULL;
    IF v_wa > 0 OR v_si > 0 THEN
        RAISE EXCEPTION 'BACKFILL FAIL: wa=% si=%', v_wa, v_si;
    END IF;
    RAISE NOTICE 'BACKFILL OK';
END $$;


-- ---------------------------------------------------------------------
-- §11. CHILD NULL 계약 (MATCH SIMPLE 우회 차단)
-- ---------------------------------------------------------------------
ALTER TABLE public.work_assignments
    ADD CONSTRAINT chk_wa_schedule_factory_pair
    CHECK ((schedule_id IS NULL) = (factory_id IS NULL));

ALTER TABLE public.safety_inspections
    ADD CONSTRAINT chk_si_schedule_factory_pair
    CHECK ((assignment_id IS NULL) = (factory_id IS NULL));


-- ---------------------------------------------------------------------
-- §12. CUTOVER + CHILD 복합 FK
-- ---------------------------------------------------------------------
ALTER TABLE public.work_assignments   DROP CONSTRAINT IF EXISTS work_assignments_schedule_id_fkey;
ALTER TABLE public.safety_inspections DROP CONSTRAINT IF EXISTS safety_inspections_assignment_id_fkey;
ALTER TABLE public.equipment_checkins DROP CONSTRAINT IF EXISTS equipment_checkins_schedule_id_fkey;

ALTER TABLE public.work_schedules     RENAME TO work_schedules_old;
ALTER TABLE public.work_schedules_new RENAME TO work_schedules;

ALTER TABLE public.work_assignments
    ADD CONSTRAINT work_assignments_schedule_fkey
        FOREIGN KEY (schedule_id, factory_id)
        REFERENCES public.work_schedules (id, factory_id) MATCH FULL;

ALTER TABLE public.safety_inspections
    ADD CONSTRAINT safety_inspections_schedule_fkey
        FOREIGN KEY (assignment_id, factory_id)
        REFERENCES public.work_schedules (id, factory_id) MATCH FULL;

-- 원본 ON DELETE SET NULL 보존. 업무 컬럼 factory_id 는 유지하고 schedule_id 만 비운다.
-- (컬럼 지정 SET NULL 은 PostgreSQL 15+; 현재 17.6)
ALTER TABLE public.equipment_checkins
    ADD CONSTRAINT equipment_checkins_schedule_fkey
        FOREIGN KEY (schedule_id, factory_id)
        REFERENCES public.work_schedules (id, factory_id)
        ON DELETE SET NULL (schedule_id);


-- ---------------------------------------------------------------------
-- §13. RLS / POLICY — 스냅샷에서 동적 재생성 (exact 보존)
--   R3-2: ENABLE 뿐 아니라 FORCE 여부까지 fingerprint 기준으로 복원한다.
--         (PRE-state 실측: enabled=true, forced=false)
--   ※ 원본 정책은 전부 qual=true 다. anon 전체 CRUD 개방은 원본 그대로이며
--     보안 강화는 이번 스코프 밖 — 별건으로 반드시 재검토.
-- ---------------------------------------------------------------------
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

DO $$
DECLARE r record; v_roles text; v_using text; v_check text;
BEGIN
    FOR r IN SELECT * FROM public._mig_ws_policies LOOP
        v_roles := replace(replace(r.roles, '{', ''), '}', '');
        v_using := CASE WHEN r.qual       IS NOT NULL THEN format(' USING (%s)', r.qual) ELSE '' END;
        v_check := CASE WHEN r.with_check IS NOT NULL THEN format(' WITH CHECK (%s)', r.with_check) ELSE '' END;
        EXECUTE format('CREATE POLICY %I ON public.work_schedules AS %s FOR %s TO %s%s%s',
                       r.policyname,
                       CASE WHEN r.permissive='PERMISSIVE' THEN 'PERMISSIVE' ELSE 'RESTRICTIVE' END,
                       r.cmd, v_roles, v_using, v_check);
    END LOOP;
END $$;


-- ---------------------------------------------------------------------
-- §14. OWNER + GRANTS — 스냅샷에서 동적 재생성
--   R3-1: is_grantable='YES' 는 WITH GRANT OPTION 까지 복원한다.
--         [실측] postgres grantee 의 7권한이 전부 YES 이므로 필수다.
--   ※ GRANT 를 실행하는 세션이 grantor 권한을 가져야 한다(운영자 = postgres).
-- ---------------------------------------------------------------------
ALTER TABLE public.work_schedules OWNER TO postgres;

DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT DISTINCT grantee, privilege_type, is_grantable
               FROM public._mig_ws_grants LOOP
        IF r.is_grantable = 'YES' THEN
            EXECUTE format('GRANT %s ON public.work_schedules TO %I WITH GRANT OPTION',
                           r.privilege_type, r.grantee);
        ELSE
            EXECUTE format('GRANT %s ON public.work_schedules TO %I',
                           r.privilege_type, r.grantee);
        END IF;
    END LOOP;
END $$;


-- ---------------------------------------------------------------------
-- §15. POSTCHECKS — EXACT CONTRACT EQUALITY (REV-2 지적 2)
-- ---------------------------------------------------------------------
DO $$
DECLARE
    v_diff bigint; v_parts int; v_owner name; v_rls bool; v_forced bool;
BEGIN
    -- (1) 데이터 37컬럼 full-row equality (스냅샷 대조)
    SELECT count(*) INTO v_diff FROM (
        (SELECT * FROM public._mig_ws_data_snapshot
         EXCEPT SELECT * FROM public.work_schedules)
        UNION ALL
        (SELECT * FROM public.work_schedules
         EXCEPT SELECT * FROM public._mig_ws_data_snapshot)) x;
    IF v_diff > 0 THEN RAISE EXCEPTION 'POSTCHECK FAIL: data full-row mismatch = %', v_diff; END IF;

    -- (2) 파티션 수
    SELECT count(*) INTO v_parts FROM pg_inherits WHERE inhparent='public.work_schedules'::regclass;
    IF v_parts <> 16 THEN RAISE EXCEPTION 'POSTCHECK FAIL: partitions = %', v_parts; END IF;

    -- (3) comments EXACT equality  (R3-3: public schema 한정)
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
    IF v_diff > 0 THEN RAISE EXCEPTION 'POSTCHECK FAIL: comments mismatch = %', v_diff; END IF;

    -- (4) grants EXACT equality  (R3-1: grantor·is_grantable 포함)
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
    IF v_diff > 0 THEN RAISE EXCEPTION 'POSTCHECK FAIL: grants mismatch = % (grantor/is_grantable 포함)', v_diff; END IF;

    -- (5) policy EXACT equality  (R3-3: public schema 한정)
    SELECT count(*) INTO v_diff FROM (
        (SELECT policyname, cmd, permissive, roles::text, qual, with_check FROM public._mig_ws_policies
         EXCEPT
         SELECT policyname, cmd, permissive, roles::text, qual, with_check FROM pg_policies
          WHERE schemaname='public' AND tablename='work_schedules')
        UNION ALL
        (SELECT policyname, cmd, permissive, roles::text, qual, with_check FROM pg_policies
          WHERE schemaname='public' AND tablename='work_schedules'
         EXCEPT
         SELECT policyname, cmd, permissive, roles::text, qual, with_check FROM public._mig_ws_policies)) x;
    IF v_diff > 0 THEN RAISE EXCEPTION 'POSTCHECK FAIL: policy mismatch = %', v_diff; END IF;

    -- (6) owner / RLS enabled+forced equality  (R3-2)
    SELECT pg_get_userbyid(relowner), relrowsecurity, relforcerowsecurity
      INTO v_owner, v_rls, v_forced
      FROM pg_class WHERE oid='public.work_schedules'::regclass;
    IF v_owner <> (SELECT owner_name FROM public._mig_ws_fingerprint) THEN
        RAISE EXCEPTION 'POSTCHECK FAIL: owner=%', v_owner;
    END IF;
    IF v_rls <> (SELECT rls_enabled FROM public._mig_ws_fingerprint) THEN
        RAISE EXCEPTION 'POSTCHECK FAIL: rls_enabled=%', v_rls;
    END IF;
    IF v_forced <> (SELECT rls_forced FROM public._mig_ws_fingerprint) THEN
        RAISE EXCEPTION 'POSTCHECK FAIL: rls_forced=% (fingerprint 불일치)', v_forced;
    END IF;

    -- (7) FK MATCH FULL
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname='work_assignments_schedule_fkey' AND confmatchtype='f') THEN
        RAISE EXCEPTION 'POSTCHECK FAIL: wa FK not MATCH FULL';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname='safety_inspections_schedule_fkey' AND confmatchtype='f') THEN
        RAISE EXCEPTION 'POSTCHECK FAIL: si FK not MATCH FULL';
    END IF;

    RAISE NOTICE 'POSTCHECK OK: data/comments/grants/policies/owner/RLS/FK 전부 EXACT';
END $$;

COMMIT;

-- =====================================================================
-- §16. 스냅샷 테이블 정리 시점
--   _mig_ws_data_snapshot 등은 DOWN 검증에 필요하므로 UP 직후 삭제하지 않는다.
--   최종 cleanup WP 에서 old table 과 함께 제거한다.
--
-- §17. SMOKE TEST (patched code 배포 직후)
--   · GET  /work-schedules?factory_id=...&planned_date_from=...   (목록)
--   · GET  /work-schedules/{id}                                   (단건, pruning 없음)
--   · PATCH /work-schedules/{id}  담당자 배정 → work_assignments INSERT (factory_id 포함 확인)
--   · POST /schedule-engine/generate/{set_id}                     (회차 생성 + 중복 체크)
--   · POST /worker-check/submit                                   (safety_inspections INSERT)
--
-- §18. 커밋 이후 (rollback window 종료 후)
--   · ANALYZE public.work_schedules;
--   · 기능 검증 통과 후에만: DROP TABLE public.work_schedules_old;
--     ⚠ old DROP 시 DOWN(FAST PATH) 불가.
--
-- §19. DROP 된 인덱스 복원 SQL
--   CREATE INDEX idx_ws_event_type ON public.work_schedules (event_type);
--   (is_excluded / status_date 는 DROP 이 아니라 복합 인덱스로 MERGE 됨 — §7 참조)
-- =====================================================================
