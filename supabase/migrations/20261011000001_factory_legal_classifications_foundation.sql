-- DRAFT — NOT APPLIED TO PRODUCTION
-- WO-TAI-SAAS-APP3-SECURE-API-LOCAL-IMPLEMENT-008 Deliverable A
-- public.factory_legal_classifications + public.factory_legal_classification_events
-- Service-role-only authority. RLS enabled. Trigger-based atomic audit.
-- NO APPLY: DB_PUSH_APPLY_MIGRATION = BLOCKED
-- Apply order: after public.factories table exists.
-- Rollback SQL: bottom of this file.

-- ============================================================
-- 1. factory_legal_classifications — 시설 별표3 분류 확인 현행판
--    factories 테이블에 민감 법적 정보를 추가하지 않는다 (별도 권한 테이블).
-- ============================================================
create table if not exists public.factory_legal_classifications (
    factory_id                  uuid        primary key
                                            references public.factories(id) on delete restrict,
    appendix3_item_no           int         not null
                                            constraint chk_flc_item_range
                                                check (appendix3_item_no >= 1 and appendix3_item_no <= 49),
    -- is_real_estate_management: item 37 전용. non-37이면 반드시 NULL.
    is_real_estate_management   boolean     null
                                            constraint chk_flc_subtype_non37_null
                                                check (appendix3_item_no = 37 or is_real_estate_management is null),
    appendix3_law_version_id    uuid        not null,
    -- confirmed_sector: 정규화된 섹터. BUILDING / INDUSTRIAL / CONSTRUCTION 만 허용.
    confirmed_sector            text        not null
                                            constraint chk_flc_sector
                                                check (confirmed_sector in ('BUILDING', 'INDUSTRIAL', 'CONSTRUCTION')),
    -- confirmed_by: 서버가 auth 토큰에서 추출한 user.id. 클라이언트가 직접 공급 불가.
    confirmed_by                uuid        not null,
    -- confirmed_at: 서버 시각. 클라이언트 시간 수용 금지.
    confirmed_at                timestamptz not null default now(),
    -- revision: CAS(비교-교환) 잠금. 업데이트 시 WHERE factory_id=X AND revision=expected.
    revision                    bigint      not null default 1
                                            constraint chk_flc_revision_positive
                                                check (revision >= 1)
);

comment on table public.factory_legal_classifications is
    'WO-008: 시설 별표3 분류 확인 현행판. service_role 전용. factories 테이블에 민감 법적 정보를 추가하지 않기 위해 별도 테이블로 분리.';

comment on column public.factory_legal_classifications.revision is
    'CAS 잠금 카운터. UPDATE 시 WHERE factory_id=X AND revision=expected 조건으로 충돌 검출.';

-- ============================================================
-- 2. factory_legal_classification_events — 감사 이벤트 (append-only)
-- ============================================================
create table if not exists public.factory_legal_classification_events (
    id                      uuid        primary key default gen_random_uuid(),
    factory_id              uuid        not null
                                        references public.factories(id) on delete restrict,
    event_type              text        not null
                                        constraint chk_flce_event_type
                                            check (event_type in ('INSERT', 'UPDATE')),
    actor_id                uuid        not null,
    occurred_at             timestamptz not null default now(),
    revision_before         bigint,
    revision_after          bigint      not null,
    item_no_before          int,
    item_no_after           int         not null,
    subtype_before          boolean,
    subtype_after           boolean,
    sector_before           text,
    sector_after            text        not null,
    law_version_id_before   uuid,
    law_version_id_after    uuid        not null
);

comment on table public.factory_legal_classification_events is
    'WO-008: 별표3 분류 확인 감사 이력. append-only. 트리거가 factory_legal_classifications 변경과 같은 트랜잭션에 기록. 감사 기록 실패 시 본 변경도 롤백됨.';

-- append-only 인덱스: factory_id + occurred_at 으로 이력 조회
create index if not exists idx_flce_factory_id_occurred_at
    on public.factory_legal_classification_events (factory_id, occurred_at desc);

-- ============================================================
-- 3. 트리거 함수 — INSERT/UPDATE 시 감사 기록 (같은 트랜잭션)
--    SECURITY INVOKER: 노출 스키마에 SECURITY DEFINER 사용 금지 (WO-008).
--    감사 INSERT 실패 → 본 INSERT/UPDATE도 자동 롤백 (트랜잭션 원자성).
-- ============================================================
create or replace function public.fn_factory_legal_classification_audit()
returns trigger
language plpgsql
security invoker
as $$
begin
    insert into public.factory_legal_classification_events (
        factory_id,
        event_type,
        actor_id,
        occurred_at,
        revision_before,
        revision_after,
        item_no_before,
        item_no_after,
        subtype_before,
        subtype_after,
        sector_before,
        sector_after,
        law_version_id_before,
        law_version_id_after
    ) values (
        new.factory_id,
        tg_op,
        new.confirmed_by,
        now(),
        case when tg_op = 'UPDATE' then old.revision else null end,
        new.revision,
        case when tg_op = 'UPDATE' then old.appendix3_item_no else null end,
        new.appendix3_item_no,
        case when tg_op = 'UPDATE' then old.is_real_estate_management else null end,
        new.is_real_estate_management,
        case when tg_op = 'UPDATE' then old.confirmed_sector else null end,
        new.confirmed_sector,
        case when tg_op = 'UPDATE' then old.appendix3_law_version_id else null end,
        new.appendix3_law_version_id
    );
    return new;
end;
$$;

-- WO-010: PostgreSQL 기본 PUBLIC EXECUTE 철회 (G3 최소권한 계약).
-- service_role 실행권한은 아래 section 4 GRANT에서 부여됨.
revoke execute on function public.fn_factory_legal_classification_audit() from public;

-- 트리거: INSERT와 UPDATE 모두 커버 (same-transaction 보장).
-- 감사 테이블 INSERT 실패 → 오류 전파 → 분류 변경 트랜잭션 롤백 (원자성 증명).
create trigger trg_factory_legal_classification_audit
    after insert or update on public.factory_legal_classifications
    for each row execute function public.fn_factory_legal_classification_audit();

-- ============================================================
-- 4. RLS 활성화 + 최소 권한
--    anon / authenticated / PUBLIC 직접 접근 차단.
--    service_role 은 Supabase에서 BYPASSRLS 권한으로 RLS를 우회함
--    (정책 없어도 서비스 롤은 접근 가능, 나머지는 차단).
-- ============================================================
alter table public.factory_legal_classifications enable row level security;
alter table public.factory_legal_classification_events enable row level security;

-- 기존 PUBLIC grant 철회 (Supabase 기본 부여를 무효화).
revoke all on public.factory_legal_classifications from anon;
revoke all on public.factory_legal_classifications from authenticated;
revoke all on public.factory_legal_classification_events from anon;
revoke all on public.factory_legal_classification_events from authenticated;

-- service_role 최소 권한:
--   분류 현행판: SELECT + INSERT + UPDATE (DELETE 금지 — factories FK ON DELETE RESTRICT)
--   감사 이벤트: SELECT + INSERT (UPDATE/DELETE 금지 — append-only)
grant select, insert, update on public.factory_legal_classifications to service_role;
grant select, insert on public.factory_legal_classification_events to service_role;

-- 트리거 함수 실행 권한 (SECURITY INVOKER이므로 service_role 컨텍스트에서 실행됨)
grant execute on function public.fn_factory_legal_classification_audit() to service_role;

-- ============================================================
-- 5. 롤백 SQL (검증용 초안 — 운영 환경 실행 금지)
-- ============================================================
-- drop trigger if exists trg_factory_legal_classification_audit
--     on public.factory_legal_classifications;
-- drop function if exists public.fn_factory_legal_classification_audit();
-- drop table if exists public.factory_legal_classification_events;
-- drop table if exists public.factory_legal_classifications;
