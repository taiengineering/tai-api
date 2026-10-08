-- ─────────────────────────────────────────────────────────────────────────────
-- TAM-008B — Approval Route Foundation
-- Tables: tam_approval_routes, tam_approval_route_versions,
--         tam_approval_route_steps, tam_approval_step_assignees
-- btree_gist: NOT required (delegation tables are a later WP)
-- PRODUCTION APPLY = 0 — Owner approval + GPT independent verification required
-- ─────────────────────────────────────────────────────────────────────────────

-- ════════════════════════════════════════════════════════════════════
-- TABLE 1: tam_approval_routes
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE tam_approval_routes (
    route_id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id         UUID        NOT NULL,
    factory_id         UUID,                           -- NULL = company-wide scope
    route_scope        TEXT        NOT NULL,
        -- 'COMPANY_DEFAULT' | 'FACTORY_DEFAULT' | 'DOCUMENT_TYPE' | 'PROCESS_TYPE'
    scope_key          TEXT,                           -- NULL for DEFAULT scopes
    display_name       TEXT        NOT NULL,
    is_active          BOOLEAN     NOT NULL DEFAULT true,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by         UUID        NOT NULL,
    current_version_id UUID,                           -- NULL before first publish

    CONSTRAINT tam_routes_scope_chk CHECK (
        route_scope IN ('COMPANY_DEFAULT','FACTORY_DEFAULT','DOCUMENT_TYPE','PROCESS_TYPE')
    ),
    CONSTRAINT tam_routes_default_key_chk CHECK (
        (route_scope IN ('COMPANY_DEFAULT','FACTORY_DEFAULT') AND scope_key IS NULL)
        OR
        (route_scope IN ('DOCUMENT_TYPE','PROCESS_TYPE') AND scope_key IS NOT NULL)
    ),
    CONSTRAINT tam_routes_factory_default_requires_factory CHECK (
        route_scope != 'FACTORY_DEFAULT' OR factory_id IS NOT NULL
    )
);

-- Scope deduplication: COALESCE normalizes NULLs for standard UNIQUE semantics
CREATE UNIQUE INDEX tam_routes_uniq
    ON tam_approval_routes (
        company_id,
        COALESCE(factory_id,  '00000000-0000-0000-0000-000000000000'::uuid),
        route_scope,
        COALESCE(scope_key, '')
    );

CREATE INDEX ix_tam_routes_tenant
    ON tam_approval_routes (company_id, factory_id, is_active);


-- ════════════════════════════════════════════════════════════════════
-- TABLE 2: tam_approval_route_versions
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE tam_approval_route_versions (
    version_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    route_id        UUID        NOT NULL
                                REFERENCES tam_approval_routes(route_id),
    version_number  INT         NOT NULL,       -- per-route 1-based sequential
    version_status  TEXT        NOT NULL DEFAULT 'DRAFT',
        -- 'DRAFT' | 'PUBLISHED' (no SUPERSEDED: history preserved, pointer replaced)
    notes           TEXT,
    published_at    TIMESTAMPTZ,
    published_by    UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID        NOT NULL,

    CONSTRAINT tam_route_ver_status_chk CHECK (
        version_status IN ('DRAFT','PUBLISHED')
    ),
    CONSTRAINT tam_route_ver_published_fields CHECK (
        version_status != 'PUBLISHED'
        OR (published_at IS NOT NULL AND published_by IS NOT NULL)
    ),
    UNIQUE (route_id, version_number),
    UNIQUE (route_id, version_id)       -- composite FK target for routes.current_version_id
);

CREATE INDEX ix_tam_route_ver_route
    ON tam_approval_route_versions (route_id, version_status);


-- ════════════════════════════════════════════════════════════════════
-- TABLE 3: tam_approval_route_steps
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE tam_approval_route_steps (
    step_id          UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id       UUID    NOT NULL
                             REFERENCES tam_approval_route_versions(version_id),
    step_order       INT     NOT NULL,          -- 1-based sequential
    step_name        TEXT    NOT NULL,
    step_type        TEXT    NOT NULL,
        -- 'SEQUENTIAL' | 'PARALLEL_ANY' | 'PARALLEL_ALL'
    allow_supplement BOOLEAN NOT NULL DEFAULT false,

    CONSTRAINT tam_steps_type_chk CHECK (
        step_type IN ('SEQUENTIAL','PARALLEL_ANY','PARALLEL_ALL')
    ),
    UNIQUE (version_id, step_order)
);

CREATE INDEX ix_tam_steps_version
    ON tam_approval_route_steps (version_id, step_order);


-- ════════════════════════════════════════════════════════════════════
-- TABLE 4: tam_approval_step_assignees
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE tam_approval_step_assignees (
    assignee_id UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    step_id     UUID        NOT NULL
                            REFERENCES tam_approval_route_steps(step_id),
    user_id     UUID        NOT NULL,
    assigned_by UUID        NOT NULL,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (step_id, user_id)
);

CREATE INDEX ix_tam_assignees_step ON tam_approval_step_assignees (step_id);
CREATE INDEX ix_tam_assignees_user ON tam_approval_step_assignees (user_id, step_id);


-- ════════════════════════════════════════════════════════════════════
-- COMPOSITE FK: routes.current_version_id must reference same-route version
-- (circular reference: routes → versions → routes; added after versions exists)
-- T26 gate: cross-route version reference is rejected at DB level
-- ════════════════════════════════════════════════════════════════════

ALTER TABLE tam_approval_routes
    ADD CONSTRAINT tam_routes_current_version_fk
    FOREIGN KEY (route_id, current_version_id)
    REFERENCES tam_approval_route_versions(route_id, version_id)
    DEFERRABLE INITIALLY DEFERRED;


-- ════════════════════════════════════════════════════════════════════
-- TRIGGER 1: PUBLISHED state guard on tam_approval_routes
-- current_version_id must reference a PUBLISHED version of the same route
-- T27 gate: DRAFT version pointer is rejected by this trigger
-- ════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION tam_routes_published_guard_fn()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_status TEXT;
BEGIN
    IF NEW.current_version_id IS NOT NULL THEN
        SELECT version_status INTO v_status
          FROM tam_approval_route_versions
         WHERE version_id = NEW.current_version_id
           AND route_id   = NEW.route_id;
        IF v_status IS DISTINCT FROM 'PUBLISHED' THEN
            RAISE EXCEPTION
                'current_version_id must reference a PUBLISHED version of the same route';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER tam_routes_published_guard_trg
    BEFORE INSERT OR UPDATE ON tam_approval_routes
    FOR EACH ROW EXECUTE FUNCTION tam_routes_published_guard_fn();


-- ════════════════════════════════════════════════════════════════════
-- TRIGGER 2: tam_approval_route_versions immutability
-- UPDATE on PUBLISHED version: forbidden
-- DELETE on any version: forbidden
-- ════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION tam_version_immutability_fn()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'tam_approval_route_versions: delete is forbidden';
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.version_status = 'PUBLISHED' THEN
        RAISE EXCEPTION 'tam_approval_route_versions: published version is immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER tam_version_immutability_trg
    BEFORE UPDATE OR DELETE ON tam_approval_route_versions
    FOR EACH ROW EXECUTE FUNCTION tam_version_immutability_fn();


-- ════════════════════════════════════════════════════════════════════
-- TRIGGER 3: tam_approval_route_steps — draft-only enforcement (R1)
-- INSERT/UPDATE/DELETE forbidden when version is not DRAFT.
-- R1: uses SELECT ... FOR UPDATE on the version row to prevent races with
--     concurrent publish_version. UPDATE checks BOTH OLD and NEW version_id.
-- ════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION tam_steps_draft_only_fn()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_status TEXT;
BEGIN
    IF TG_OP = 'INSERT' THEN
        SELECT version_status INTO v_status
          FROM tam_approval_route_versions
         WHERE version_id = NEW.version_id FOR UPDATE;
        IF v_status IS DISTINCT FROM 'DRAFT' THEN
            RAISE EXCEPTION
                'tam_approval_route_steps: modifications forbidden on non-DRAFT version (status=%)',
                v_status;
        END IF;
        RETURN NEW;
    END IF;

    IF TG_OP = 'UPDATE' THEN
        -- Check OLD side
        SELECT version_status INTO v_status
          FROM tam_approval_route_versions
         WHERE version_id = OLD.version_id FOR UPDATE;
        IF v_status IS DISTINCT FROM 'DRAFT' THEN
            RAISE EXCEPTION
                'tam_approval_route_steps: modifications forbidden on non-DRAFT version (status=%)',
                v_status;
        END IF;
        -- Check NEW side if version_id changed
        IF NEW.version_id IS DISTINCT FROM OLD.version_id THEN
            SELECT version_status INTO v_status
              FROM tam_approval_route_versions
             WHERE version_id = NEW.version_id FOR UPDATE;
            IF v_status IS DISTINCT FROM 'DRAFT' THEN
                RAISE EXCEPTION
                    'tam_approval_route_steps: modifications forbidden on non-DRAFT version (status=%)',
                    v_status;
            END IF;
        END IF;
        RETURN NEW;
    END IF;

    IF TG_OP = 'DELETE' THEN
        SELECT version_status INTO v_status
          FROM tam_approval_route_versions
         WHERE version_id = OLD.version_id FOR UPDATE;
        IF v_status IS DISTINCT FROM 'DRAFT' THEN
            RAISE EXCEPTION
                'tam_approval_route_steps: modifications forbidden on non-DRAFT version (status=%)',
                v_status;
        END IF;
        RETURN OLD;
    END IF;
END;
$$;

CREATE TRIGGER tam_steps_draft_only_trg
    BEFORE INSERT OR UPDATE OR DELETE ON tam_approval_route_steps
    FOR EACH ROW EXECUTE FUNCTION tam_steps_draft_only_fn();


-- ════════════════════════════════════════════════════════════════════
-- TRIGGER 4: tam_approval_step_assignees — draft-only enforcement (R1)
-- INSERT/UPDATE/DELETE forbidden when step's version is not DRAFT.
-- R1: uses FOR UPDATE OF rv on the version row. UPDATE checks BOTH
--     OLD.step_id and NEW.step_id (if different) to prevent step
--     reassignment across version boundaries.
-- ════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION tam_assignees_draft_only_fn()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_status  TEXT;
BEGIN
    IF TG_OP = 'INSERT' THEN
        SELECT rv.version_status INTO v_status
          FROM tam_approval_route_steps    s
          JOIN tam_approval_route_versions rv ON rv.version_id = s.version_id
         WHERE s.step_id = NEW.step_id
           FOR UPDATE OF rv;
        IF v_status IS DISTINCT FROM 'DRAFT' THEN
            RAISE EXCEPTION
                'tam_approval_step_assignees: modifications forbidden on non-DRAFT version (status=%)',
                v_status;
        END IF;
        RETURN NEW;
    END IF;

    IF TG_OP = 'UPDATE' THEN
        -- Check OLD step's version
        SELECT rv.version_status INTO v_status
          FROM tam_approval_route_steps    s
          JOIN tam_approval_route_versions rv ON rv.version_id = s.version_id
         WHERE s.step_id = OLD.step_id
           FOR UPDATE OF rv;
        IF v_status IS DISTINCT FROM 'DRAFT' THEN
            RAISE EXCEPTION
                'tam_approval_step_assignees: modifications forbidden on non-DRAFT version (status=%)',
                v_status;
        END IF;
        -- Check NEW step's version if step changed
        IF NEW.step_id IS DISTINCT FROM OLD.step_id THEN
            SELECT rv.version_status INTO v_status
              FROM tam_approval_route_steps    s
              JOIN tam_approval_route_versions rv ON rv.version_id = s.version_id
             WHERE s.step_id = NEW.step_id
               FOR UPDATE OF rv;
            IF v_status IS DISTINCT FROM 'DRAFT' THEN
                RAISE EXCEPTION
                    'tam_approval_step_assignees: modifications forbidden on non-DRAFT version (status=%)',
                    v_status;
            END IF;
        END IF;
        RETURN NEW;
    END IF;

    IF TG_OP = 'DELETE' THEN
        SELECT rv.version_status INTO v_status
          FROM tam_approval_route_steps    s
          JOIN tam_approval_route_versions rv ON rv.version_id = s.version_id
         WHERE s.step_id = OLD.step_id
           FOR UPDATE OF rv;
        IF v_status IS DISTINCT FROM 'DRAFT' THEN
            RAISE EXCEPTION
                'tam_approval_step_assignees: modifications forbidden on non-DRAFT version (status=%)',
                v_status;
        END IF;
        RETURN OLD;
    END IF;
END;
$$;

CREATE TRIGGER tam_assignees_draft_only_trg
    BEFORE INSERT OR UPDATE OR DELETE ON tam_approval_step_assignees
    FOR EACH ROW EXECUTE FUNCTION tam_assignees_draft_only_fn();
