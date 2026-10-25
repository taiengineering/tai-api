-- WO-TAI-SEC-SEARCHPATH-REM97-CW3-SOURCE-001
-- CW3 격리 환경 설정: EXT037 + EXT132 + EXT165 ext snapshot 9개 함수
-- Run BEFORE run_cw3_regression.sql

SET search_path = public;

-- ─── ROLES ───────────────────────────────────────────────────────────────────
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role BYPASSRLS NOLOGIN;
  END IF;
END;
$$;

GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;

-- ─── 공통 테이블 ─────────────────────────────────────────────────────────────
CREATE TABLE public.public_data_source_runtime (
  source_id      text PRIMARY KEY,
  current_run_id uuid
);

CREATE TABLE public.public_data_sync_runs (
  id          uuid        PRIMARY KEY,
  status      text        NOT NULL,
  lease_until timestamptz NOT NULL
);

-- ─── EXT037 테이블 ───────────────────────────────────────────────────────────
CREATE TABLE public.ext037_chemical_safety_snapshots (
  id                       uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id                text        NOT NULL,
  status                   text        NOT NULL DEFAULT 'STAGING',
  is_current               boolean     NOT NULL DEFAULT false,
  total_fetched            integer,
  content_hash             text,
  completed_at             timestamptz,
  error_message            text,
  checkpoint_api_total     integer,
  last_page_no             integer,
  checkpoint_total_count   integer
);

CREATE TABLE public.ext037_chemical_safety_snapshot_items (
  snapshot_id  uuid        NOT NULL,
  datano       text        NOT NULL,
  raw          jsonb       NOT NULL DEFAULT '{}',
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE(snapshot_id, datano)
);

-- ─── EXT132 테이블 ───────────────────────────────────────────────────────────
CREATE TABLE public.ext132_hazardous_material_snapshots (
  id                       uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id                text        NOT NULL,
  status                   text        NOT NULL DEFAULT 'STAGING',
  is_current               boolean     NOT NULL DEFAULT false,
  total_fetched            integer,
  content_hash             text,
  completed_at             timestamptz,
  error_message            text,
  checkpoint_api_total     integer,
  last_page_no             integer,
  checkpoint_total_count   integer
);

CREATE TABLE public.ext132_hazardous_material_snapshot_items (
  snapshot_id  uuid        NOT NULL,
  chemicalno   text        NOT NULL,
  raw          jsonb       NOT NULL DEFAULT '{}',
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE(snapshot_id, chemicalno)
);

-- ─── EXT165 테이블 ───────────────────────────────────────────────────────────
CREATE TABLE public.ext165_chemical_accident_snapshots (
  id                       uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id                text        NOT NULL,
  status                   text        NOT NULL DEFAULT 'STAGING',
  is_current               boolean     NOT NULL DEFAULT false,
  total_fetched            integer,
  content_hash             text,
  completed_at             timestamptz,
  error_message            text,
  checkpoint_api_total     integer,
  last_page_no             integer,
  checkpoint_total_count   integer,
  collect_scope            text
);

CREATE TABLE public.ext165_chemical_accident_snapshot_items (
  snapshot_id  uuid        NOT NULL,
  datano       text        NOT NULL,
  raw          jsonb       NOT NULL DEFAULT '{}',
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE(snapshot_id, datano)
);

-- ─── 9개 함수 생성 (proconfig=NULL — 운영 기준선 재현) ─────────────────────────
-- prosrc는 운영 DB에서 직접 추출한 값과 동일하게 유지

-- ── EXT037: fn_ext037_save_page_checkpoint ──────────────────────────────────
CREATE OR REPLACE FUNCTION public.fn_ext037_save_page_checkpoint(
  p_snapshot_id uuid,
  p_items       jsonb,
  p_page_no     integer,
  p_api_total   integer,
  p_run_id      uuid
)
RETURNS integer
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $$
declare
    v_item          jsonb;
    v_actual_count  int;
    v_source_id     text;
    v_current_run   uuid;
    v_run_status    text;
    v_lease_until   timestamptz;
    v_snap_status   text;
begin
    select source_id into v_source_id
    from ext037_chemical_safety_snapshots
    where id = p_snapshot_id;
    if not found then
        raise exception 'RUN_FENCED: snapshot % not found', p_snapshot_id;
    end if;
    select current_run_id into v_current_run
    from public_data_source_runtime
    where source_id = v_source_id
    for update;
    if v_current_run is null or v_current_run::text != p_run_id::text then
        raise exception 'RUN_FENCED: run_id=% is not current owner of source=%', p_run_id, v_source_id;
    end if;
    select status, lease_until into v_run_status, v_lease_until
    from public_data_sync_runs
    where id = p_run_id;
    if not found or v_run_status != 'RUNNING' or v_lease_until <= now() then
        raise exception 'RUN_FENCED: run_id=% is not RUNNING or lease expired', p_run_id;
    end if;
    select status into v_snap_status
    from ext037_chemical_safety_snapshots
    where id = p_snapshot_id
    for update;
    if v_snap_status != 'STAGING' then
        raise exception 'SNAPSHOT_NOT_STAGING: snapshot % has status=%, expected STAGING',
            p_snapshot_id, v_snap_status;
    end if;
    for v_item in select * from jsonb_array_elements(p_items)
    loop
        insert into ext037_chemical_safety_snapshot_items
            (snapshot_id, datano, raw, created_at)
        values
            (p_snapshot_id, v_item->>'datano', coalesce(v_item->'raw', '{}'), now())
        on conflict (snapshot_id, datano) do update
            set raw = excluded.raw;
    end loop;
    select count(*) into v_actual_count
    from ext037_chemical_safety_snapshot_items
    where snapshot_id = p_snapshot_id;
    update ext037_chemical_safety_snapshots
    set
        last_page_no           = p_page_no,
        checkpoint_total_count = v_actual_count,
        checkpoint_api_total   = coalesce(p_api_total, checkpoint_api_total)
    where id = p_snapshot_id;
    return v_actual_count;
end;
$$;

-- ── EXT037: fn_ext037_complete_snapshot ─────────────────────────────────────
CREATE OR REPLACE FUNCTION public.fn_ext037_complete_snapshot(
  p_snapshot_id  uuid,
  p_source_id    text,
  p_total_items  integer,
  p_content_hash text,
  p_run_id       uuid
)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $$
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
    select current_run_id into v_current_run
    from public_data_source_runtime
    where source_id = p_source_id
    for update;
    if v_current_run is null or v_current_run::text != p_run_id::text then
        return false;
    end if;
    select status, lease_until into v_run_status, v_lease_until
    from public_data_sync_runs
    where id = p_run_id;
    if not found or v_run_status != 'RUNNING' or v_lease_until <= now() then
        return false;
    end if;
    select status, source_id, checkpoint_api_total
    into v_snap_status, v_snap_source_id, v_checkpoint_api
    from ext037_chemical_safety_snapshots
    where id = p_snapshot_id
    for update;
    if not found or v_snap_status != 'STAGING' or v_snap_source_id != p_source_id then
        return false;
    end if;
    select count(*) into v_actual_count
    from ext037_chemical_safety_snapshot_items
    where snapshot_id = p_snapshot_id;
    if v_actual_count <> p_total_items then
        return false;
    end if;
    if v_checkpoint_api is null then
        return false;
    end if;
    if v_actual_count <> v_checkpoint_api then
        return false;
    end if;
    update ext037_chemical_safety_snapshots
    set is_current = false
    where source_id  = p_source_id
      and status     = 'COMPLETED'
      and is_current = true
      and id        != p_snapshot_id;
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

-- ── EXT037: fn_ext037_fail_snapshot ─────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.fn_ext037_fail_snapshot(
  p_snapshot_id   uuid,
  p_run_id        uuid,
  p_error_message text
)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $$
declare
    v_source_id     text;
    v_current_run   uuid;
    v_run_status    text;
    v_lease_until   timestamptz;
    v_snap_status   text;
begin
    select source_id into v_source_id
    from ext037_chemical_safety_snapshots
    where id = p_snapshot_id;
    if not found then
        return false;
    end if;
    select current_run_id into v_current_run
    from public_data_source_runtime
    where source_id = v_source_id
    for update;
    if v_current_run is null or v_current_run::text != p_run_id::text then
        return false;
    end if;
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

-- ── EXT132: fn_ext132_save_page_checkpoint ──────────────────────────────────
CREATE OR REPLACE FUNCTION public.fn_ext132_save_page_checkpoint(
  p_snapshot_id uuid,
  p_items       jsonb,
  p_page_no     integer,
  p_api_total   integer,
  p_run_id      uuid
)
RETURNS integer
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $$
declare
    v_item          jsonb;
    v_actual_count  int;
    v_source_id     text;
    v_current_run   uuid;
    v_run_status    text;
    v_lease_until   timestamptz;
    v_snap_status   text;
begin
    select source_id into v_source_id
    from ext132_hazardous_material_snapshots
    where id = p_snapshot_id;
    if not found then
        raise exception 'RUN_FENCED: snapshot % not found', p_snapshot_id;
    end if;
    select current_run_id into v_current_run
    from public_data_source_runtime
    where source_id = v_source_id
    for update;
    if v_current_run is null or v_current_run::text != p_run_id::text then
        raise exception 'RUN_FENCED: run_id=% is not current owner of source=%', p_run_id, v_source_id;
    end if;
    select status, lease_until into v_run_status, v_lease_until
    from public_data_sync_runs
    where id = p_run_id;
    if not found or v_run_status != 'RUNNING' or v_lease_until <= now() then
        raise exception 'RUN_FENCED: run_id=% is not RUNNING or lease expired', p_run_id;
    end if;
    select status into v_snap_status
    from ext132_hazardous_material_snapshots
    where id = p_snapshot_id
    for update;
    if v_snap_status != 'STAGING' then
        raise exception 'SNAPSHOT_NOT_STAGING: snapshot % has status=%, expected STAGING',
            p_snapshot_id, v_snap_status;
    end if;
    for v_item in select * from jsonb_array_elements(p_items)
    loop
        insert into ext132_hazardous_material_snapshot_items
            (snapshot_id, chemicalno, raw, created_at)
        values
            (p_snapshot_id, v_item->>'chemicalno', coalesce(v_item->'raw', '{}'), now())
        on conflict (snapshot_id, chemicalno) do update
            set raw = excluded.raw;
    end loop;
    select count(*) into v_actual_count
    from ext132_hazardous_material_snapshot_items
    where snapshot_id = p_snapshot_id;
    update ext132_hazardous_material_snapshots
    set
        last_page_no           = p_page_no,
        checkpoint_total_count = v_actual_count,
        checkpoint_api_total   = coalesce(p_api_total, checkpoint_api_total)
    where id = p_snapshot_id;
    return v_actual_count;
end;
$$;

-- ── EXT132: fn_ext132_complete_snapshot ─────────────────────────────────────
CREATE OR REPLACE FUNCTION public.fn_ext132_complete_snapshot(
  p_snapshot_id  uuid,
  p_source_id    text,
  p_total_items  integer,
  p_content_hash text,
  p_run_id       uuid
)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $$
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
    select current_run_id into v_current_run
    from public_data_source_runtime
    where source_id = p_source_id
    for update;
    if v_current_run is null or v_current_run::text != p_run_id::text then
        return false;
    end if;
    select status, lease_until into v_run_status, v_lease_until
    from public_data_sync_runs
    where id = p_run_id;
    if not found or v_run_status != 'RUNNING' or v_lease_until <= now() then
        return false;
    end if;
    select status, source_id, checkpoint_api_total
    into v_snap_status, v_snap_source_id, v_checkpoint_api
    from ext132_hazardous_material_snapshots
    where id = p_snapshot_id
    for update;
    if not found or v_snap_status != 'STAGING' or v_snap_source_id != p_source_id then
        return false;
    end if;
    select count(*) into v_actual_count
    from ext132_hazardous_material_snapshot_items
    where snapshot_id = p_snapshot_id;
    if v_actual_count <> p_total_items then
        return false;
    end if;
    if v_checkpoint_api is null then
        return false;
    end if;
    if v_actual_count <> v_checkpoint_api then
        return false;
    end if;
    update ext132_hazardous_material_snapshots
    set is_current = false
    where source_id  = p_source_id
      and status     = 'COMPLETED'
      and is_current = true
      and id        != p_snapshot_id;
    update ext132_hazardous_material_snapshots
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

-- ── EXT132: fn_ext132_fail_snapshot ─────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.fn_ext132_fail_snapshot(
  p_snapshot_id   uuid,
  p_run_id        uuid,
  p_error_message text
)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $$
declare
    v_source_id     text;
    v_current_run   uuid;
    v_run_status    text;
    v_lease_until   timestamptz;
    v_snap_status   text;
begin
    select source_id into v_source_id
    from ext132_hazardous_material_snapshots
    where id = p_snapshot_id;
    if not found then
        return false;
    end if;
    select current_run_id into v_current_run
    from public_data_source_runtime
    where source_id = v_source_id
    for update;
    if v_current_run is null or v_current_run::text != p_run_id::text then
        return false;
    end if;
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
    select status into v_snap_status
    from ext132_hazardous_material_snapshots
    where id = p_snapshot_id
    for update;
    if v_snap_status != 'STAGING' then
        return false;
    end if;
    update ext132_hazardous_material_snapshots
    set
        status        = 'FAILED',
        error_message = left(p_error_message, 500),
        completed_at  = now()
    where id = p_snapshot_id;
    return true;
end;
$$;

-- ── EXT165: fn_ext165_save_page_checkpoint ──────────────────────────────────
CREATE OR REPLACE FUNCTION public.fn_ext165_save_page_checkpoint(
  p_snapshot_id uuid,
  p_items       jsonb,
  p_page_no     integer,
  p_api_total   integer,
  p_run_id      uuid
)
RETURNS integer
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $$
declare
    v_item          jsonb;
    v_actual_count  int;
    v_source_id     text;
    v_current_run   uuid;
    v_run_status    text;
    v_lease_until   timestamptz;
    v_snap_status   text;
begin
    select source_id into v_source_id
    from ext165_chemical_accident_snapshots
    where id = p_snapshot_id;
    if not found then
        raise exception 'RUN_FENCED: snapshot % not found', p_snapshot_id;
    end if;
    select current_run_id into v_current_run
    from public_data_source_runtime
    where source_id = v_source_id
    for update;
    if v_current_run is null or v_current_run::text != p_run_id::text then
        raise exception 'RUN_FENCED: run_id=% is not current owner of source=%', p_run_id, v_source_id;
    end if;
    select status, lease_until into v_run_status, v_lease_until
    from public_data_sync_runs
    where id = p_run_id;
    if not found or v_run_status != 'RUNNING' or v_lease_until <= now() then
        raise exception 'RUN_FENCED: run_id=% is not RUNNING or lease expired', p_run_id;
    end if;
    select status into v_snap_status
    from ext165_chemical_accident_snapshots
    where id = p_snapshot_id
    for update;
    if v_snap_status != 'STAGING' then
        raise exception 'SNAPSHOT_NOT_STAGING: snapshot % has status=%, expected STAGING',
            p_snapshot_id, v_snap_status;
    end if;
    for v_item in select * from jsonb_array_elements(p_items)
    loop
        insert into ext165_chemical_accident_snapshot_items
            (snapshot_id, datano, raw, created_at)
        values
            (p_snapshot_id, v_item->>'datano', coalesce(v_item->'raw', '{}'), now())
        on conflict (snapshot_id, datano) do update
            set raw = excluded.raw;
    end loop;
    select count(*) into v_actual_count
    from ext165_chemical_accident_snapshot_items
    where snapshot_id = p_snapshot_id;
    update ext165_chemical_accident_snapshots
    set
        last_page_no           = p_page_no,
        checkpoint_total_count = v_actual_count,
        checkpoint_api_total   = coalesce(p_api_total, checkpoint_api_total)
    where id = p_snapshot_id;
    return v_actual_count;
end;
$$;

-- ── EXT165: fn_ext165_complete_snapshot ─────────────────────────────────────
CREATE OR REPLACE FUNCTION public.fn_ext165_complete_snapshot(
  p_snapshot_id  uuid,
  p_source_id    text,
  p_total_items  integer,
  p_content_hash text,
  p_run_id       uuid
)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $$
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
    select current_run_id into v_current_run
    from public_data_source_runtime
    where source_id = p_source_id
    for update;
    if v_current_run is null or v_current_run::text != p_run_id::text then
        return false;
    end if;
    select status, lease_until into v_run_status, v_lease_until
    from public_data_sync_runs
    where id = p_run_id;
    if not found or v_run_status != 'RUNNING' or v_lease_until <= now() then
        return false;
    end if;
    select status, source_id, checkpoint_api_total, collect_scope
    into v_snap_status, v_snap_source_id, v_checkpoint_api, v_collect_scope
    from ext165_chemical_accident_snapshots
    where id = p_snapshot_id
    for update;
    if not found or v_snap_status != 'STAGING' or v_snap_source_id != p_source_id then
        return false;
    end if;
    select count(*) into v_actual_count
    from ext165_chemical_accident_snapshot_items
    where snapshot_id = p_snapshot_id;
    if v_actual_count <> p_total_items then
        return false;
    end if;
    if v_checkpoint_api is null then
        return false;
    end if;
    if v_actual_count <> v_checkpoint_api then
        return false;
    end if;
    if v_collect_scope is null then
        update ext165_chemical_accident_snapshots
        set is_current = false
        where source_id  = p_source_id
          and status     = 'COMPLETED'
          and is_current = true
          and id        != p_snapshot_id;
    end if;
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
        raise exception 'PROMOTE_FAILED: snapshot % promotion returned % rows (expected 1)',
            p_snapshot_id, v_updated;
    end if;
    return true;
end;
$$;

-- ── EXT165: fn_ext165_fail_snapshot ─────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.fn_ext165_fail_snapshot(
  p_snapshot_id   uuid,
  p_run_id        uuid,
  p_error_message text
)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $$
declare
    v_source_id     text;
    v_current_run   uuid;
    v_run_status    text;
    v_lease_until   timestamptz;
    v_snap_status   text;
begin
    select source_id into v_source_id
    from ext165_chemical_accident_snapshots
    where id = p_snapshot_id;
    if not found then
        return false;
    end if;
    select current_run_id into v_current_run
    from public_data_source_runtime
    where source_id = v_source_id
    for update;
    if v_current_run is null or v_current_run::text != p_run_id::text then
        return false;
    end if;
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
    select status into v_snap_status
    from ext165_chemical_accident_snapshots
    where id = p_snapshot_id
    for update;
    if v_snap_status != 'STAGING' then
        return false;
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

-- ─── 권한: PUBLIC EXECUTE 박탈 후 service_role 전용 부여 ─────────────────────
REVOKE EXECUTE ON FUNCTION public.fn_ext037_save_page_checkpoint(uuid, jsonb, integer, integer, uuid) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.fn_ext037_complete_snapshot(uuid, text, integer, text, uuid) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.fn_ext037_fail_snapshot(uuid, uuid, text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.fn_ext132_save_page_checkpoint(uuid, jsonb, integer, integer, uuid) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.fn_ext132_complete_snapshot(uuid, text, integer, text, uuid) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.fn_ext132_fail_snapshot(uuid, uuid, text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.fn_ext165_save_page_checkpoint(uuid, jsonb, integer, integer, uuid) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.fn_ext165_complete_snapshot(uuid, text, integer, text, uuid) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.fn_ext165_fail_snapshot(uuid, uuid, text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.fn_ext037_save_page_checkpoint(uuid, jsonb, integer, integer, uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_ext037_complete_snapshot(uuid, text, integer, text, uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_ext037_fail_snapshot(uuid, uuid, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_ext132_save_page_checkpoint(uuid, jsonb, integer, integer, uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_ext132_complete_snapshot(uuid, text, integer, text, uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_ext132_fail_snapshot(uuid, uuid, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_ext165_save_page_checkpoint(uuid, jsonb, integer, integer, uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_ext165_complete_snapshot(uuid, text, integer, text, uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_ext165_fail_snapshot(uuid, uuid, text) TO service_role;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.public_data_source_runtime TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.public_data_sync_runs TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ext037_chemical_safety_snapshots TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ext037_chemical_safety_snapshot_items TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ext132_hazardous_material_snapshots TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ext132_hazardous_material_snapshot_items TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ext165_chemical_accident_snapshots TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ext165_chemical_accident_snapshot_items TO service_role;

-- ─── 설정 검증 ────────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_fn_count   int;
  v_bad_count  int;
  v_tbl_count  int;
  v_acl_count  int;
BEGIN
  -- 9개 함수 존재 확인
  SELECT COUNT(*) INTO v_fn_count
  FROM pg_proc
  WHERE proname IN (
    'fn_ext037_save_page_checkpoint', 'fn_ext037_complete_snapshot', 'fn_ext037_fail_snapshot',
    'fn_ext132_save_page_checkpoint', 'fn_ext132_complete_snapshot', 'fn_ext132_fail_snapshot',
    'fn_ext165_save_page_checkpoint', 'fn_ext165_complete_snapshot', 'fn_ext165_fail_snapshot'
  );
  IF v_fn_count IS DISTINCT FROM 9 THEN
    RAISE EXCEPTION 'SETUP FAILED: expected 9 functions, found %', v_fn_count;
  END IF;

  -- proconfig=NULL (기준선) 확인
  SELECT COUNT(*) INTO v_bad_count
  FROM pg_proc
  WHERE proname IN (
    'fn_ext037_save_page_checkpoint', 'fn_ext037_complete_snapshot', 'fn_ext037_fail_snapshot',
    'fn_ext132_save_page_checkpoint', 'fn_ext132_complete_snapshot', 'fn_ext132_fail_snapshot',
    'fn_ext165_save_page_checkpoint', 'fn_ext165_complete_snapshot', 'fn_ext165_fail_snapshot'
  ) AND proconfig IS NOT NULL;
  IF v_bad_count > 0 THEN
    RAISE EXCEPTION 'SETUP FAILED: % functions already have proconfig set', v_bad_count;
  END IF;

  -- 8개 테이블 존재 확인
  SELECT COUNT(*) INTO v_tbl_count
  FROM pg_tables
  WHERE schemaname = 'public'
    AND tablename IN (
      'public_data_source_runtime', 'public_data_sync_runs',
      'ext037_chemical_safety_snapshots', 'ext037_chemical_safety_snapshot_items',
      'ext132_hazardous_material_snapshots', 'ext132_hazardous_material_snapshot_items',
      'ext165_chemical_accident_snapshots', 'ext165_chemical_accident_snapshot_items'
    );
  IF v_tbl_count IS DISTINCT FROM 8 THEN
    RAISE EXCEPTION 'SETUP FAILED: expected 8 tables, found %', v_tbl_count;
  END IF;

  -- service_role EXECUTE 권한 확인 (9개)
  SELECT COUNT(*) INTO v_acl_count
  FROM pg_proc p
  JOIN pg_roles r ON r.rolname = 'service_role'
  WHERE p.proname IN (
    'fn_ext037_save_page_checkpoint', 'fn_ext037_complete_snapshot', 'fn_ext037_fail_snapshot',
    'fn_ext132_save_page_checkpoint', 'fn_ext132_complete_snapshot', 'fn_ext132_fail_snapshot',
    'fn_ext165_save_page_checkpoint', 'fn_ext165_complete_snapshot', 'fn_ext165_fail_snapshot'
  )
  AND EXISTS (
    SELECT 1
    FROM aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner)))
    WHERE grantee = r.oid
      AND privilege_type = 'EXECUTE'
  );
  IF v_acl_count IS DISTINCT FROM 9 THEN
    RAISE EXCEPTION 'SETUP FAILED: service_role EXECUTE granted on % of 9 functions (expected 9)', v_acl_count;
  END IF;

  RAISE NOTICE 'SETUP OK: 9 functions (proconfig=NULL) + 8 tables + roles + service_role ACL';
END;
$$;
