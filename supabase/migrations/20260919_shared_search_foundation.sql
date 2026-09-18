-- WO-TAI-SHARED-SEARCH-F1 — Shared Search Foundation.
--
-- Introduces the ONE shared search projection + the two supporting
-- tables that carry rebuild runs and their staging documents. No
-- Domain-specific search table. No FTS index, no pg_trgm index, no
-- ranking index — those land in F3 (SEARCH-05) alongside the
-- retrieval engine's actual query plan.
--
-- Migration file is checked into the repo. Production apply is
-- explicitly deferred (Owner-approved separate step). Every unique
-- constraint / CHECK enforces a contract clause from
-- docs/search/TAI_SHARED_SEARCH_DOCUMENT_CONTRACT_v1.md.

-- --------------------------------------------------------------------
-- search_documents — the ONE current serving projection.
-- Contract: 1 (object_type, canonical_id) -> 1 current row.
-- --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.search_documents (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  object_type          text NOT NULL,
  canonical_id         text NOT NULL,

  source_id            text NOT NULL,
  source_key           text,                              -- NULLABLE (contract §3)

  title                text NOT NULL,
  summary              text,
  search_text          text NOT NULL,

  aliases              text[] NOT NULL DEFAULT '{}',
  keywords             text[] NOT NULL DEFAULT '{}',

  -- subjects = ordered list of {subject_type, subject_key} pairs (contract §3, §5)
  subjects             jsonb NOT NULL DEFAULT '[]'::jsonb,
  -- context  = ordered list of {context_type, context_key}   (contract §8)
  context              jsonb NOT NULL DEFAULT '[]'::jsonb,

  public_url           text,
  saas_url             text,

  publication_status   text NOT NULL,
  visibility_scopes    text[] NOT NULL DEFAULT '{}',

  source_updated_at    timestamptz NOT NULL,
  content_hash         text NOT NULL,
  indexed_at           timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT search_documents_publication_status_chk CHECK (
    publication_status IN ('PUBLISHED', 'HOLD', 'REMOVED')
  ),
  CONSTRAINT search_documents_subjects_is_array CHECK (
    jsonb_typeof(subjects) = 'array'
  ),
  CONSTRAINT search_documents_context_is_array CHECK (
    jsonb_typeof(context) = 'array'
  )
);

-- Contract §2: (object_type, canonical_id) uniquely identifies a
-- canonical searchable object. Enforced at the DB layer so the
-- Common Writer's Python-side check has a hard floor.
CREATE UNIQUE INDEX IF NOT EXISTS search_documents_canonical_uk
  ON public.search_documents (object_type, canonical_id);

-- Publication filter index — the retrieval engine (F3) will pick
-- final index shapes; this one is Foundation-side minimum for
-- Common Writer operations.
CREATE INDEX IF NOT EXISTS search_documents_publication_status_idx
  ON public.search_documents (publication_status);

COMMENT ON TABLE public.search_documents IS
  'Unified Shared Search projection. One row per canonical searchable object. Never a source of truth — populated by Domain adapters (F2).';
COMMENT ON COLUMN public.search_documents.source_key IS
  'NULLABLE. Some Domains have no source-native identifier (e.g. CSI). Synthetic placeholders are forbidden.';
COMMENT ON COLUMN public.search_documents.publication_status IS
  'One of PUBLISHED / HOLD / REMOVED. Adapters map Domain state to this shared enum.';
COMMENT ON COLUMN public.search_documents.subjects IS
  'jsonb array of {subject_type, subject_key} pairs, sorted + deduplicated. Not parallel arrays.';
COMMENT ON COLUMN public.search_documents.context IS
  'jsonb array of {context_type, context_key} pairs. Context types are constrained by the writer.';
COMMENT ON COLUMN public.search_documents.content_hash IS
  'Deterministic SHA-256 of retrieval-scoped normalized fields. See docs/search/TAI_SHARED_SEARCH_DOCUMENT_CONTRACT_v1.md §5.';

-- --------------------------------------------------------------------
-- search_rebuild_runs — one row per FULL REBUILD attempt.
-- --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.search_rebuild_runs (
  run_id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_type               text NOT NULL,        -- FULL / DOMAIN
  status                 text NOT NULL,        -- see CHECK below

  started_at             timestamptz NOT NULL DEFAULT now(),
  completed_at           timestamptz,

  expected_domains       text[] NOT NULL DEFAULT '{}',
  completed_domains      text[] NOT NULL DEFAULT '{}',

  candidate_count        integer NOT NULL DEFAULT 0,
  current_count_before   integer,

  error_code             text,
  error_message          text,

  manifest_json          jsonb NOT NULL DEFAULT '{}'::jsonb,

  CONSTRAINT search_rebuild_runs_status_chk CHECK (
    status IN ('RUNNING', 'VALIDATED', 'PROMOTED', 'FAILED')
  ),
  CONSTRAINT search_rebuild_runs_run_type_chk CHECK (
    run_type IN ('FULL', 'DOMAIN')
  )
);

CREATE INDEX IF NOT EXISTS search_rebuild_runs_status_idx
  ON public.search_rebuild_runs (status, started_at DESC);

COMMENT ON TABLE public.search_rebuild_runs IS
  'One row per Shared Search FULL REBUILD attempt. Promotion is atomic; partial failures never leave the current projection in a partial state.';

-- --------------------------------------------------------------------
-- search_rebuild_documents — staged documents per run.
-- One (run_id, object_type, canonical_id) tuple per staged doc.
-- --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.search_rebuild_documents (
  run_id               uuid NOT NULL REFERENCES public.search_rebuild_runs (run_id) ON DELETE CASCADE,
  object_type          text NOT NULL,
  canonical_id         text NOT NULL,
  document_json        jsonb NOT NULL,
  content_hash         text NOT NULL,
  staged_at            timestamptz NOT NULL DEFAULT now(),

  PRIMARY KEY (run_id, object_type, canonical_id)
);

CREATE INDEX IF NOT EXISTS search_rebuild_documents_run_idx
  ON public.search_rebuild_documents (run_id);

COMMENT ON TABLE public.search_rebuild_documents IS
  'Staged SearchDocuments for a FULL REBUILD run. Only rows from a VALIDATED run are eligible for atomic promotion into search_documents.';

-- --------------------------------------------------------------------
-- promote_search_rebuild(run_id)
-- Atomic promotion: replace current search_documents with the run's
-- staged documents, iff the run is in VALIDATED state.
--
-- Guarantee (Constitution §10, Doc Contract §11):
--   partial rebuild -> current unchanged
-- This function performs the swap inside a single transaction. On
-- ANY error inside the function the transaction rolls back and the
-- current projection is untouched.
-- --------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.promote_search_rebuild(p_run_id uuid)
RETURNS TABLE (promoted_count integer)
LANGUAGE plpgsql
AS $$
DECLARE
  v_status  text;
  v_count   integer;
BEGIN
  -- Guard: the run must exist and be VALIDATED.
  SELECT status INTO v_status
    FROM public.search_rebuild_runs
    WHERE run_id = p_run_id
    FOR UPDATE;
  IF v_status IS NULL THEN
    RAISE EXCEPTION 'search_rebuild_run % not found', p_run_id
      USING ERRCODE = 'no_data_found';
  END IF;
  IF v_status <> 'VALIDATED' THEN
    RAISE EXCEPTION 'search_rebuild_run % is % (must be VALIDATED)', p_run_id, v_status
      USING ERRCODE = 'invalid_parameter_value';
  END IF;

  -- Atomic replace. TRUNCATE-then-INSERT would take a heavier lock;
  -- DELETE-then-INSERT under one transaction is sufficient at
  -- Foundation scale. If any INSERT raises the whole tx rolls back.
  --
  -- PUBLISHED-only filter (Foundation §11.4 tombstone contract +
  -- Document Contract §6): HOLD and REMOVED staged rows never
  -- enter the current projection. This matches the Python
  -- RebuildFramework.promote() semantics.
  DELETE FROM public.search_documents;

  INSERT INTO public.search_documents (
      object_type, canonical_id,
      source_id, source_key,
      title, summary, search_text,
      aliases, keywords, subjects, context,
      public_url, saas_url,
      publication_status, visibility_scopes,
      source_updated_at, content_hash, indexed_at
  )
  SELECT
      (document_json->>'object_type'),
      (document_json->>'canonical_id'),
      (document_json->>'source_id'),
      (document_json->>'source_key'),
      (document_json->>'title'),
      (document_json->>'summary'),
      (document_json->>'search_text'),
      COALESCE(ARRAY(SELECT jsonb_array_elements_text(document_json->'aliases')), '{}'),
      COALESCE(ARRAY(SELECT jsonb_array_elements_text(document_json->'keywords')), '{}'),
      COALESCE(document_json->'subjects', '[]'::jsonb),
      COALESCE(document_json->'context',  '[]'::jsonb),
      (document_json->>'public_url'),
      (document_json->>'saas_url'),
      (document_json->>'publication_status'),
      COALESCE(ARRAY(SELECT jsonb_array_elements_text(document_json->'visibility_scopes')), '{}'),
      (document_json->>'source_updated_at')::timestamptz,
      content_hash,
      now()
  FROM public.search_rebuild_documents
  WHERE run_id = p_run_id
    AND document_json->>'publication_status' = 'PUBLISHED';

  GET DIAGNOSTICS v_count = ROW_COUNT;

  UPDATE public.search_rebuild_runs
     SET status       = 'PROMOTED',
         completed_at = now()
   WHERE run_id = p_run_id;

  promoted_count := v_count;
  RETURN NEXT;
END;
$$;

COMMENT ON FUNCTION public.promote_search_rebuild(uuid) IS
  'Atomic promotion of a VALIDATED rebuild run into search_documents. Rolls back on any error; current projection stays intact.';
