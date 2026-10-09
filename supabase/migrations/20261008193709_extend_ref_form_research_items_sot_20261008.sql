alter table public.ref_form_research_items
 add column if not exists canonical_title text,
 add column if not exists practitioner_role text,
 add column if not exists artifact_type text,
 add column if not exists suggested_formats text[],
 add column if not exists source_url text,
 add column if not exists source_attachment_url text,
 add column if not exists source_document_checksum text,
 add column if not exists source_document_access text not null default 'NOT_CHECKED',
 add column if not exists observed_fields jsonb not null default '[]'::jsonb,
 add column if not exists proposed_fields jsonb not null default '[]'::jsonb,
 add column if not exists legal_required_fields jsonb not null default '[]'::jsonb,
 add column if not exists source_observation_note text,
 add column if not exists legal_sot_reference text,
 add column if not exists legal_checked_at timestamptz,
 add column if not exists license_reference text,
 add column if not exists reuse_checked_at timestamptz,
 add column if not exists relation_group text,
 add column if not exists related_research_ids text[],
 add column if not exists validation_blockers text[] not null default array[]::text[],
 add column if not exists reviewer_id text,
 add column if not exists reviewed_at timestamptz,
 add column if not exists owner_approval_status text not null default 'NOT_REQUESTED',
 add column if not exists owner_approved_at timestamptz,
 add column if not exists publication_status text not null default 'NOT_READY',
 add column if not exists corpus_version text not null default 'REF01-FROZEN-20261008';
alter table public.ref_form_research_items
 add constraint ref_form_owner_approval_status_ck check(owner_approval_status in ('NOT_REQUESTED','PENDING','APPROVED','REJECTED')),
 add constraint ref_form_publication_status_ck check(publication_status in ('NOT_READY','READY_FOR_REVIEW','APPROVED_FOR_PUBLICATION','PUBLISHED','RETIRED'));
create index if not exists ref_form_research_relation_idx on public.ref_form_research_items(relation_group);
create index if not exists ref_form_research_publication_idx on public.ref_form_research_items(publication_status,owner_approval_status);
comment on table public.ref_form_research_items is 'Single source of truth for frozen REF-01 form discovery, evidence, legal/rights validation and publication gate; legal facts authoritative only through LEG.';
