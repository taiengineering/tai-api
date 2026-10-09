create table if not exists public.ref_form_research_items (
 research_id text primary key,
 source_report text not null,
 source_title text not null,
 source_evidence text not null default 'UNKNOWN',
 source_fields_status text not null default 'UNVERIFIED',
 reuse_rights_status text not null default 'UNVERIFIED',
 legal_review_status text not null default 'PENDING',
 workflow_family text,
 work_trigger text,
 canonical_candidate_id text,
 disposition text not null default 'UNREVIEWED',
 review_status text not null default 'PENDING',
 reviewer_notes text,
 payload jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 constraint ref_form_research_items_disposition_ck check(disposition in ('UNREVIEWED','INDEPENDENT_CANDIDATE','OFFICIAL_ORIGINAL','TECHNICAL_REFERENCE','EXCLUDE','NEEDS_REVIEW')),
 constraint ref_form_research_items_review_ck check(review_status in ('PENDING','IN_PROGRESS','REVIEWED','BLOCKED'))
);
alter table public.ref_form_research_items enable row level security;
revoke all on public.ref_form_research_items from anon,authenticated;
create index if not exists ref_form_research_review_idx on public.ref_form_research_items(review_status,source_report);
create index if not exists ref_form_research_candidate_idx on public.ref_form_research_items(canonical_candidate_id);
comment on table public.ref_form_research_items is 'Internal REF-01 frozen research source row ledger. No public API grant; owner-governed review, not publication inventory.';