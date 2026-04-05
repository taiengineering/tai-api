-- Supabase에서 실행: 공개 사이트 FAQ · 문의 접수
-- 실행 후 API의 site_faqs / site_contact_leads 테이블 사용

create table if not exists public.site_faqs (
  id uuid primary key default gen_random_uuid(),
  question text not null,
  answer text not null,
  sort_order int not null default 0,
  is_published boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_site_faqs_sort on public.site_faqs (is_published, sort_order);

create table if not exists public.site_contact_leads (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  company_name text,
  email text not null,
  phone text,
  inquiry_type text,
  content text not null,
  source text default 'nexas.taieng.co.kr',
  created_at timestamptz not null default now()
);

create index if not exists idx_site_contact_leads_created on public.site_contact_leads (created_at desc);

comment on table public.site_faqs is '공개 웹 FAQ (관리자에서 편집)';
comment on table public.site_contact_leads is '공개 웹 문의 접수';
