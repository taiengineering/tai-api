-- WO: MASTER-WO-TAI-SEARCH-DICT-001 (OBJ-SEARCH-DICT)
-- STEP: search dictionary persistence (optional runtime tier T6 pg_trgm)
-- ARTIFACT ONLY — DB APPLY = 0 (운영자/GPT 승인 후 별도 실행)
-- Additive + idempotent. No drops, no data mutation. public. schema.

CREATE TABLE IF NOT EXISTS public.search_term_master (
    term_id              TEXT PRIMARY KEY,            -- SHA256_UTF8 per WO §23
    term_original        TEXT NOT NULL,
    term_normalized      TEXT NOT NULL,
    term_compact         TEXT NOT NULL,
    term_latin_lower     TEXT,
    term_no_punctuation  TEXT,
    term_type            TEXT NOT NULL,
    language             TEXT,
    pos_hint             TEXT,
    subject_type         TEXT NOT NULL,
    subject_key          TEXT NOT NULL,
    canonical_id         TEXT,                        -- nullable per Contract
    status               TEXT NOT NULL,               -- APPROVED indexed; others audit-only
    source_id            TEXT,
    source_key           TEXT,
    evidence_ref         TEXT,
    quality_flag         TEXT,
    curation_method      TEXT,
    confidence           TEXT,
    created_from_snapshot TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS public.search_term_relations (
    relation_id      TEXT PRIMARY KEY,
    from_term_id     TEXT NOT NULL,
    to_subject_type  TEXT NOT NULL,
    to_subject_key   TEXT NOT NULL,
    relation_type    TEXT NOT NULL,
    status           TEXT NOT NULL,
    evidence_ref     TEXT,
    created_from_snapshot TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_search_term_normalized
    ON public.search_term_master (term_normalized);
CREATE INDEX IF NOT EXISTS ix_search_term_compact
    ON public.search_term_master (term_compact);
CREATE INDEX IF NOT EXISTS ix_search_term_subject
    ON public.search_term_master (subject_type, subject_key);
CREATE INDEX IF NOT EXISTS ix_search_term_status
    ON public.search_term_master (status);

-- Optional fuzzy tier (T6). Requires pg_trgm; guarded so apply stays idempotent.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS ix_search_term_trgm
    ON public.search_term_master USING gin (term_normalized gin_trgm_ops);

COMMENT ON TABLE public.search_term_master IS
    'TAI search dictionary terms (WO SEARCH-DICT-001). APPROVED rows feed production search; others audit-only.';
COMMENT ON TABLE public.search_term_relations IS
    'TAI search dictionary term relations (abbreviation/spacing/synonym/english). MERGE=OWNER.';
