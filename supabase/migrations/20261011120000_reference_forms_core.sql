-- =============================================================================
-- Migration: 20261011120000_reference_forms_core.sql
-- Description: Reference Forms CMS — 12-table core schema
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. reference_forms — core identity, status machine
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reference_forms (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    status              TEXT        NOT NULL DEFAULT 'DRAFT'
                                    CHECK (status IN ('DRAFT','PUBLISHED','ARCHIVED')),
    owner_approved      BOOLEAN     NOT NULL DEFAULT false,
    owner_approved_at   TIMESTAMPTZ,
    published_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 2. reference_form_content — slug, title, description, body_html, content_hash
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reference_form_content (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    form_id         UUID        NOT NULL
                                REFERENCES reference_forms(id) ON DELETE RESTRICT,
    lang            TEXT        NOT NULL DEFAULT 'ko',
    canonical_slug  TEXT        NOT NULL,
    title           TEXT        NOT NULL,
    description     TEXT,
    body_html       TEXT,
    content_hash    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (form_id, lang),
    UNIQUE (canonical_slug)
);

-- ---------------------------------------------------------------------------
-- 3. reference_form_slug_history — redirect log
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reference_form_slug_history (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    form_id     UUID        NOT NULL
                            REFERENCES reference_forms(id) ON DELETE RESTRICT,
    old_slug    TEXT        NOT NULL UNIQUE,
    new_slug    TEXT        NOT NULL,
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 4. reference_form_slug_registry — global slug uniqueness
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reference_form_slug_registry (
    slug        TEXT        PRIMARY KEY,
    form_id     UUID        NOT NULL
                            REFERENCES reference_forms(id) ON DELETE RESTRICT,
    slug_status TEXT        NOT NULL DEFAULT 'CANONICAL'
                            CHECK (slug_status IN ('CANONICAL','HISTORY')),
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 5. reference_form_files — file_ref, sha256, qa_status, approved_at
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reference_form_files (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    form_id             UUID        NOT NULL
                                    REFERENCES reference_forms(id) ON DELETE RESTRICT,
    file_ref            TEXT        NOT NULL,
    sha256              TEXT        NOT NULL,
    qa_status           TEXT        NOT NULL DEFAULT 'PENDING'
                                    CHECK (qa_status IN ('PENDING','QA_PASS','QA_FAIL')),
    approved_at         TIMESTAMPTZ,
    is_active           BOOLEAN     NOT NULL DEFAULT true,
    preview_artifact_id UUID,       -- FK added after table 6
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 6. reference_form_preview_artifacts — preview_ref, source_file_sha256, is_published
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reference_form_preview_artifacts (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    form_id             UUID        NOT NULL
                                    REFERENCES reference_forms(id) ON DELETE RESTRICT,
    preview_ref         TEXT        NOT NULL,
    source_file_sha256  TEXT        NOT NULL,
    is_published        BOOLEAN     NOT NULL DEFAULT false,
    qa_status           TEXT        NOT NULL DEFAULT 'PENDING'
                                    CHECK (qa_status IN ('PENDING','QA_PASS','QA_FAIL')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Add FK from reference_form_files.preview_artifact_id → reference_form_preview_artifacts(id)
ALTER TABLE reference_form_files
    ADD CONSTRAINT fk_files_preview_artifact
    FOREIGN KEY (preview_artifact_id)
    REFERENCES reference_form_preview_artifacts(id) ON DELETE RESTRICT;

-- ---------------------------------------------------------------------------
-- 7. reference_form_sources — rights_status
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reference_form_sources (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    form_id         UUID        NOT NULL
                                REFERENCES reference_forms(id) ON DELETE RESTRICT,
    source_name     TEXT        NOT NULL,
    source_url      TEXT,
    rights_status   TEXT        NOT NULL DEFAULT 'REVIEW_REQUIRED'
                                CHECK (rights_status IN ('REVIEW_REQUIRED','CLEARED','BLOCKED')),
    is_active       BOOLEAN     NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 8. reference_form_relations — form_id, related_form_id, relation_type
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reference_form_relations (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    form_id         UUID        NOT NULL
                                REFERENCES reference_forms(id) ON DELETE RESTRICT,
    related_form_id UUID        NOT NULL
                                REFERENCES reference_forms(id) ON DELETE RESTRICT,
    relation_type   TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (form_id, related_form_id, relation_type)
);

-- ---------------------------------------------------------------------------
-- 9. reference_form_legacy_links — legacy_code UNIQUE
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reference_form_legacy_links (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    form_id     UUID        NOT NULL
                            REFERENCES reference_forms(id) ON DELETE RESTRICT,
    legacy_code TEXT        NOT NULL UNIQUE,
    is_active   BOOLEAN     NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 10. reference_form_aliases — alias_slug UNIQUE
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reference_form_aliases (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    form_id     UUID        NOT NULL
                            REFERENCES reference_forms(id) ON DELETE RESTRICT,
    alias_slug  TEXT        NOT NULL UNIQUE,
    is_active   BOOLEAN     NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 11. reference_form_approvals — approved_content_hash, approved_file_hashes JSONB
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reference_form_approvals (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    form_id                 UUID        NOT NULL
                                        REFERENCES reference_forms(id) ON DELETE RESTRICT,
    approval_status         TEXT        NOT NULL DEFAULT 'PENDING'
                                        CHECK (approval_status IN ('PENDING','APPROVED','REJECTED')),
    approved_content_hash   TEXT,
    approved_file_hashes    JSONB       NOT NULL DEFAULT '[]'::JSONB,
    is_current              BOOLEAN     NOT NULL DEFAULT true,
    approved_at             TIMESTAMPTZ,
    approved_by             TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- UNIQUE INDEX: only one current APPROVED approval per form
CREATE UNIQUE INDEX IF NOT EXISTS uq_approvals_current_approved
    ON reference_form_approvals(form_id)
    WHERE is_current = true AND approval_status = 'APPROVED';

-- ---------------------------------------------------------------------------
-- 12. reference_form_events — audit log, immutable (ON DELETE RESTRICT)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reference_form_events (
    id          BIGSERIAL   PRIMARY KEY,
    form_id     UUID        NOT NULL
                            REFERENCES reference_forms(id) ON DELETE RESTRICT,
    event_type  TEXT        NOT NULL,
    actor       TEXT,
    payload     JSONB       NOT NULL DEFAULT '{}'::JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- INDEXES
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_reference_forms_status
    ON reference_forms(status);

CREATE INDEX IF NOT EXISTS idx_reference_form_content_canonical_slug
    ON reference_form_content(canonical_slug);

CREATE INDEX IF NOT EXISTS idx_reference_form_files_qa_status
    ON reference_form_files(qa_status, is_active);

CREATE INDEX IF NOT EXISTS idx_reference_form_events_created_at
    ON reference_form_events(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_reference_form_events_form_id
    ON reference_form_events(form_id);

-- =============================================================================
-- FUNCTIONS
-- =============================================================================

-- fn_reference_forms_set_updated_at: BEFORE UPDATE trigger function
CREATE OR REPLACE FUNCTION fn_reference_forms_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

-- fn_reference_form_content_hash: BEFORE INSERT OR UPDATE on reference_form_content
CREATE OR REPLACE FUNCTION fn_reference_form_content_hash()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.content_hash = encode(
        extensions.digest(
            NEW.canonical_slug
            || E'\x1F'
            || NEW.title
            || E'\x1F'
            || COALESCE(NEW.description, '')
            || E'\x1F'
            || COALESCE(NEW.body_html, ''),
            'sha256'
        ),
        'hex'
    );
    RETURN NEW;
END;
$$;

-- =============================================================================
-- TRIGGERS
-- =============================================================================

-- updated_at triggers
CREATE TRIGGER trg_reference_forms_updated_at
    BEFORE UPDATE ON reference_forms
    FOR EACH ROW EXECUTE FUNCTION fn_reference_forms_set_updated_at();

CREATE TRIGGER trg_reference_form_content_updated_at
    BEFORE UPDATE ON reference_form_content
    FOR EACH ROW EXECUTE FUNCTION fn_reference_forms_set_updated_at();

CREATE TRIGGER trg_reference_form_files_updated_at
    BEFORE UPDATE ON reference_form_files
    FOR EACH ROW EXECUTE FUNCTION fn_reference_forms_set_updated_at();

CREATE TRIGGER trg_reference_form_preview_artifacts_updated_at
    BEFORE UPDATE ON reference_form_preview_artifacts
    FOR EACH ROW EXECUTE FUNCTION fn_reference_forms_set_updated_at();

-- content_hash trigger
CREATE TRIGGER trg_reference_form_content_hash
    BEFORE INSERT OR UPDATE ON reference_form_content
    FOR EACH ROW EXECUTE FUNCTION fn_reference_form_content_hash();

-- =============================================================================
-- ROW LEVEL SECURITY
-- =============================================================================
ALTER TABLE reference_forms                     ENABLE ROW LEVEL SECURITY;
ALTER TABLE reference_form_content              ENABLE ROW LEVEL SECURITY;
ALTER TABLE reference_form_slug_history         ENABLE ROW LEVEL SECURITY;
ALTER TABLE reference_form_slug_registry        ENABLE ROW LEVEL SECURITY;
ALTER TABLE reference_form_files                ENABLE ROW LEVEL SECURITY;
ALTER TABLE reference_form_preview_artifacts    ENABLE ROW LEVEL SECURITY;
ALTER TABLE reference_form_sources              ENABLE ROW LEVEL SECURITY;
ALTER TABLE reference_form_relations            ENABLE ROW LEVEL SECURITY;
ALTER TABLE reference_form_legacy_links         ENABLE ROW LEVEL SECURITY;
ALTER TABLE reference_form_aliases              ENABLE ROW LEVEL SECURITY;
ALTER TABLE reference_form_approvals            ENABLE ROW LEVEL SECURITY;
ALTER TABLE reference_form_events               ENABLE ROW LEVEL SECURITY;

-- Standard service_role policy for all tables except events
CREATE POLICY "service_role_only" ON reference_forms
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "service_role_only" ON reference_form_content
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "service_role_only" ON reference_form_slug_history
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "service_role_only" ON reference_form_slug_registry
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "service_role_only" ON reference_form_files
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "service_role_only" ON reference_form_preview_artifacts
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "service_role_only" ON reference_form_sources
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "service_role_only" ON reference_form_relations
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "service_role_only" ON reference_form_legacy_links
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "service_role_only" ON reference_form_aliases
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "service_role_only" ON reference_form_approvals
    FOR ALL USING (auth.role() = 'service_role');

-- Events: INSERT + SELECT only (immutable audit log)
CREATE POLICY "service_role_insert" ON reference_form_events
    FOR INSERT WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "service_role_select" ON reference_form_events
    FOR SELECT USING (auth.role() = 'service_role');
