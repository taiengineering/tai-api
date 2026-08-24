-- =====================================================================
-- WP-PARTITION-02B-R1 : work_schedules → PARTITION BY HASH (factory_id)
-- UP MIGRATION  (CURRENT-STATE REBASE of 20260822 REV-3 — NOT APPLIED)
--
--   PostgreSQL 17.6 / Supabase project vwlahtguyggrhvslabax
--   REBASE BASE API HEAD = 6874bb85f5a9519d0f3c052f31492873a1a388bd (04E deployed)
--   CANONICAL PHYSICAL DESIGN = WORK_SCHEDULES_PARTITION_DESIGN_FINAL_v1 (설계 변경 없음)
--
--   [OLD PACKAGE 대비 REBASE 변경점 — 물리설계는 불변]
--   REBASE-1 (§10): OLD UP 은 work_assignments.factory_id / safety_inspections.factory_id 를
--                   "이번 HASH 가 ADD 하는 컬럼"으로 취급(ADD COLUMN + backfill + companion COMMENT).
--                   현재 이 두 컬럼은 04C(wa)/04D(si) 의 독립 LIVE 자산이다.
--                   → HASH UP 은 ADD 하지 않는다. PRECHECK(존재/타입/nullable/mismatch 0)만 수행.
--                   → companion COMMENT 도 새로 넣지 않는다(현재 comment=NULL, 04C/04D-owned metadata 불변).
--   REBASE-2 : backfill(§10 UPDATE) 제거. 04C/04D 가 이미 companion 을 채웠고 mismatch=0(실측).
--              대신 LOCK 이후 mismatch/null=0 을 PRECHECK 로 재확인(참조는 canonical parent).
--   REBASE-3 : child pair CHECK / composite FK / partition core(§3~§9,§11~§15) 는 OLD 설계 그대로 유지.
--
--   [REV-2 CRITICAL — 물리설계 불변]
--   CRITICAL-1 (§2 snapshot + §14-B rebind + §15-(9)): dashboard_stats matview OID rebind.
--   CRITICAL-2 (§2/§4/§12 REVOKE + §15-(10)): rollback anchor / snapshot / physical partition privilege lockdown.
--   [REV-3 CRITICAL-3 — ACL exactness]
--   ACL 스냅샷/POSTCHECK SoT = pg_class.relacl + aclexplode (information_schema.role_table_grants 는 PG17 MAINTAIN 누락 + matview 0 rows).
--   MAINTAIN 포함 8 privileges × role 캡처. restore 는 REVOKE ALL → 스냅샷 재생 → aclexplode 양방향 EXCEPT. matview ACL = arwdDxtm × 4 roles(owner-only 아님).
--   [REV-3A CRITICAL-4 — acldefault object type]
--   matview ACL fallback 도 acldefault('r',...) 사용. 'm'(relkind 코드)은 acldefault object type 인자로 무효 (PG17.6: ERROR unrecognized object type abbreviation: m).
--
--   [PRE-STATE 실측 2026-08-24 @ 6874bb85 · fresh]
--     work_schedules : rows=66 · cols=37 · factory_id NULL=0 · distinct factory=4 · dup target=0
--                      set/factory mismatch=0 · constraints=7 · CHECK=0 · indexes=12 · policies=6
--                      user triggers=0 · owner=postgres · RLS enabled=true forced=false · relkind='r' · comments=26
--                      ACL(aclexplode): anon/authenticated/service_role/postgres 각 arwdDxtm (SELECT/INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER/MAINTAIN)
--     dependent matview: dashboard_stats (owner postgres · populated · ws deps 3 · def 참조 12 · idx singleton · comment NULL · ACL arwdDxtm×4 · reloptions NULL · heap · permanent)
--     work_assignments   : rows=5991 · factory companion LIVE(04C) · linked factory NULL=0 · mismatch=0 · schedule NULL=0
--                          factory_id: uuid/nullable · comment=NULL
--     safety_inspections : rows=2 · linked=1 · legacy standalone(assignment NULL)=1 · linked factory NULL=0
--                          linked mismatch=0 · partial pair=0 · factory companion LIVE(04D) · factory_id uuid/nullable · comment=NULL
--     equipment_checkins : rows=0 · cross-factory=0 · direct anon INSERT path=OPEN (composite FK 가 봉쇄)
--     work_schedules_old / _new / _mig_* : 부재 (clean start)
--     현재 child→ws 단일 FK: work_assignments_schedule_id_fkey · safety_inspections_assignment_id_fkey
--                             · equipment_checkins_schedule_id_fkey(ON DELETE SET NULL)
--     현재 ws PK=work_schedules_pkey(id) · UNIQUE idx=uq_work_schedules_inspection_set_planned_date
--
--   ⚠ 실행 전 GPT 재검증 + 운영자 승인 필요. DB 미적용. 단일 transaction 원자성 필수.
-- =====================================================================

-- ---------------------------------------------------------------------
-- §0-A. CUTOVER ORDERING 계약 (REBASE)
--   OLD 계약은 "UP → patched code deploy → smoke" 였으나, 현재 04C/04D/04E writer 가 전부 LIVE 이고
--   HASH UP 은 신규 code deploy 를 동반하지 않는다(companion 컬럼 이미 존재).
--   [확정 순서]
--     1. maintenance ON (API/worker 트래픽 차단) + application write freeze
--     2. 활성 write 세션 0 확인
--     3. 이 UP 실행 (내부 ACCESS EXCLUSIVE LOCK = 2차 방어; equipment_checkins direct anon 도 lock 대기)
--     4. DB validation (POSTCHECK)
--     5. application health/static smoke (코드 배포 없음 → deployed SHA 불변 expected)
--     6. maintenance OFF
--   CODE DEPLOY = 0. Railway deployed SHA = migration 전후 동일.
-- ---------------------------------------------------------------------

BEGIN;

-- ---------------------------------------------------------------------
-- §0-B. WRITE FREEZE (4개 테이블 ACCESS EXCLUSIVE — direct anon equipment_checkins 포함 봉쇄)
-- ---------------------------------------------------------------------
LOCK TABLE public.work_schedules     IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.work_assignments   IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.safety_inspections IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.equipment_checkins IN ACCESS EXCLUSIVE MODE;


-- ---------------------------------------------------------------------
-- §1. HARD PRECHECKS (LOCK 이후 — direct anon path 때문에 값은 LOCK 이후에만 authoritative)
--   REBASE: child factory_id companion 은 04C/04D-owned → 존재/타입/nullable/mismatch 를 assertion.
--           ADD 하지 않는다. legacy si standalone(assignment NULL & factory NULL) 은 허용.
-- ---------------------------------------------------------------------
DO $$
DECLARE
    v_factory_null bigint; v_set_mismatch bigint; v_dup_unique bigint;
    v_wa_orphan bigint; v_si_orphan bigint; v_ec_mismatch bigint;
    v_checks bigint; v_triggers bigint; v_owner name;
    v_wa_fac_exists bool; v_si_fac_exists bool;
    v_wa_fac_type text; v_si_fac_type text; v_wa_fac_null text; v_si_fac_null text;
    v_wa_linked_null bigint; v_wa_mismatch bigint;
    v_si_linked_null bigint; v_si_mismatch bigint; v_si_partial bigint;
    v_ec_cross bigint;
BEGIN
    -- (parent) work_schedules
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

    IF v_factory_null > 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: ws factory_id NULL = %', v_factory_null; END IF;
    IF v_set_mismatch > 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: ws set/factory mismatch = %', v_set_mismatch; END IF;
    IF v_dup_unique   > 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: ws dup unique candidate = %', v_dup_unique; END IF;
    IF v_wa_orphan    > 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: wa orphan = %', v_wa_orphan; END IF;
    IF v_si_orphan    > 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: si orphan = %', v_si_orphan; END IF;
    IF v_ec_mismatch  > 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: ec factory mismatch = %', v_ec_mismatch; END IF;
    IF v_checks      <> 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: ws CHECK 제약 % (설계 0)', v_checks; END IF;
    IF v_triggers    <> 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: ws trigger % (설계 0)', v_triggers; END IF;
    IF v_owner  <> 'postgres' THEN RAISE EXCEPTION 'PRECHECK FAIL: ws owner=% (설계 postgres)', v_owner; END IF;

    -- (REBASE) child companion factory_id 는 04C/04D 소유 = 반드시 이미 존재해야 한다 (ADD 아님)
    SELECT EXISTS(SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='work_assignments' AND column_name='factory_id')
      INTO v_wa_fac_exists;
    SELECT EXISTS(SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='safety_inspections' AND column_name='factory_id')
      INTO v_si_fac_exists;
    IF NOT v_wa_fac_exists THEN RAISE EXCEPTION 'PRECHECK FAIL: work_assignments.factory_id 부재 (04C 미적용?) — HASH 는 ADD 하지 않음'; END IF;
    IF NOT v_si_fac_exists THEN RAISE EXCEPTION 'PRECHECK FAIL: safety_inspections.factory_id 부재 (04D 미적용?) — HASH 는 ADD 하지 않음'; END IF;

    SELECT data_type, is_nullable INTO v_wa_fac_type, v_wa_fac_null FROM information_schema.columns
      WHERE table_schema='public' AND table_name='work_assignments' AND column_name='factory_id';
    SELECT data_type, is_nullable INTO v_si_fac_type, v_si_fac_null FROM information_schema.columns
      WHERE table_schema='public' AND table_name='safety_inspections' AND column_name='factory_id';
    IF v_wa_fac_type <> 'uuid' OR v_wa_fac_null <> 'YES' THEN RAISE EXCEPTION 'PRECHECK FAIL: wa.factory_id 타입/nullable=%/%', v_wa_fac_type, v_wa_fac_null; END IF;
    IF v_si_fac_type <> 'uuid' OR v_si_fac_null <> 'YES' THEN RAISE EXCEPTION 'PRECHECK FAIL: si.factory_id 타입/nullable=%/%', v_si_fac_type, v_si_fac_null; END IF;

    -- (REBASE) child companion 정합: linked null / mismatch = 0. legacy si standalone 은 허용, partial pair 는 금지.
    SELECT count(*) INTO v_wa_linked_null FROM public.work_assignments WHERE schedule_id IS NOT NULL AND factory_id IS NULL;
    SELECT count(*) INTO v_wa_mismatch FROM public.work_assignments wa JOIN public.work_schedules ws ON ws.id=wa.schedule_id
       WHERE wa.factory_id IS DISTINCT FROM ws.factory_id;
    IF v_wa_linked_null > 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: wa linked factory NULL = %', v_wa_linked_null; END IF;
    IF v_wa_mismatch    > 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: wa factory mismatch = %', v_wa_mismatch; END IF;

    SELECT count(*) INTO v_si_linked_null FROM public.safety_inspections WHERE assignment_id IS NOT NULL AND factory_id IS NULL;
    SELECT count(*) INTO v_si_mismatch FROM public.safety_inspections si JOIN public.work_schedules ws ON ws.id=si.assignment_id
       WHERE si.factory_id IS DISTINCT FROM ws.factory_id;
    SELECT count(*) INTO v_si_partial FROM public.safety_inspections
       WHERE (assignment_id IS NULL) <> (factory_id IS NULL);   -- partial pair (한쪽만 NULL) 금지
    IF v_si_linked_null > 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: si linked factory NULL = %', v_si_linked_null; END IF;
    IF v_si_mismatch    > 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: si linked factory mismatch = %', v_si_mismatch; END IF;
    IF v_si_partial     > 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: si partial pair(한쪽만 NULL) = %', v_si_partial; END IF;
    -- legacy standalone (assignment NULL & factory NULL) 은 위 조건들을 자연히 통과 → 허용.

    -- (REBASE) equipment_checkins cross-factory (LOCK 이후이므로 direct anon 우회분까지 포함해 authoritative)
    SELECT count(*) INTO v_ec_cross FROM public.equipment_checkins ec
      JOIN public.equipment_assets ea ON ea.id = ec.equipment_asset_id
      JOIN public.work_schedules ws ON ws.id = ec.schedule_id
     WHERE ec.schedule_id IS NOT NULL AND ea.factory_id IS DISTINCT FROM ws.factory_id;
    IF v_ec_cross > 0 THEN RAISE EXCEPTION 'PRECHECK FAIL: equipment_checkins cross-factory = % (human resolution 필요)', v_ec_cross; END IF;

    RAISE NOTICE 'PRECHECK OK (parent + 04C/04D companion assertion + ec cross-factory 0)';
END $$;


-- ---------------------------------------------------------------------
-- §2. PRE-STATE CONTRACT 캡처 (내용 기반 — DOWN exact 비교용)
-- ---------------------------------------------------------------------
CREATE TABLE public._mig_ws_fingerprint AS
SELECT
    (SELECT count(*)                   FROM public.work_schedules) AS row_count,
    (SELECT count(DISTINCT factory_id) FROM public.work_schedules) AS distinct_factory,
    (SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='public.work_schedules'::regclass) AS owner_name,
    (SELECT relrowsecurity FROM pg_class WHERE oid='public.work_schedules'::regclass) AS rls_enabled,
    (SELECT relforcerowsecurity FROM pg_class WHERE oid='public.work_schedules'::regclass) AS rls_forced,
    now() AS captured_at;

CREATE TABLE public._mig_ws_data_snapshot AS
SELECT * FROM public.work_schedules;

CREATE TABLE public._mig_ws_comments AS
SELECT coalesce(a.attname, '(table)') AS objname, d.description
  FROM pg_description d
  JOIN pg_class c ON c.oid = d.objoid AND c.relname='work_schedules'
  JOIN pg_namespace ns ON ns.oid = c.relnamespace AND ns.nspname='public'
  LEFT JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.objsubid;

CREATE TABLE public._mig_ws_grants AS
SELECT
    CASE WHEN a.grantor=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantor) END AS grantor,
    CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS grantee,
    a.privilege_type, a.is_grantable
  FROM pg_class c
  CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl, acldefault('r', c.relowner))) a
 WHERE c.oid='public.work_schedules'::regclass;
-- [REV-3 CRITICAL-3] ACL SoT = pg_class.relacl + aclexplode (information_schema.role_table_grants 는 PG17 MAINTAIN 누락).
--   grantee/grantor 는 oid 0 → PUBLIC 매핑. is_grantable 은 boolean.

CREATE TABLE public._mig_ws_policies AS
SELECT policyname, cmd, permissive, roles::text AS roles, qual, with_check
  FROM pg_policies WHERE schemaname='public' AND tablename='work_schedules';

-- [REV-2 CRITICAL-2] rollback anchor 보호: _mig_* 는 postgres 만 접근. anon/authenticated/service_role 변조 차단.
--   특히 _mig_ws_data_snapshot 은 RLS 없는 work_schedules 전량 스냅샷 → default public grant 로 노출/변조되면 rollback 기준 훼손.
DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT unnest(ARRAY['_mig_ws_fingerprint','_mig_ws_data_snapshot','_mig_ws_comments','_mig_ws_grants','_mig_ws_policies']) AS t
    LOOP
        EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM PUBLIC', r.t);
        EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM anon, authenticated, service_role', r.t);
    END LOOP;
END $$;

-- [REV-2 CRITICAL-1] dashboard_stats matview dependency 스냅샷 (rename 시 OID 가 old 를 계속 가리키므로 swap 후 재생성 필요)
CREATE TABLE public._mig_ws_matview AS
SELECT
    'dashboard_stats'::text AS matview_name,
    pg_get_viewdef('public.dashboard_stats'::regclass, true) AS definition,
    pg_get_userbyid(relowner) AS owner_name,
    relispopulated AS populated,
    obj_description('public.dashboard_stats'::regclass) AS comment_text
  FROM pg_class WHERE oid='public.dashboard_stats'::regclass;

CREATE TABLE public._mig_ws_matview_idx AS
SELECT indexname, indexdef FROM pg_indexes
 WHERE schemaname='public' AND tablename='dashboard_stats';

CREATE TABLE public._mig_ws_matview_grants AS
SELECT
    CASE WHEN a.grantor=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantor) END AS grantor,
    CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS grantee,
    a.privilege_type, a.is_grantable
  FROM pg_class c
  CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl, acldefault('r', c.relowner))) a
 WHERE c.oid='public.dashboard_stats'::regclass;
-- [REV-3 CRITICAL-3] matview ACL 도 aclexplode. 실측: anon/authenticated/service_role/postgres 각 arwdDxtm (owner-only 아님).
-- [REV-3A CRITICAL-4] acldefault object type code 는 matview 도 'r'(relation) 사용. 'm' 은 pg_class.relkind 코드이지 acldefault 인자가 아님
--   (PG17.6 실측: acldefault('m',...) → ERROR unrecognized object type abbreviation: m). relacl non-NULL 이라 현재는 COALESCE 로 평가 안 되지만 실행가능성 보장.

DO $$
BEGIN
    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public._mig_ws_matview FROM PUBLIC';
    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public._mig_ws_matview FROM anon, authenticated, service_role';
    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public._mig_ws_matview_idx FROM PUBLIC';
    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public._mig_ws_matview_idx FROM anon, authenticated, service_role';
    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public._mig_ws_matview_grants FROM PUBLIC';
    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public._mig_ws_matview_grants FROM anon, authenticated, service_role';
END $$;


-- ---------------------------------------------------------------------
-- §3. SHADOW PARTITIONED TABLE  (PK(id,factory_id) 계약 → factory_id NOT NULL)
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

ALTER TABLE public.work_schedules_new OWNER TO postgres;


-- ---------------------------------------------------------------------
-- §4. HASH PARTITIONS (MODULUS 16) + owner
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
        -- [REV-2 CRITICAL-2] physical child (p00~p15) 직접 노출 차단.
        --   접근은 logical parent(work_schedules) 경유만. physical child 를 PostgREST 에 직접 노출하지 않는다.
        EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM PUBLIC', r.relname);
        EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM anon, authenticated, service_role', r.relname);
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
-- §6. COPY VALIDATION — 37컬럼 FULL-ROW EQUALITY (양방향 EXCEPT)
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
-- §7. INDEXES (OLD 설계 유지)
-- ---------------------------------------------------------------------
CREATE INDEX idx_ws_new_factory_planned  ON public.work_schedules_new (factory_id, planned_date);
CREATE INDEX idx_ws_new_factory_status_p ON public.work_schedules_new (factory_id, status_code, planned_date);
CREATE INDEX idx_ws_new_factory_excluded ON public.work_schedules_new (factory_id, is_excluded);
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
-- §9. COMMENTS 복제 — 스냅샷에서 동적 재생성
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
-- §10. [REBASE] CHILD companion 은 04C/04D-owned — ADD/backfill/COMMENT 하지 않는다.
--   OLD UP §10 의 ALTER ADD COLUMN / UPDATE backfill / COMMENT 부여는 전부 제거됨.
--   근거: work_assignments.factory_id=04C LIVE · safety_inspections.factory_id=04D LIVE ·
--         현재 comment=NULL(둘 다) · linked null/mismatch=0 (§1 PRECHECK 에서 이미 assertion).
--   HASH 는 이 컬럼들의 값/메타데이터를 변경하지 않는다. (child pair CHECK 는 §11, composite FK 는 §12)
-- ---------------------------------------------------------------------


-- ---------------------------------------------------------------------
-- §11. CHILD NULL 계약 (MATCH SIMPLE 우회 차단) — wa/si 에만 pair CHECK
--   legacy si standalone(assignment NULL & factory NULL) 은 (NULL)=(NULL)=true 로 통과.
--   equipment_checkins 는 pair CHECK 없음(schedule optional, factory=asset).
-- ---------------------------------------------------------------------
ALTER TABLE public.work_assignments
    ADD CONSTRAINT chk_wa_schedule_factory_pair
    CHECK ((schedule_id IS NULL) = (factory_id IS NULL));

ALTER TABLE public.safety_inspections
    ADD CONSTRAINT chk_si_schedule_factory_pair
    CHECK ((assignment_id IS NULL) = (factory_id IS NULL));


-- ---------------------------------------------------------------------
-- §12. CUTOVER + CHILD 복합 FK (child별 MATCH 계약)
--   현재 단일 FK 이름(실측): work_assignments_schedule_id_fkey · safety_inspections_assignment_id_fkey
--                            · equipment_checkins_schedule_id_fkey
-- ---------------------------------------------------------------------
ALTER TABLE public.work_assignments   DROP CONSTRAINT IF EXISTS work_assignments_schedule_id_fkey;
ALTER TABLE public.safety_inspections DROP CONSTRAINT IF EXISTS safety_inspections_assignment_id_fkey;
ALTER TABLE public.equipment_checkins DROP CONSTRAINT IF EXISTS equipment_checkins_schedule_id_fkey;

ALTER TABLE public.work_schedules     RENAME TO work_schedules_old;
ALTER TABLE public.work_schedules_new RENAME TO work_schedules;

-- [REV-2 CRITICAL-2] rollback anchor(work_schedules_old) 직접 write surface 차단.
--   old 는 rename 되며 기존 permissive RLS 정책(anon INSERT/UPDATE/DELETE=true)과 grants 를 그대로 들고 온다.
--   → anchor 무결성 위해 anon/authenticated/service_role/ PUBLIC 권한 회수. postgres(=DOWN 수행자) 만 접근.
--   (기존 RLS 정책은 old 에 남지만, table-level GRANT 가 없으면 anon/authenticated 는 접근 불가.)
REVOKE ALL PRIVILEGES ON TABLE public.work_schedules_old FROM PUBLIC;
REVOKE ALL PRIVILEGES ON TABLE public.work_schedules_old FROM anon, authenticated, service_role;

-- A. work_assignments : MATCH FULL
ALTER TABLE public.work_assignments
    ADD CONSTRAINT work_assignments_schedule_fkey
        FOREIGN KEY (schedule_id, factory_id)
        REFERENCES public.work_schedules (id, factory_id) MATCH FULL;

-- B. safety_inspections : MATCH FULL (legacy NULL pair 통과)
ALTER TABLE public.safety_inspections
    ADD CONSTRAINT safety_inspections_schedule_fkey
        FOREIGN KEY (assignment_id, factory_id)
        REFERENCES public.work_schedules (id, factory_id) MATCH FULL;

-- C. equipment_checkins : MATCH SIMPLE + ON DELETE SET NULL (schedule_id) [PG15+; 17.6]
--    factory_id = asset authority → schedule 삭제 시 schedule_id 만 NULL, factory_id 보존.
ALTER TABLE public.equipment_checkins
    ADD CONSTRAINT equipment_checkins_schedule_fkey
        FOREIGN KEY (schedule_id, factory_id)
        REFERENCES public.work_schedules (id, factory_id)
        ON DELETE SET NULL (schedule_id);


-- ---------------------------------------------------------------------
-- §13. RLS / POLICY — 스냅샷에서 동적 재생성 (enabled+forced exact)
-- ---------------------------------------------------------------------
DO $$
DECLARE v_enabled bool; v_forced bool;
BEGIN
    SELECT rls_enabled, rls_forced INTO v_enabled, v_forced FROM public._mig_ws_fingerprint;
    IF v_enabled THEN ALTER TABLE public.work_schedules ENABLE ROW LEVEL SECURITY;
    ELSE ALTER TABLE public.work_schedules DISABLE ROW LEVEL SECURITY; END IF;
    IF v_forced THEN ALTER TABLE public.work_schedules FORCE ROW LEVEL SECURITY;
    ELSE ALTER TABLE public.work_schedules NO FORCE ROW LEVEL SECURITY; END IF;
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
-- §14. OWNER + GRANTS — 스냅샷에서 동적 재생성 (REV-3: aclexplode SoT + ACL reset, is_grantable boolean, PUBLIC 처리)
-- ---------------------------------------------------------------------
ALTER TABLE public.work_schedules OWNER TO postgres;

-- [REV-3 CRITICAL-3] 명시 ACL reset 후 스냅샷 재생 (default ACL 우연 의존 제거).
REVOKE ALL PRIVILEGES ON TABLE public.work_schedules FROM PUBLIC;
REVOKE ALL PRIVILEGES ON TABLE public.work_schedules FROM anon, authenticated, service_role;
DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT DISTINCT grantee, privilege_type, is_grantable
               FROM public._mig_ws_grants LOOP
        IF r.is_grantable THEN
            EXECUTE format('GRANT %s ON public.work_schedules TO %s WITH GRANT OPTION',
                           r.privilege_type, CASE WHEN r.grantee='PUBLIC' THEN 'PUBLIC' ELSE quote_ident(r.grantee) END);
        ELSE
            EXECUTE format('GRANT %s ON public.work_schedules TO %s',
                           r.privilege_type, CASE WHEN r.grantee='PUBLIC' THEN 'PUBLIC' ELSE quote_ident(r.grantee) END);
        END IF;
    END LOOP;
END $$;


-- ---------------------------------------------------------------------
-- §14-B. [REV-2 CRITICAL-1] dashboard_stats MATVIEW OID REBIND
--   matview 는 relation OID 로 dependency 를 잡으므로, rename 만으로는 old(=work_schedules_old) 를 계속 참조.
--   → 같은 transaction 안에서 DROP 후 스냅샷 definition 으로 재생성하여 NEW canonical work_schedules 에 재결합.
--   owner/index/grants/comment/ populated(WITH DATA) 복원. matview 정의는 이름 'work_schedules' 를 참조하므로
--   재생성 시점엔 NEW canonical 이 이미 그 이름을 가진다(§12 swap 완료) → 자동으로 NEW OID 에 결합.
-- ---------------------------------------------------------------------
DO $$
DECLARE
    v_def text; v_owner name; v_populated bool; v_comment text; r record;
BEGIN
    SELECT definition, owner_name, populated, comment_text
      INTO v_def, v_owner, v_populated, v_comment FROM public._mig_ws_matview LIMIT 1;

    -- DROP old-bound matview (CASCADE 불필요: dashboard_stats 에 종속된 추가 객체 없음 — 있으면 사전 STOP 대상)
    EXECUTE 'DROP MATERIALIZED VIEW IF EXISTS public.dashboard_stats';

    -- 재생성 (populated 였으면 WITH DATA)
    EXECUTE format('CREATE MATERIALIZED VIEW public.dashboard_stats AS %s WITH %s DATA',
                   v_def, CASE WHEN v_populated THEN '' ELSE 'NO' END);

    -- owner 복원
    EXECUTE format('ALTER MATERIALIZED VIEW public.dashboard_stats OWNER TO %I', v_owner);

    -- index 복원 (idx_dashboard_stats_singleton = UNIQUE ((1)); CONCURRENTLY refresh 전제)
    FOR r IN SELECT indexdef FROM public._mig_ws_matview_idx LOOP
        EXECUTE r.indexdef;
    END LOOP;

    -- comment 복원 (원본 NULL 이면 skip)
    IF v_comment IS NOT NULL THEN
        EXECUTE format('COMMENT ON MATERIALIZED VIEW public.dashboard_stats IS %L', v_comment);
    END IF;

    -- grants 복원 [REV-3 CRITICAL-3]: ACL reset 후 aclexplode 스냅샷 재생 (MAINTAIN 포함, arwdDxtm × roles).
    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public.dashboard_stats FROM PUBLIC';
    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public.dashboard_stats FROM anon, authenticated, service_role';
    FOR r IN SELECT grantee, privilege_type, is_grantable FROM public._mig_ws_matview_grants LOOP
        IF r.is_grantable THEN
            EXECUTE format('GRANT %s ON public.dashboard_stats TO %s WITH GRANT OPTION',
                           r.privilege_type, CASE WHEN r.grantee='PUBLIC' THEN 'PUBLIC' ELSE quote_ident(r.grantee) END);
        ELSE
            EXECUTE format('GRANT %s ON public.dashboard_stats TO %s',
                           r.privilege_type, CASE WHEN r.grantee='PUBLIC' THEN 'PUBLIC' ELSE quote_ident(r.grantee) END);
        END IF;
    END LOOP;
END $$;


-- ---------------------------------------------------------------------
-- §15. POSTCHECKS — EXACT CONTRACT EQUALITY (+ REBASE: child companion 보존 검증)
-- ---------------------------------------------------------------------
DO $$
DECLARE
    v_diff bigint; v_parts int; v_owner name; v_rls bool; v_forced bool;
    v_wa_fac bool; v_si_fac bool;
BEGIN
    -- (1) 데이터 37컬럼 full-row equality (스냅샷 대조)
    SELECT count(*) INTO v_diff FROM (
        (SELECT * FROM public._mig_ws_data_snapshot EXCEPT SELECT * FROM public.work_schedules)
        UNION ALL
        (SELECT * FROM public.work_schedules EXCEPT SELECT * FROM public._mig_ws_data_snapshot)) x;
    IF v_diff > 0 THEN RAISE EXCEPTION 'POSTCHECK FAIL: data full-row mismatch = %', v_diff; END IF;

    -- (2) 파티션 수
    SELECT count(*) INTO v_parts FROM pg_inherits WHERE inhparent='public.work_schedules'::regclass;
    IF v_parts <> 16 THEN RAISE EXCEPTION 'POSTCHECK FAIL: partitions = %', v_parts; END IF;

    -- (3) comments EXACT equality
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

    -- (4) grants EXACT equality [REV-3 CRITICAL-3: aclexplode SoT, MAINTAIN 포함]
    SELECT count(*) INTO v_diff FROM (
        (SELECT grantor, grantee, privilege_type, is_grantable FROM public._mig_ws_grants
         EXCEPT
         SELECT CASE WHEN a.grantor=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantor) END,
                CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
                a.privilege_type, a.is_grantable
           FROM pg_class c CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl, acldefault('r', c.relowner))) a
          WHERE c.oid='public.work_schedules'::regclass)
        UNION ALL
        (SELECT CASE WHEN a.grantor=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantor) END,
                CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
                a.privilege_type, a.is_grantable
           FROM pg_class c CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl, acldefault('r', c.relowner))) a
          WHERE c.oid='public.work_schedules'::regclass
         EXCEPT
         SELECT grantor, grantee, privilege_type, is_grantable FROM public._mig_ws_grants)) x;
    IF v_diff > 0 THEN RAISE EXCEPTION 'POSTCHECK FAIL: grants mismatch = % (aclexplode/MAINTAIN 포함)', v_diff; END IF;

    -- (5) policy EXACT equality
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

    -- (6) owner / RLS enabled+forced equality
    SELECT pg_get_userbyid(relowner), relrowsecurity, relforcerowsecurity
      INTO v_owner, v_rls, v_forced FROM pg_class WHERE oid='public.work_schedules'::regclass;
    IF v_owner <> (SELECT owner_name FROM public._mig_ws_fingerprint) THEN RAISE EXCEPTION 'POSTCHECK FAIL: owner=%', v_owner; END IF;
    IF v_rls <> (SELECT rls_enabled FROM public._mig_ws_fingerprint) THEN RAISE EXCEPTION 'POSTCHECK FAIL: rls_enabled=%', v_rls; END IF;
    IF v_forced <> (SELECT rls_forced FROM public._mig_ws_fingerprint) THEN RAISE EXCEPTION 'POSTCHECK FAIL: rls_forced=%', v_forced; END IF;

    -- (7) child composite FK MATCH type
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='work_assignments_schedule_fkey' AND confmatchtype='f') THEN
        RAISE EXCEPTION 'POSTCHECK FAIL: wa FK not MATCH FULL'; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='safety_inspections_schedule_fkey' AND confmatchtype='f') THEN
        RAISE EXCEPTION 'POSTCHECK FAIL: si FK not MATCH FULL'; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='equipment_checkins_schedule_fkey' AND confmatchtype='s') THEN
        RAISE EXCEPTION 'POSTCHECK FAIL: ec FK not MATCH SIMPLE'; END IF;

    -- (8) [REBASE] child companion factory_id 는 여전히 존재해야 한다 (HASH 가 삭제하지 않음)
    SELECT EXISTS(SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='work_assignments' AND column_name='factory_id') INTO v_wa_fac;
    SELECT EXISTS(SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='safety_inspections' AND column_name='factory_id') INTO v_si_fac;
    IF NOT v_wa_fac THEN RAISE EXCEPTION 'POSTCHECK FAIL: work_assignments.factory_id 소실(04C 자산)'; END IF;
    IF NOT v_si_fac THEN RAISE EXCEPTION 'POSTCHECK FAIL: safety_inspections.factory_id 소실(04D 자산)'; END IF;

    -- (9) [REV-2 CRITICAL-1] dashboard_stats matview 가 NEW canonical work_schedules(OID) 에 재결합됐는지
    IF NOT EXISTS (
        SELECT 1 FROM pg_depend d
          JOIN pg_rewrite rw ON rw.oid = d.objid
          JOIN pg_class mv ON mv.oid = rw.ev_class AND mv.relname='dashboard_stats' AND mv.relkind='m'
         WHERE d.refobjid = 'public.work_schedules'::regclass) THEN
        RAISE EXCEPTION 'POSTCHECK FAIL: dashboard_stats 가 NEW work_schedules 에 미결합 (여전히 old OID 참조)';
    END IF;
    -- old table 에는 더 이상 matview dependency 가 없어야 함
    IF EXISTS (
        SELECT 1 FROM pg_depend d
          JOIN pg_rewrite rw ON rw.oid = d.objid
          JOIN pg_class mv ON mv.oid = rw.ev_class AND mv.relname='dashboard_stats' AND mv.relkind='m'
         WHERE d.refobjid = 'public.work_schedules_old'::regclass) THEN
        RAISE EXCEPTION 'POSTCHECK FAIL: dashboard_stats 가 여전히 work_schedules_old 를 참조';
    END IF;
    -- (9-B) [REV-3 CRITICAL-3] matview ACL 이 스냅샷대로 복원됐는지 (aclexplode, MAINTAIN 포함)
    SELECT count(*) INTO v_diff FROM (
        (SELECT grantor, grantee, privilege_type, is_grantable FROM public._mig_ws_matview_grants
         EXCEPT
         SELECT CASE WHEN a.grantor=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantor) END,
                CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
                a.privilege_type, a.is_grantable
           FROM pg_class c CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl, acldefault('r', c.relowner))) a
          WHERE c.oid='public.dashboard_stats'::regclass)
        UNION ALL
        (SELECT CASE WHEN a.grantor=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantor) END,
                CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
                a.privilege_type, a.is_grantable
           FROM pg_class c CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl, acldefault('r', c.relowner))) a
          WHERE c.oid='public.dashboard_stats'::regclass
         EXCEPT
         SELECT grantor, grantee, privilege_type, is_grantable FROM public._mig_ws_matview_grants)) x;
    IF v_diff > 0 THEN RAISE EXCEPTION 'POSTCHECK FAIL: dashboard_stats grants mismatch = % (aclexplode/MAINTAIN)', v_diff; END IF;

    -- (10) [REV-2 CRITICAL-2] anchor / snapshot / physical child 직접 노출 차단 확인
    IF has_table_privilege('anon','public.work_schedules_old','SELECT')
       OR has_table_privilege('authenticated','public.work_schedules_old','UPDATE')
       OR has_table_privilege('service_role','public.work_schedules_old','SELECT') THEN
        RAISE EXCEPTION 'POSTCHECK FAIL: work_schedules_old 직접 권한 잔존 (anchor 변조 가능)';
    END IF;
    IF has_table_privilege('anon','public._mig_ws_data_snapshot','SELECT')
       OR has_table_privilege('authenticated','public._mig_ws_data_snapshot','UPDATE') THEN
        RAISE EXCEPTION 'POSTCHECK FAIL: _mig_ws_data_snapshot 직접 권한 잔존';
    END IF;
    IF has_table_privilege('anon','public.work_schedules_p00','SELECT')
       OR has_table_privilege('authenticated','public.work_schedules_p00','SELECT')
       OR has_table_privilege('service_role','public.work_schedules_p00','SELECT') THEN
        RAISE EXCEPTION 'POSTCHECK FAIL: physical partition 직접 권한 잔존 (p00 노출)';
    END IF;
    -- canonical parent 는 grants 스냅샷대로 복원됐는지 (service_role SELECT 가능해야 API 정상)
    IF NOT has_table_privilege('service_role','public.work_schedules','SELECT') THEN
        RAISE EXCEPTION 'POSTCHECK FAIL: canonical work_schedules service_role SELECT 미복원';
    END IF;

    RAISE NOTICE 'POSTCHECK OK: data/comments/grants(aclexplode·MAINTAIN)/policies/owner/RLS/FK EXACT + companion 보존 + matview NEW OID rebind + matview ACL + anchor/partition lockdown';
END $$;

COMMIT;

-- =====================================================================
-- §16. 스냅샷 테이블 정리 시점 — DOWN 검증에 필요하므로 UP 직후 삭제 안 함. cleanup WP 에서 old 와 함께 제거.
--   대상: _mig_ws_fingerprint/_data_snapshot/_comments/_grants/_policies/_matview/_matview_idx/_matview_grants
--   (전부 anon/authenticated/service_role REVOKE 상태 = anchor 보호)
-- §17. SMOKE (코드 배포 없음 · production synthetic business write = 0 · READ-ONLY only)
--   · /health 200 · deployed SHA == migration 전과 동일
--   · GET /work-schedules?factory_id=...  (partition pruning 동작) · GET /work-schedules/{id}
--   · EXPLAIN 으로 partition pruning 확인 (logical parent 경유; physical child 직접 접근 아님)
--   · refresh_dashboard_stats() 1회 → NEW canonical 참조 정상 확인
--   · business write(PATCH/POST) smoke 금지. FK/pair 는 dry-run 에서 이미 증명. natural write 는 관찰만.
-- §18. 커밋 이후 순서: POST VALIDATION → ANALYZE public.work_schedules → read-only smoke → MAINTENANCE OFF.
--      기능 검증 통과 후에만 DROP work_schedules_old (그 전엔 FAST-PATH DOWN 가능; matview 는 이미 NEW 결합이라 old DROP 미차단)
-- §19. DROP 된 인덱스 복원: CREATE INDEX idx_ws_event_type ON public.work_schedules (event_type);
--   (is_excluded/status_date 는 복합 인덱스로 MERGE — §7)
-- =====================================================================
