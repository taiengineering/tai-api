-- ============================================================
-- 안전보건자료 검색엔진 (Postgres 네이티브 · pg_trgm)
--   대상 테이블 : public.kosha_safety_materials
--   프로젝트    : vwlahtguyggrhvslabax (Supabase)
--   적용 방법   : Supabase 대시보드 > SQL Editor 에 붙여넣고 "Run" 1회 실행
--
--   실제 컬럼: id, title, product_type, industry, accident_type,
--             url, raw_json, collected_at, category, industry_category
--   - category         : 자료유형 (EDUCATION/CASE_STUDY/GUIDE/... )
--   - industry_category: 업종     (CONSTRUCTION/MANUFACTURING/SERVICE/COMMON) = 프론트의 sector
--   - collected_at     : 수집시각 (최신순 정렬 기준)
--
--   적용 후 프론트(safety.js)는 자동으로 이 RPC(관련도 랭킹 검색)를 사용한다.
--   미적용 상태에서도 프론트는 직접 조회로 폴백하여 정상 동작한다.
-- ============================================================

-- 1) 트라이그램 확장 (한글 부분검색·유사도 랭킹)
create extension if not exists pg_trgm;

-- 2) 인덱스
--    제목 부분검색/유사도용 GIN 트라이그램 인덱스
create index if not exists idx_ksm_title_trgm
  on public.kosha_safety_materials using gin (title gin_trgm_ops);
--    필터·정렬용 b-tree 인덱스
create index if not exists idx_ksm_collected_at
  on public.kosha_safety_materials (collected_at desc);
create index if not exists idx_ksm_category
  on public.kosha_safety_materials (category);
create index if not exists idx_ksm_industry_category
  on public.kosha_safety_materials (industry_category);

-- 3) 검색 RPC
--    q         : 검색어 (빈 문자열이면 최신순 전체)
--    cat       : 자료유형 필터 ('ALL' 이면 전체)
--    sec       : 업종 필터  ('ALL' 이면 전체, 내부적으로 industry_category 매칭)
--    page_no   : 1부터
--    page_size : 페이지당 건수
--    반환      : 목록 + total_count(필터 적용 후 전체 건수, 페이지네이션용)
create or replace function public.search_safety_materials(
  q         text default '',
  cat       text default 'ALL',
  sec       text default 'ALL',
  page_no   int  default 1,
  page_size int  default 20
)
returns table (
  id           text,
  title        text,
  url          text,
  category     text,
  sector       text,
  collected_at timestamptz,
  total_count  bigint
)
language sql
stable
as $$
  with filtered as (
    select
      m.id::text          as id,
      m.title             as title,
      m.url               as url,
      m.category          as category,
      m.industry_category as sector,
      m.collected_at      as collected_at,
      case when coalesce(q, '') = '' then 0 else similarity(m.title, q) end as sim
    from public.kosha_safety_materials m
    where (cat = 'ALL' or m.category = cat)
      and (sec = 'ALL' or m.industry_category = sec)
      and (coalesce(q, '') = '' or m.title ilike '%' || q || '%')
  ),
  cnt as (select count(*)::bigint as c from filtered)
  select
    f.id, f.title, f.url, f.category, f.sector, f.collected_at,
    (select c from cnt) as total_count
  from filtered f
  order by f.sim desc, f.collected_at desc nulls last
  limit  greatest(page_size, 1)
  offset (greatest(page_no, 1) - 1) * greatest(page_size, 1);
$$;

-- 4) 익명(anon) 실행 권한 (프론트 anon key 로 호출)
grant execute on function public.search_safety_materials(text, text, text, int, int) to anon;

-- 5) PostgREST 스키마 캐시 재적재 (새 함수 즉시 노출)
notify pgrst, 'reload schema';

-- ------------------------------------------------------------
-- 확인:
--   select * from public.search_safety_materials('추락', 'ALL', 'ALL', 1, 5);
--
-- 롤백:
--   drop function if exists public.search_safety_materials(text,text,text,int,int);
--   drop index if exists idx_ksm_title_trgm;
--   drop index if exists idx_ksm_collected_at;
--   drop index if exists idx_ksm_category;
--   drop index if exists idx_ksm_industry_category;
-- ------------------------------------------------------------
