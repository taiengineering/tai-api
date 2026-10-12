-- DRAFT — NOT APPLIED TO PRODUCTION
-- EXT-037 화학안전원 화학물질안전정보 스냅샷 기반 스토리지 (TAI-WO-P0-05-EXT037)
-- G1 probe 확인: XML 응답, resultCode "00", dataNo PK (TEXT), 7189건
-- GAP-B: source_id + checkpoint 필드
-- GAP-D/R3-03: fn_ext037_complete_snapshot — run 소유권 검증 + 원자적 승격
-- PATCH-02: fn_ext037_save_page_checkpoint — 원자적 페이지 저장 + 체크포인트
-- PATCH-04: is_current 열 — 단일 현행판 포인터, fn_ext037_complete_snapshot 원자적 전환
-- R3-01: public_data_source_runtime seed 행 (is_enabled=false)
-- Apply only after: Owner approval obtained, migration slot confirmed

-- ============================================================
-- 스냅샷 헤더 테이블
-- ============================================================
create table if not exists ext037_chemical_safety_snapshots (
    id                      uuid        primary key default gen_random_uuid(),
    run_id                  text        not null,
    source_id               text        not null default 'EXT037_CHEMICAL_SAFETY',
    status                  text        not null default 'STAGING'
                                        check (status in ('STAGING', 'COMPLETED', 'FAILED')),
    total_fetched           int,
    content_hash            text,
    error_message           text,
    -- GAP-B: 체크포인트 필드
    last_page_no            int         not null default 0,
    checkpoint_total_count  int,
    checkpoint_api_total    int,
    -- PATCH-04: 단일 현행판 포인터 (fn_ext037_complete_snapshot이 원자적으로 전환)
    is_current              boolean     not null default false,
    created_at              timestamptz not null default now(),
    completed_at            timestamptz
);

comment on table ext037_chemical_safety_snapshots is
    'EXT-037 화학안전원 화학물질안전정보 수집 스냅샷. STAGING→COMPLETED 원자적 프로모션.';

-- source_id 당 STAGING 스냅샷 하나만 허용
create unique index if not exists uidx_ext037_snapshots_one_staging
    on ext037_chemical_safety_snapshots (source_id)
    where status = 'STAGING';

-- status 인덱스 (COMPLETED 최신 조회용)
create index if not exists idx_ext037_snapshots_status_completed_at
    on ext037_chemical_safety_snapshots (status, completed_at desc);

-- PATCH-04: source_id 당 is_current=true 스냅샷 최대 1개 강제 (DB 수준 불변식)
create unique index if not exists uidx_ext037_snapshots_one_current
    on ext037_chemical_safety_snapshots (source_id)
    where is_current = true;

-- ============================================================
-- 스냅샷 아이템 테이블
-- ============================================================
create table if not exists ext037_chemical_safety_snapshot_items (
    id              bigserial   primary key,
    snapshot_id     uuid        not null references ext037_chemical_safety_snapshots(id) on delete cascade,
    datano          text        not null,   -- G1 probe 확인: dataNo PK (TEXT)
    raw             jsonb       not null default '{}',
    created_at      timestamptz not null default now(),

    unique (snapshot_id, datano)
);

comment on table ext037_chemical_safety_snapshot_items is
    'EXT-037 스냅샷별 화학물질안전정보 레코드. datano = G1 probe 확인 PK.';

create index if not exists idx_ext037_items_snapshot_id
    on ext037_chemical_safety_snapshot_items (snapshot_id);

-- ============================================================
-- PATCH-02: 원자적 페이지 저장 + 체크포인트 RPC
-- ============================================================
create or replace function fn_ext037_save_page_checkpoint(
    p_snapshot_id   uuid,
    p_items         jsonb,      -- array of {datano: text, raw: object}
    p_page_no       int,
    p_api_total     int,        -- nullable
    p_run_id        uuid        -- 쓰기 전 소유권 + Lease 검증용
) returns int
language plpgsql
security invoker
as $$
declare
    v_item          jsonb;
    v_actual_count  int;
    v_source_id     text;
    v_current_run   uuid;
    v_run_status    text;
    v_lease_until   timestamptz;
    v_snap_status   text;
begin
    -- 스냅샷의 source_id 조회 (잠금 전 source_id 확보)
    select source_id into v_source_id
    from ext037_chemical_safety_snapshots
    where id = p_snapshot_id;

    if not found then
        raise exception 'RUN_FENCED: snapshot % not found', p_snapshot_id;
    end if;

    -- runtime FOR UPDATE FIRST — deadlock 방지
    select current_run_id into v_current_run
    from public_data_source_runtime
    where source_id = v_source_id
    for update;

    if v_current_run is null or v_current_run::text != p_run_id::text then
        raise exception 'RUN_FENCED: run_id=% is not current owner of source=%', p_run_id, v_source_id;
    end if;

    -- Run 상태 + Lease 유효성 검증
    select status, lease_until into v_run_status, v_lease_until
    from public_data_sync_runs
    where id = p_run_id;

    if not found or v_run_status != 'RUNNING' or v_lease_until <= now() then
        raise exception 'RUN_FENCED: run_id=% is not RUNNING or lease expired', p_run_id;
    end if;

    -- snapshot FOR UPDATE 잠금 + STAGING 상태 검증 (COMPLETED/FAILED 쓰기 차단)
    select status into v_snap_status
    from ext037_chemical_safety_snapshots
    where id = p_snapshot_id
    for update;

    if v_snap_status != 'STAGING' then
        raise exception 'SNAPSHOT_NOT_STAGING: snapshot % has status=%, expected STAGING',
            p_snapshot_id, v_snap_status;
    end if;

    -- 1. upsert items (snapshot_id,datano on_conflict)
    for v_item in select * from jsonb_array_elements(p_items)
    loop
        insert into ext037_chemical_safety_snapshot_items
            (snapshot_id, datano, raw, created_at)
        values
            (p_snapshot_id, v_item->>'datano', coalesce(v_item->'raw', '{}'), now())
        on conflict (snapshot_id, datano) do update
            set raw = excluded.raw;
    end loop;

    -- 2. actual DB unique item count (idempotent — re-run safe)
    select count(*) into v_actual_count
    from ext037_chemical_safety_snapshot_items
    where snapshot_id = p_snapshot_id;

    -- 3. checkpoint UPDATE
    update ext037_chemical_safety_snapshots
    set
        last_page_no           = p_page_no,
        checkpoint_total_count = v_actual_count,
        checkpoint_api_total   = coalesce(p_api_total, checkpoint_api_total)
    where id = p_snapshot_id;

    return v_actual_count;
end;
$$;

comment on function fn_ext037_save_page_checkpoint is
    'EXT-037 페이지 저장 + 체크포인트. runtime FOR UPDATE → run 검증 → snapshot FOR UPDATE + STAGING 검증. RUN_FENCED/SNAPSHOT_NOT_STAGING 예외로 차단.';

-- ============================================================
-- GAP-D/R3-03: 원자적 스냅샷 완결 RPC
-- PATCH-002-02: is_current 해제 순서 수정 — 기존 현행판 해제 FIRST, 신규 승격 SECOND
-- ============================================================
create or replace function fn_ext037_complete_snapshot(
    p_snapshot_id   uuid,
    p_source_id     text,
    p_total_items   int,
    p_content_hash  text,
    p_run_id        uuid    -- R3-03: 실행 소유권 검증용
) returns boolean
language plpgsql
security invoker
as $$
declare
    v_actual_count      int;
    v_updated           int;
    v_current_run       uuid;
    v_run_status        text;
    v_lease_until       timestamptz;
    v_snap_status       text;
    v_snap_source_id    text;
    v_checkpoint_api    int;
begin
    -- runtime FOR UPDATE FIRST — deadlock 방지
    select current_run_id into v_current_run
    from public_data_source_runtime
    where source_id = p_source_id
    for update;

    if v_current_run is null or v_current_run::text != p_run_id::text then
        return false;
    end if;

    -- Run이 RUNNING 상태이고 lease가 유효한지 확인
    select status, lease_until into v_run_status, v_lease_until
    from public_data_sync_runs
    where id = p_run_id;

    if not found or v_run_status != 'RUNNING' or v_lease_until <= now() then
        return false;
    end if;

    -- snapshot FOR UPDATE 잠금 — DML 전 상태 고정
    select status, source_id, checkpoint_api_total
    into v_snap_status, v_snap_source_id, v_checkpoint_api
    from ext037_chemical_safety_snapshots
    where id = p_snapshot_id
    for update;

    if not found or v_snap_status != 'STAGING' or v_snap_source_id != p_source_id then
        return false;
    end if;

    -- 1. 실제 아이템 수 검증
    select count(*) into v_actual_count
    from ext037_chemical_safety_snapshot_items
    where snapshot_id = p_snapshot_id;

    if v_actual_count <> p_total_items then
        return false;
    end if;

    -- REPAIR-B: checkpoint_api_total NULL → 수집 증거 없음 → 승격 차단 (fail-closed)
    if v_checkpoint_api is null then
        return false;
    end if;

    -- checkpoint_api_total 교차 검증 — DB count와 일치해야 승격 허용
    if v_actual_count <> v_checkpoint_api then
        return false;
    end if;

    -- STEP 1: 기존 현행판 is_current 해제 FIRST (unique index 충돌 방지)
    update ext037_chemical_safety_snapshots
    set is_current = false
    where source_id  = p_source_id
      and status     = 'COMPLETED'
      and is_current = true
      and id        != p_snapshot_id;

    -- STEP 2: STAGING → COMPLETED + 현행판 지정
    update ext037_chemical_safety_snapshots
    set
        status        = 'COMPLETED',
        total_fetched = p_total_items,
        content_hash  = p_content_hash,
        completed_at  = now(),
        is_current    = true
    where id        = p_snapshot_id
      and source_id = p_source_id
      and status    = 'STAGING';

    get diagnostics v_updated = row_count;

    if v_updated != 1 then
        raise exception 'PROMOTE_FAILED: snapshot % promotion returned % rows (expected 1)',
            p_snapshot_id, v_updated;
    end if;

    return true;
end;
$$;

comment on function fn_ext037_complete_snapshot is
    'EXT-037 스냅샷 원자적 완결. runtime FOR UPDATE → snapshot FOR UPDATE + STAGING 검증 → checkpoint_api_total NULL 차단 → count 검증 → is_current 해제 → COMPLETED 승격. PROMOTE_FAILED 예외로 롤백 보장.';

-- ============================================================
-- fn_ext037_fail_snapshot — Run 소유권 + RUNNING/Lease 검증 + STAGING guard
-- lock 순서: runtime FOR UPDATE → snapshot FOR UPDATE (deadlock 방지)
-- ============================================================
create or replace function fn_ext037_fail_snapshot(
    p_snapshot_id   uuid,
    p_run_id        uuid,
    p_error_message text
) returns boolean
language plpgsql
security invoker
as $$
declare
    v_source_id     text;
    v_current_run   uuid;
    v_run_status    text;
    v_lease_until   timestamptz;
    v_snap_status   text;
begin
    -- source_id 조회 (잠금 전)
    select source_id into v_source_id
    from ext037_chemical_safety_snapshots
    where id = p_snapshot_id;

    if not found then
        return false;
    end if;

    -- lock 순서 1: runtime FOR UPDATE FIRST (deadlock 방지)
    select current_run_id into v_current_run
    from public_data_source_runtime
    where source_id = v_source_id
    for update;

    if v_current_run is null or v_current_run::text != p_run_id::text then
        return false;
    end if;

    -- Run 존재·RUNNING 상태·Lease 유효성 검증
    select status, lease_until into v_run_status, v_lease_until
    from public_data_sync_runs
    where id = p_run_id;

    if not found then
        return false;
    end if;

    if v_run_status != 'RUNNING' then
        return false;
    end if;

    if v_lease_until <= clock_timestamp() then
        return false;
    end if;

    -- lock 순서 2: snapshot FOR UPDATE SECOND
    select status into v_snap_status
    from ext037_chemical_safety_snapshots
    where id = p_snapshot_id
    for update;

    if v_snap_status != 'STAGING' then
        return false;
    end if;

    update ext037_chemical_safety_snapshots
    set
        status        = 'FAILED',
        error_message = left(p_error_message, 500),
        completed_at  = now()
    where id = p_snapshot_id;

    return true;
end;
$$;

comment on function fn_ext037_fail_snapshot is
    'EXT-037 스냅샷 실패 마킹. runtime FOR UPDATE → Run RUNNING/Lease 검증 → snapshot FOR UPDATE + STAGING 검증. 모든 조건 미충족 시 false 반환(예외 없음).';

-- ============================================================
-- R3-01: public_data_source_runtime seed 행 (is_enabled=false)
-- MANUAL 실행에서 fn_public_data_claim_run이 이 행을 조회한다.
-- ============================================================
insert into public_data_source_runtime (source_id, is_enabled)
values ('EXT037_CHEMICAL_SAFETY', false)
on conflict (source_id) do nothing;

-- ============================================================
-- RLS: 서비스롤 전용 (공개 접근 차단)
-- ============================================================
alter table ext037_chemical_safety_snapshots enable row level security;
alter table ext037_chemical_safety_snapshot_items enable row level security;

create policy "service_role_all_ext037_snapshots"
    on ext037_chemical_safety_snapshots
    for all
    to service_role
    using (true)
    with check (true);

create policy "service_role_all_ext037_items"
    on ext037_chemical_safety_snapshot_items
    for all
    to service_role
    using (true)
    with check (true);
