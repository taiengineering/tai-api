-- DRAFT — NOT APPLIED TO PRODUCTION
-- EXT-165 화학물질안전원 화학사고 스냅샷 기반 스토리지 (WO-001B-R3 + PATCH-001 + PATCH-002)
-- GAP-B: source_id + checkpoint 필드
-- GAP-D/R3-03: fn_ext165_complete_snapshot — run 소유권 검증 + 원자적 승격
-- PATCH-02: fn_ext165_save_page_checkpoint — 원자적 페이지 저장 + 체크포인트
-- PATCH-04: is_current 열 — 단일 현행판 포인터, fn_ext165_complete_snapshot 원자적 전환
-- PATCH-002-02: fn_ext165_complete_snapshot — is_current 해제 순서 수정 (기존 현행판 해제 FIRST)
-- PATCH-002-04: FOR UPDATE 잠금 — 쓰기 단계 동시 접근 차단
-- PATCH-002-06: collect_scope 열 — 연도별 수집 결과를 전체 현행판으로 승격하지 않음
--               collect_scope IS NOT NULL → is_current = false (연도별 부분 스냅샷)
--               collect_scope IS NULL     → is_current = true  (전체수집 현행판)
-- R3-01: public_data_source_runtime seed 행 (is_enabled=false)
-- Apply only after: sample API call verified, Owner approval obtained

-- ============================================================
-- 스냅샷 헤더 테이블
-- ============================================================
create table if not exists ext165_chemical_accident_snapshots (
    id                      uuid        primary key default gen_random_uuid(),
    run_id                  text        not null,
    source_id               text        not null default 'EXT165_CHEMICAL_ACCIDENT',
    status                  text        not null default 'STAGING'
                                        check (status in ('STAGING', 'COMPLETED', 'FAILED')),
    total_fetched           int,
    content_hash            text,
    error_message           text,
    -- GAP-B: 체크포인트 필드
    last_page_no            int         not null default 0,
    checkpoint_total_count  int,
    checkpoint_api_total    int,
    -- PATCH-04: 단일 현행판 포인터 (fn_ext165_complete_snapshot이 원자적으로 전환)
    is_current              boolean     not null default false,
    -- PATCH-002-06: 연도별 수집 범위 식별 (NULL=전체수집, '2024'=연도별)
    collect_scope           text,
    created_at              timestamptz not null default now(),
    completed_at            timestamptz
);

comment on table ext165_chemical_accident_snapshots is
    'EXT-165 화학물질안전원 화학사고 수집 스냅샷. STAGING→COMPLETED 원자적 프로모션. collect_scope NULL=전체/NOT NULL=연도별(is_current=false).';

-- GAP-D/PATCH-002-06: source_id+collect_scope 당 STAGING 스냅샷 하나만 허용
-- coalesce(collect_scope, '')로 NULL과 값 구분 → 전체/연도별 STAGING 동시 허용
create unique index if not exists uidx_ext165_snapshots_one_staging
    on ext165_chemical_accident_snapshots (source_id, coalesce(collect_scope, ''))
    where status = 'STAGING';

-- status 인덱스 (COMPLETED 최신 조회용)
create index if not exists idx_ext165_snapshots_status_completed_at
    on ext165_chemical_accident_snapshots (status, completed_at desc);

-- PATCH-04: source_id 당 is_current=true 스냅샷 최대 1개 강제 (DB 수준 불변식)
-- 연도별 스냅샷(collect_scope IS NOT NULL)은 is_current=false이므로 이 인덱스에 포함되지 않음
create unique index if not exists uidx_ext165_snapshots_one_current
    on ext165_chemical_accident_snapshots (source_id)
    where is_current = true;

-- ============================================================
-- 스냅샷 아이템 테이블
-- ============================================================
create table if not exists ext165_chemical_accident_snapshot_items (
    id              bigserial   primary key,
    snapshot_id     uuid        not null references ext165_chemical_accident_snapshots(id) on delete cascade,
    datano          text        not null,   -- 원본 source key (XML 필드명 UNVERIFIED)
    raw             jsonb       not null default '{}',
    created_at      timestamptz not null default now(),

    unique (snapshot_id, datano)
);

comment on table ext165_chemical_accident_snapshot_items is
    'EXT-165 스냅샷별 화학사고 레코드. datano는 UNVERIFIED — 실 API 응답 확인 후 확정.';

create index if not exists idx_ext165_items_snapshot_id
    on ext165_chemical_accident_snapshot_items (snapshot_id);

-- ============================================================
-- PATCH-02/PATCH-002-04: 원자적 페이지 저장 + 체크포인트 RPC
-- ============================================================
create or replace function fn_ext165_save_page_checkpoint(
    p_snapshot_id   uuid,
    p_items         jsonb,      -- array of {datano: text, raw: object}
    p_page_no       int,
    p_api_total     int,        -- nullable
    p_run_id        uuid        -- PATCH-03: 쓰기 전 소유권 + Lease 검증용
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
    -- PATCH-03-A: 스냅샷의 source_id 조회 (잠금 전 source_id 확보)
    select source_id into v_source_id
    from ext165_chemical_accident_snapshots
    where id = p_snapshot_id;

    if not found then
        raise exception 'RUN_FENCED: snapshot % not found', p_snapshot_id;
    end if;

    -- PATCH-002-04/PATCH-003: runtime FOR UPDATE FIRST — deadlock 방지
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

    -- PATCH-003-04: snapshot FOR UPDATE 잠금 + STAGING 상태 검증 (COMPLETED/FAILED 쓰기 차단)
    select status into v_snap_status
    from ext165_chemical_accident_snapshots
    where id = p_snapshot_id
    for update;

    if v_snap_status != 'STAGING' then
        raise exception 'SNAPSHOT_NOT_STAGING: snapshot % has status=%, expected STAGING',
            p_snapshot_id, v_snap_status;
    end if;

    -- 소유권 + 상태 확인 완료 — 페이지 저장 + 체크포인트 갱신 (이하 단일 트랜잭션)

    -- 1. upsert items (snapshot_id,datano on_conflict)
    for v_item in select * from jsonb_array_elements(p_items)
    loop
        insert into ext165_chemical_accident_snapshot_items
            (snapshot_id, datano, raw, created_at)
        values
            (p_snapshot_id, v_item->>'datano', coalesce(v_item->'raw', '{}'), now())
        on conflict (snapshot_id, datano) do update
            set raw = excluded.raw;
    end loop;

    -- 2. actual DB unique item count (idempotent — re-run safe)
    select count(*) into v_actual_count
    from ext165_chemical_accident_snapshot_items
    where snapshot_id = p_snapshot_id;

    -- 3. checkpoint UPDATE
    update ext165_chemical_accident_snapshots
    set
        last_page_no           = p_page_no,
        checkpoint_total_count = v_actual_count,
        checkpoint_api_total   = coalesce(p_api_total, checkpoint_api_total)
    where id = p_snapshot_id;

    return v_actual_count;
end;
$$;

comment on function fn_ext165_save_page_checkpoint is
    'PATCH-02/03/PATCH-002-04/PATCH-003-04: EXT-165 페이지 저장 + 체크포인트. runtime FOR UPDATE → run 검증 → snapshot FOR UPDATE + STAGING 검증. RUN_FENCED/SNAPSHOT_NOT_STAGING 예외로 차단.';

-- ============================================================
-- GAP-D/R3-03/PATCH-002-02/04/06: 원자적 스냅샷 완결 RPC
-- PATCH-002-02: is_current 해제 순서 수정 — 기존 현행판 해제 FIRST, 신규 승격 SECOND
--               (기존 순서는 unique index 위반 발생)
-- PATCH-002-04: FOR UPDATE 잠금 — 승격 과정 동시 접근 차단
-- PATCH-002-06: collect_scope IS NOT NULL → is_current = false (연도별 부분 스냅샷)
--               collect_scope IS NULL     → is_current = true  (전체수집 현행판)
-- ============================================================
create or replace function fn_ext165_complete_snapshot(
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
    v_collect_scope     text;
    v_snap_status       text;
    v_snap_source_id    text;
    v_checkpoint_api    int;
begin
    -- PATCH-002-04/PATCH-003: runtime FOR UPDATE FIRST — deadlock 방지
    select current_run_id into v_current_run
    from public_data_source_runtime
    where source_id = p_source_id
    for update;

    if v_current_run is null or v_current_run::text != p_run_id::text then
        return false;  -- 소유권 없음 또는 다른 Run이 선점
    end if;

    -- R3-03-2: Run이 RUNNING 상태이고 lease가 유효한지 확인
    select status, lease_until into v_run_status, v_lease_until
    from public_data_sync_runs
    where id = p_run_id;

    if not found or v_run_status != 'RUNNING' or v_lease_until <= now() then
        return false;  -- Run이 없거나 만료됨
    end if;

    -- PATCH-003-01: snapshot FOR UPDATE 잠금 — DML 전 상태 고정 + 원자성 보장
    -- STAGING + source_id 검증: 실패 시 어떤 DML도 실행되지 않으므로 안전하게 return false
    -- collect_scope도 여기서 조회하여 별도 SELECT 제거 (PATCH-002-06)
    select status, source_id, checkpoint_api_total, collect_scope
    into v_snap_status, v_snap_source_id, v_checkpoint_api, v_collect_scope
    from ext165_chemical_accident_snapshots
    where id = p_snapshot_id
    for update;

    if not found or v_snap_status != 'STAGING' or v_snap_source_id != p_source_id then
        return false;
    end if;

    -- 1. 실제 아이템 수 검증
    select count(*) into v_actual_count
    from ext165_chemical_accident_snapshot_items
    where snapshot_id = p_snapshot_id;

    if v_actual_count <> p_total_items then
        return false;
    end if;

    -- REPAIR-B: checkpoint_api_total NULL → 수집 증거 없음 → 승격 차단 (fail-closed)
    if v_checkpoint_api is null then
        return false;
    end if;

    -- PATCH-003-02: checkpoint_api_total 교차 검증 — DB count와 일치해야 승격 허용
    if v_actual_count <> v_checkpoint_api then
        return false;
    end if;

    -- STEP 1: 기존 현행판 is_current 해제 FIRST (unique index 충돌 방지)
    -- 연도별 스냅샷(v_collect_scope IS NOT NULL)은 is_current=false이므로 해제 불필요.
    -- FOR UPDATE 잠금 후 이 DML이 실행됨.
    -- STEP 2가 실패하면 RAISE EXCEPTION으로 전체 트랜잭션 롤백 → is_current 해제도 롤백됨.
    if v_collect_scope is null then
        update ext165_chemical_accident_snapshots
        set is_current = false
        where source_id  = p_source_id
          and status     = 'COMPLETED'
          and is_current = true
          and id        != p_snapshot_id;
    end if;

    -- STEP 2: STAGING → COMPLETED + 현행판 지정
    -- PATCH-002-06: is_current = (v_collect_scope IS NULL)
    --   전체수집(NULL) = 현행판(true), 연도별(NOT NULL) = 부분 스냅샷(false)
    -- run_id 조건 제거: 소유권은 위 public_data_source_runtime 검증으로 확인됨.
    -- Resume 시 새 run_id가 snapshot.run_id(원래 run)와 달라도 승격 가능.
    update ext165_chemical_accident_snapshots
    set
        status        = 'COMPLETED',
        total_fetched = p_total_items,
        content_hash  = p_content_hash,
        completed_at  = now(),
        is_current    = (v_collect_scope is null)
    where id        = p_snapshot_id
      and source_id = p_source_id
      and status    = 'STAGING';

    get diagnostics v_updated = row_count;

    if v_updated != 1 then
        -- FOR UPDATE 잠금 후에도 0행이면 내부 버그 — RAISE로 전체 트랜잭션 롤백
        -- STEP 1의 is_current=false 해제도 롤백되어 기존 현행판이 보존됨
        raise exception 'PROMOTE_FAILED: snapshot % promotion returned % rows (expected 1)',
            p_snapshot_id, v_updated;
    end if;

    return true;
end;
$$;

comment on function fn_ext165_complete_snapshot is
    'GAP-D/R3-03/PATCH-04/PATCH-002-02/04/06/PATCH-003-01/02/REPAIR-B: EXT-165 스냅샷 원자적 완결. runtime FOR UPDATE → snapshot FOR UPDATE + STAGING 검증 → checkpoint_api_total NULL 차단(REPAIR-B) → count 검증 → is_current 해제(STEP1) → COMPLETED 승격(STEP2). PROMOTE_FAILED 예외로 롤백 보장.';

-- ============================================================
-- REPAIR-A/002: fn_ext165_fail_snapshot — Run 소유권 + RUNNING/Lease 검증 + STAGING guard
-- lock 순서: runtime FOR UPDATE → (Run 검증) → snapshot FOR UPDATE (deadlock 방지)
-- ============================================================
create or replace function fn_ext165_fail_snapshot(
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
    from ext165_chemical_accident_snapshots
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
        return false;  -- 소유권 없음
    end if;

    -- REPAIR-002: Run 존재·RUNNING 상태·Lease 유효성 검증
    -- clock_timestamp() 사용: 잠금 대기 중 경과 시간 반영 (now()는 트랜잭션 시작 시각)
    select status, lease_until into v_run_status, v_lease_until
    from public_data_sync_runs
    where id = p_run_id;

    if not found then
        return false;  -- Run 행 없음
    end if;

    if v_run_status != 'RUNNING' then
        return false;  -- Run이 RUNNING 상태 아님 (FAILED/COMPLETED 등)
    end if;

    if v_lease_until <= clock_timestamp() then
        return false;  -- Lease 만료 (잠금 대기 중 경과 포함)
    end if;

    -- lock 순서 2: snapshot FOR UPDATE SECOND
    select status into v_snap_status
    from ext165_chemical_accident_snapshots
    where id = p_snapshot_id
    for update;

    if v_snap_status != 'STAGING' then
        return false;  -- STAGING 아닌 스냅샷 덮어쓰기 차단
    end if;

    update ext165_chemical_accident_snapshots
    set
        status        = 'FAILED',
        error_message = left(p_error_message, 500),
        completed_at  = now()
    where id = p_snapshot_id;

    return true;
end;
$$;

comment on function fn_ext165_fail_snapshot is
    'REPAIR-A/002: EXT-165 스냅샷 실패 마킹. runtime FOR UPDATE → Run RUNNING/Lease 검증(REPAIR-002) → snapshot FOR UPDATE + STAGING 검증. 모든 조건 미충족 시 false 반환(예외 없음).';

-- ============================================================
-- R3-01: public_data_source_runtime seed 행 (is_enabled=false)
-- MANUAL 실행에서 fn_public_data_claim_run이 이 행을 조회한다.
-- ============================================================
insert into public_data_source_runtime (source_id, is_enabled)
values ('EXT165_CHEMICAL_ACCIDENT', false)
on conflict (source_id) do nothing;

-- ============================================================
-- RLS: 서비스롤 전용 (공개 접근 차단)
-- ============================================================
alter table ext165_chemical_accident_snapshots enable row level security;
alter table ext165_chemical_accident_snapshot_items enable row level security;

create policy "service_role_all_ext165_snapshots"
    on ext165_chemical_accident_snapshots
    for all
    to service_role
    using (true)
    with check (true);

create policy "service_role_all_ext165_items"
    on ext165_chemical_accident_snapshot_items
    for all
    to service_role
    using (true)
    with check (true);
