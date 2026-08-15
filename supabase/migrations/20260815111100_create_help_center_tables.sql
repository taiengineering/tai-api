-- WP-1 헬프센터 신규 스키마 (Goal G-msu9k73f-da14e7)
-- 전량 신설. 기존 safe_help_content 는 읽기 전용 참고 자산으로 보존하며 이 마이그레이션에서 건드리지 않는다.
-- 키 설계: doc_id 네임스페이스 / 문서 slug 는 언어별 유일 / 노드 slug 는 형제 내 유일

-- ============================================================
-- 1. 블록 배열 검증 함수 (help_doc.blocks CHECK 용)
-- ============================================================
create or replace function public.help_blocks_valid(b jsonb)
returns boolean
language plpgsql
immutable
as $$
declare
  e jsonb;
  n_total int;
  n_uniq  int;
begin
  if b is null then
    return true;
  end if;
  if jsonb_typeof(b) <> 'array' then
    return false;
  end if;

  for e in select * from jsonb_array_elements(b) loop
    if jsonb_typeof(e) <> 'object' then
      return false;
    end if;
    if (e ->> 'block_id') is null or (e ->> 'type') is null then
      return false;
    end if;
    if (e ->> 'type') not in
       ('lead','step','callout','checklist','escalate','include','table','image') then
      return false;
    end if;
  end loop;

  select count(*), count(distinct x ->> 'block_id')
    into n_total, n_uniq
    from jsonb_array_elements(b) x;

  if n_total <> n_uniq then
    return false;
  end if;

  return true;
end
$$;

comment on function public.help_blocks_valid(jsonb) is
  'help_doc.blocks 형식 검증: 배열 / 각 원소는 block_id 와 허용된 type 8종 보유 / block_id 중복 불가';

-- ============================================================
-- 2. 공통 updated_at 트리거 함수
-- ============================================================
create or replace function public.help_touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end
$$;

-- ============================================================
-- 3. help_doc — 문서(내용). 배치는 소유하지 않는다.
-- ============================================================
create table if not exists public.help_doc (
  doc_id        text primary key,
  type          text        not null,
  slug          text        not null,
  lang          text        not null default 'ko',
  doc_group     text        not null,
  title         text        not null,
  answer_short  text        not null,
  when_to_use   text        not null,
  blocks        jsonb       not null default '[]'::jsonb,
  aliases       text[]      not null default '{}',
  symptom_texts text[]      not null default '{}',
  page_slug     text,
  related_laws  text[]      not null default '{}',
  pair_doc      text,
  status        text        not null default 'DRAFT',
  version       integer     not null default 1,
  change_note   text,
  review_due    date,
  search_tsv    tsvector,
  created_at    timestamptz not null default now(),
  created_by    text,
  updated_at    timestamptz not null default now(),
  updated_by    text,

  constraint help_doc_type_chk
    check (type in ('GUIDE','TROUBLE','FAQ','TASK','CONCEPT','POLICY')),
  constraint help_doc_status_chk
    check (status in ('DRAFT','PUBLISHED','ARCHIVED')),
  constraint help_doc_slug_chk
    check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  constraint help_doc_lang_chk
    check (lang ~ '^[a-z]{2}(-[A-Z]{2})?$'),
  -- doc_id 네임스페이스: <TYPE>-<domain>-<key>
  constraint help_doc_doc_id_ns_chk
    check (doc_id ~ '^(GUIDE|TROUBLE|FAQ|TASK|CONCEPT|POLICY)-[a-z0-9]+(-[a-z0-9]+)+$'),
  -- K1 / K2 강제: 요약과 참조 조건이 없는 문서는 저장할 수 없다
  constraint help_doc_answer_short_chk
    check (length(btrim(answer_short)) > 0),
  constraint help_doc_when_to_use_chk
    check (length(btrim(when_to_use)) > 0),
  constraint help_doc_blocks_chk
    check (public.help_blocks_valid(blocks)),
  constraint help_doc_pair_fk
    foreign key (pair_doc) references public.help_doc (doc_id) on delete set null
);

-- 문서 slug 는 언어별로 유일 (전역 유일이 아니다 — 번역본이 같은 slug 를 쓸 수 있어야 한다)
create unique index if not exists help_doc_slug_lang_key
  on public.help_doc (slug, lang);

create index if not exists help_doc_group_idx    on public.help_doc (doc_group);
create index if not exists help_doc_type_idx     on public.help_doc (type);
create index if not exists help_doc_status_idx   on public.help_doc (status);
create index if not exists help_doc_pageslug_idx on public.help_doc (page_slug);
create index if not exists help_doc_pair_idx     on public.help_doc (pair_doc);
create index if not exists help_doc_tsv_idx      on public.help_doc using gin (search_tsv);
create index if not exists help_doc_aliases_idx  on public.help_doc using gin (aliases);
create index if not exists help_doc_symptom_idx  on public.help_doc using gin (symptom_texts);
create index if not exists help_doc_review_idx   on public.help_doc (review_due) where review_due is not null;

drop trigger if exists help_doc_touch_trg on public.help_doc;
create trigger help_doc_touch_trg
  before update on public.help_doc
  for each row execute function public.help_touch_updated_at();

comment on table  public.help_doc is '헬프센터 문서. 내용만 소유하고 배치는 help_node 가 소유한다.';
comment on column public.help_doc.doc_id       is '네임스페이스 키 <TYPE>-<domain>-<key> (예: TROUBLE-tbm-attendee-missing)';
comment on column public.help_doc.answer_short is 'LLM 계약 K1 — 그 자체로 답이 되는 2~3문장. 비어 있을 수 없다.';
comment on column public.help_doc.when_to_use  is 'LLM 계약 K2 — 어떤 문의에 이 문서를 꺼내는가. 비어 있을 수 없다.';
comment on column public.help_doc.blocks       is '본문 블록 배열. 각 블록은 안정적 block_id 를 갖는다.';
comment on column public.help_doc.doc_group    is '번역본 묶음 키. lang 과 함께 같은 문서의 언어 변형을 묶는다.';
comment on column public.help_doc.pair_doc     is '문서 짝 — 작업자 증상(TROUBLE) 과 안전관리자 조치(TASK) 를 연결한다.';

-- ============================================================
-- 4. help_node — 트리(배치). 내용은 소유하지 않는다.
-- ============================================================
create table if not exists public.help_node (
  id          uuid        primary key default gen_random_uuid(),
  parent_id   uuid,
  root_key    text        not null,
  node_type   text        not null,
  title       text        not null,
  slug        text        not null,
  description text,
  sort_order  integer     not null default 0,
  visibility  text        not null default 'PUBLIC',
  roles       text[]      not null default '{}',
  sectors     text[]      not null default '{}',
  min_level   integer,
  addons      text[]      not null default '{}',
  doc_id      text,
  link_url    text,
  icon        text,
  status      text        not null default 'DRAFT',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),

  constraint help_node_parent_fk
    foreign key (parent_id) references public.help_node (id) on delete restrict,
  constraint help_node_doc_fk
    foreign key (doc_id) references public.help_doc (doc_id) on delete restrict,
  constraint help_node_root_key_chk
    check (root_key in ('ROLE','JOURNEY','SYMPTOM','CROSS')),
  constraint help_node_type_chk
    check (node_type in ('SECTION','DOC','LINK')),
  constraint help_node_visibility_chk
    check (visibility in ('PUBLIC','AUTH')),
  constraint help_node_status_chk
    check (status in ('DRAFT','PUBLISHED','ARCHIVED')),
  constraint help_node_slug_chk
    check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  -- 노드 종류별 필수 항목
  constraint help_node_shape_chk
    check (
      (node_type = 'DOC'     and doc_id is not null and link_url is null)
      or (node_type = 'SECTION' and doc_id is null     and link_url is null)
      or (node_type = 'LINK'    and link_url is not null and doc_id is null)
    ),
  -- 루트는 SECTION 만 가능
  constraint help_node_root_shape_chk
    check (parent_id is not null or node_type = 'SECTION')
);

-- 노드 slug 는 형제 안에서만 유일하다 (루트는 parent_id 가 null 이므로 고정 UUID 로 대체해 묶는다)
create unique index if not exists help_node_sibling_slug_key
  on public.help_node (coalesce(parent_id, '00000000-0000-0000-0000-000000000000'::uuid), slug);

create index if not exists help_node_parent_idx on public.help_node (parent_id, sort_order);
create index if not exists help_node_root_idx   on public.help_node (root_key, sort_order);
create index if not exists help_node_doc_idx    on public.help_node (doc_id);
create index if not exists help_node_status_idx on public.help_node (status);

drop trigger if exists help_node_touch_trg on public.help_node;
create trigger help_node_touch_trg
  before update on public.help_node
  for each row execute function public.help_touch_updated_at();

-- 순환 참조 차단
create or replace function public.help_node_no_cycle()
returns trigger
language plpgsql
as $$
declare
  cur   uuid;
  depth int := 0;
begin
  if new.parent_id is null then
    return new;
  end if;
  if new.parent_id = new.id then
    raise exception 'help_node: 자기 자신을 부모로 지정할 수 없습니다 (id=%)', new.id;
  end if;

  cur := new.parent_id;
  while cur is not null loop
    depth := depth + 1;
    if cur = new.id then
      raise exception 'help_node: 순환 참조입니다 (id=%)', new.id;
    end if;
    if depth > 32 then
      raise exception 'help_node: 계층 깊이 상한(32)을 넘었습니다 (id=%)', new.id;
    end if;
    select parent_id into cur from public.help_node where id = cur;
  end loop;

  return new;
end
$$;

drop trigger if exists help_node_no_cycle_trg on public.help_node;
create trigger help_node_no_cycle_trg
  before insert or update of parent_id on public.help_node
  for each row execute function public.help_node_no_cycle();

comment on table  public.help_node is '헬프센터 트리. 문서가 어디에·어떤 순서로·누구에게 보이는지를 소유한다. 같은 doc_id 를 여러 노드에 배치할 수 있다.';
comment on column public.help_node.root_key   is '축 구분 — ROLE(역할) / JOURNEY(여정) / SYMPTOM(증상) / CROSS(횡단)';
comment on column public.help_node.slug       is '형제 안에서만 유일. 경로 기반 URL 을 구성한다.';
comment on column public.help_node.visibility is 'PUBLIC 은 비로그인 노출, AUTH 는 로그인 필요. 판정은 서버에서 종결한다.';

-- ============================================================
-- 5. help_feedback — 문서별 도움 여부 수집
-- ============================================================
create table if not exists public.help_feedback (
  id           uuid        primary key default gen_random_uuid(),
  doc_id       text        not null,
  block_id     text,
  verdict      text        not null,
  reason_code  text,
  reason_text  text,
  ctx          text,
  referrer     text,
  session_hash text        not null,
  created_at   timestamptz not null default now(),

  constraint help_feedback_doc_fk
    foreign key (doc_id) references public.help_doc (doc_id) on delete cascade,
  constraint help_feedback_verdict_chk
    check (verdict in ('UP','DOWN'))
);

-- 같은 세션이 같은 문서에 중복 기록하지 못하게 한다
create unique index if not exists help_feedback_once_key
  on public.help_feedback (doc_id, session_hash);

create index if not exists help_feedback_doc_idx
  on public.help_feedback (doc_id, created_at desc);

comment on table  public.help_feedback is '문서 피드백. 개인 식별자를 저장하지 않는다 — 세션 해시만 보관한다.';
comment on column public.help_feedback.session_hash is '중복 방지용 단방향 해시. 원문 식별자를 저장하지 않는다.';

-- ============================================================
-- 6. help_search_log — 검색어 수집. 결과 0건이 곧 문서 결손 목록이다.
-- ============================================================
create table if not exists public.help_search_log (
  id             uuid        primary key default gen_random_uuid(),
  q              text        not null,
  ctx            text,
  role           text,
  sector         text,
  result_count   integer     not null default 0,
  clicked_doc_id text,
  created_at     timestamptz not null default now()
);

create index if not exists help_search_log_zero_idx
  on public.help_search_log (created_at desc)
  where result_count = 0;

create index if not exists help_search_log_q_idx
  on public.help_search_log (lower(q));

create index if not exists help_search_log_created_idx
  on public.help_search_log (created_at desc);

comment on table public.help_search_log is '헬프센터 검색 로그. result_count = 0 인 검색어가 문서 결손 후보다.';
