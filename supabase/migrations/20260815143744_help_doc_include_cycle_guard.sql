-- WP-1 보강 (Goal G-msu9k73f-da14e7)
-- include 블록의 순환 참조와 끊어진 참조를 DB에서 차단한다.
-- 트리 순환은 help_node_no_cycle 트리거가 막고 있으나 include 순환이 비어 있어 이를 맞춘다.
-- 어드민 편집기가 DB에 직접 쓰므로 서비스 계층이 아니라 데이터 계층에서 보장한다.

-- ============================================================
-- 1. blocks 에서 include 참조 대상 추출
-- ============================================================
create or replace function public.help_doc_include_refs(b jsonb)
returns text[]
language sql
immutable
as $$
  select coalesce(array_agg(distinct e ->> 'doc_id'), '{}'::text[])
    from jsonb_array_elements(coalesce(b, '[]'::jsonb)) e
   where e ->> 'type' = 'include'
     and e ->> 'doc_id' is not null
$$;

comment on function public.help_doc_include_refs(jsonb) is
  'blocks 배열에서 include 블록이 가리키는 doc_id 목록을 뽑는다.';

-- ============================================================
-- 2. include 순환·끊어진 참조 차단 트리거
-- ============================================================
create or replace function public.help_doc_no_include_cycle()
returns trigger
language plpgsql
as $$
declare
  seen     text[] := array[new.doc_id];
  frontier text[];
  nxt      text[];
  d        text;
  depth    int := 0;
begin
  frontier := public.help_doc_include_refs(new.blocks);

  if array_length(frontier, 1) is null then
    return new;
  end if;

  while array_length(frontier, 1) is not null loop
    depth := depth + 1;
    if depth > 16 then
      raise exception 'help_doc: include 깊이 상한(16)을 넘었습니다 (doc_id=%)', new.doc_id;
    end if;

    nxt := '{}'::text[];

    foreach d in array frontier loop
      if d = new.doc_id then
        raise exception 'help_doc: include 순환 참조입니다 (doc_id=%)', new.doc_id;
      end if;

      if not exists (select 1 from public.help_doc where doc_id = d) then
        raise exception 'help_doc: include 대상 문서가 없습니다 (doc_id=%)', d;
      end if;

      if not (d = any(seen)) then
        seen := seen || d;
        nxt  := nxt || coalesce(
                  (select public.help_doc_include_refs(blocks)
                     from public.help_doc where doc_id = d),
                  '{}'::text[]);
      end if;
    end loop;

    frontier := nxt;
  end loop;

  return new;
end
$$;

comment on function public.help_doc_no_include_cycle() is
  'include 블록의 순환 참조와 끊어진 참조를 차단한다. 깊이 상한 16.';

drop trigger if exists help_doc_no_include_cycle_trg on public.help_doc;
create trigger help_doc_no_include_cycle_trg
  before insert or update of blocks on public.help_doc
  for each row execute function public.help_doc_no_include_cycle();
