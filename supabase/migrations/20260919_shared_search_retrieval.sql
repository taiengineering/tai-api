-- WO-TAI-SHARED-SEARCH-F3 §12-§16 — Shared Search Retrieval Indexes.
--
-- Builds ONLY on top of the existing Foundation tables (F1 migration
-- 20260919_shared_search_foundation.sql). Does NOT redefine any
-- Foundation schema. Adds FTS, pg_trgm, and JSON/array GIN indexes
-- that the Shared Retrieval Engine (services/shared_search/retrieval.py)
-- needs to support the 8-tier query plan.
--
-- Migration is checked in. Production apply is explicitly deferred
-- until F3-G1 Owner Approval (after GATE-1 independent verify +
-- Owner sign-off). See docs/search/TAI_SHARED_SEARCH_F3_RETRIEVAL_PUBLIC.md
-- for the activation sequence.
--
-- Every index is IF NOT EXISTS — safe to re-apply.
-- No DDL that touches Foundation tables (search_documents, etc.)
-- outside of adding indexes.

-- pg_trgm is required for TRIGRAM tier (tier 8, §15).
-- Extension is CREATE IF NOT EXISTS — harmless on pre-existing installs.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- --------------------------------------------------------------------
-- FTS indexes (§14)
-- --------------------------------------------------------------------

-- Primary FTS index over search_text (the lexical body for all Domains).
-- Uses 'simple' dictionary so Korean/English pass through without stemming.
-- The retrieval engine issues:
--   to_tsvector('simple', search_text) @@ plainto_tsquery('simple', $q)
CREATE INDEX IF NOT EXISTS search_documents_fts_search_text_idx
  ON public.search_documents
  USING gin(to_tsvector('simple', search_text));

-- Weighted FTS: title promoted to weight 'A', search_text to 'B'.
-- Used for ts_rank_cd scoring when a dictionary SUBJECT match
-- needs to be compared against FTS relevance.
-- Expression must match the retrieval engine's query exactly.
CREATE INDEX IF NOT EXISTS search_documents_fts_weighted_idx
  ON public.search_documents
  USING gin(
    setweight(to_tsvector('simple', title), 'A')
    || setweight(to_tsvector('simple', coalesce(search_text, '')), 'B')
  );

-- --------------------------------------------------------------------
-- pg_trgm index (§15) — TRIGRAM tier, title only.
-- WO §15: "대형 법령 본문 전체에 무조건 trigram GIN을 걸어 index 폭증
-- 시키지 않는다." → only title, not search_text.
-- --------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS search_documents_title_trgm_idx
  ON public.search_documents
  USING gin(title gin_trgm_ops);

-- --------------------------------------------------------------------
-- JSON / array GIN indexes (§16) — only for columns used in the
-- retrieval query plan.
-- --------------------------------------------------------------------

-- subjects GIN: supports `subjects @> '[{"subject_key": "X"}]'::jsonb`
CREATE INDEX IF NOT EXISTS search_documents_subjects_gin_idx
  ON public.search_documents
  USING gin(subjects);

-- context GIN: supports `context @> '[{"context_key": "X"}]'::jsonb`
CREATE INDEX IF NOT EXISTS search_documents_context_gin_idx
  ON public.search_documents
  USING gin(context);

-- aliases GIN: supports `aliases @> ARRAY['term']`
CREATE INDEX IF NOT EXISTS search_documents_aliases_gin_idx
  ON public.search_documents
  USING gin(aliases);

-- visibility_scopes GIN: `visibility_scopes @> ARRAY['PUBLIC']`
-- Already needed for every retrieval query's visibility filter.
CREATE INDEX IF NOT EXISTS search_documents_visibility_scopes_gin_idx
  ON public.search_documents
  USING gin(visibility_scopes);

-- --------------------------------------------------------------------
-- Scalar indexes for identifier / canonical exact tiers (§19)
-- --------------------------------------------------------------------

-- source_key exact match (IDENTIFIER_EXACT, tier 1).
-- Partial index excludes NULL rows for smaller index footprint.
CREATE INDEX IF NOT EXISTS search_documents_source_key_idx
  ON public.search_documents (object_type, source_key)
  WHERE source_key IS NOT NULL;

-- canonical_id exact match (CANONICAL_EXACT, tier 2).
CREATE INDEX IF NOT EXISTS search_documents_canonical_id_idx
  ON public.search_documents (object_type, canonical_id);

-- object_type filter — used with most retrieval queries that allow
-- caller-specified object_type restrictions.
CREATE INDEX IF NOT EXISTS search_documents_object_type_idx
  ON public.search_documents (object_type);

-- source_updated_at DESC — used in deterministic ORDER BY within each tier.
CREATE INDEX IF NOT EXISTS search_documents_source_updated_at_idx
  ON public.search_documents (source_updated_at DESC);

-- title exact / prefix — for TITLE_EXACT tier without FTS overhead.
CREATE INDEX IF NOT EXISTS search_documents_title_lower_idx
  ON public.search_documents (lower(title));

-- --------------------------------------------------------------------
-- Comments
-- --------------------------------------------------------------------
COMMENT ON INDEX search_documents_fts_search_text_idx IS
  'FTS tier 7: to_tsvector(simple, search_text) @@ plainto_tsquery(simple, $q)';
COMMENT ON INDEX search_documents_fts_weighted_idx IS
  'Weighted FTS: title=A, search_text=B. Used for ts_rank_cd ordering within FTS tier.';
COMMENT ON INDEX search_documents_title_trgm_idx IS
  'TRIGRAM tier 8: title % $q (pg_trgm similarity). Title only per WO §15.';
COMMENT ON INDEX search_documents_subjects_gin_idx IS
  'SUBJECT tier 3: subjects @> [{subject_key: X}]::jsonb';
COMMENT ON INDEX search_documents_context_gin_idx IS
  'CONTEXT tier 6: context @> [{context_key: X}]::jsonb';
COMMENT ON INDEX search_documents_aliases_gin_idx IS
  'ALIAS_EXACT tier 5: aliases @> ARRAY[$q]';
COMMENT ON INDEX search_documents_visibility_scopes_gin_idx IS
  'Visibility filter: visibility_scopes @> ARRAY[scope] — applied to all tiers.';
COMMENT ON INDEX search_documents_source_key_idx IS
  'IDENTIFIER_EXACT tier 1: (object_type, source_key) = ($type, $q)';
COMMENT ON INDEX search_documents_canonical_id_idx IS
  'CANONICAL_EXACT tier 2: (object_type, canonical_id) = ($type, $q)';
