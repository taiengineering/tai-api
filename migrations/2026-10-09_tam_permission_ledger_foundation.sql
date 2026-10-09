-- ─────────────────────────────────────────────────────────────────────────────
-- TAM-008C-004 — Authorization Ledger DB Foundation
--
-- Tables created:
--   1. tam_approval_audit_events   (TAM-006 확정 스키마 + Permission 이벤트 타입)
--   2. tam_permission_grants       (권한 부여 원장)
--   3. tam_permission_revocations  (권한 철회 원장)
--
-- Design reference: docs/tam/TAI_WO_TAM_008C_AUTHORIZATION_LEDGER_DESIGN.md
-- Design anchor:    c388a7f6
--
-- Migration order note:
--   This migration is independent of TAM-008B (2026-10-09_tam_approval_route_foundation.sql).
--   TAM-008B creates route/version/step/assignee tables; this migration creates permission ledger.
--   Both can be applied in any order; neither depends on the other's tables.
--
-- PRODUCTION APPLY = 0
--   Requires: Owner approval + GPT independent verification
--   Apply method: supabase db push --linked  (NOT apply_migration MCP)
--
-- Factory FK note (Option A — pending CHECK-A1~A5):
--   This migration uses a BEFORE INSERT TRIGGER for factory-company scope validation.
--   Option A (FOREIGN KEY (company_id, factory_id) REFERENCES factories(company_id, id))
--   requires a separate migration to add UNIQUE(company_id, id) to the factories table.
--   Apply the Option A migration ONLY after CHECK-A1~A5 verification in production.
-- ─────────────────────────────────────────────────────────────────────────────

-- ════════════════════════════════════════════════════════════════════
-- TABLE 1: tam_approval_audit_events
-- TAM-006 § 3.11 확정 스키마 — Append-only
-- tam_approval_audit_events가 이미 존재하면 스킵 (idempotent)
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS tam_approval_audit_events (
    audit_id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID        NOT NULL,
    request_id      UUID,                   -- 권한 이벤트는 NULL
    event_type      TEXT        NOT NULL,
    actor_user_id   UUID        NOT NULL,
    event_data      JSONB       NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes (IF NOT EXISTS — safe to re-apply)
CREATE INDEX IF NOT EXISTS ix_tam_audit_request
    ON tam_approval_audit_events (company_id, request_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_tam_audit_event_type
    ON tam_approval_audit_events (company_id, event_type, occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_tam_audit_compliance
    ON tam_approval_audit_events (company_id, occurred_at DESC);

-- Append-only trigger
CREATE OR REPLACE FUNCTION tam_audit_immutability_fn()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'tam_approval_audit_events: UPDATE forbidden (append-only)';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'tam_approval_audit_events: DELETE forbidden (append-only)';
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS tam_audit_immutability_trg ON tam_approval_audit_events;
CREATE TRIGGER tam_audit_immutability_trg
    BEFORE UPDATE OR DELETE ON tam_approval_audit_events
    FOR EACH ROW EXECUTE FUNCTION tam_audit_immutability_fn();


-- ════════════════════════════════════════════════════════════════════
-- TABLE 2: tam_permission_grants
-- 권한 부여 원장 — Append-only
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE tam_permission_grants (
    grant_id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id         UUID        NOT NULL
                                   REFERENCES companies(id),
    factory_id         UUID        NULL
                                   REFERENCES factories(id),
    subject_user_id    UUID        NOT NULL,
    permission_code    TEXT        NOT NULL
                                   CHECK (permission_code IN (
                                       'ROUTE_MANAGER',
                                       'ASSIGNEE_MANAGER',
                                       'REQUEST_SUBMITTER',
                                       'DELEGATION_MANAGER',
                                       'REQUEST_REVOKER'
                                   )),
    granted_by         UUID        NOT NULL,
    granted_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_from         TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_until        TIMESTAMPTZ NULL,
    grant_reason       TEXT        NULL,
    idempotency_key    UUID        UNIQUE NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT tam_grants_valid_period CHECK (
        valid_until IS NULL OR valid_until > valid_from
    )
);

-- Indexes
CREATE INDEX ix_tam_grants_company
    ON tam_permission_grants (company_id, permission_code);
CREATE INDEX ix_tam_grants_subject
    ON tam_permission_grants (subject_user_id, company_id);
CREATE INDEX ix_tam_grants_factory
    ON tam_permission_grants (company_id, factory_id)
    WHERE factory_id IS NOT NULL;

-- Factory-company scope validation trigger
-- (Option B light — will be replaced by Option A composite FK after CHECK-A1~A5)
CREATE OR REPLACE FUNCTION tam_grants_validate_factory_company_fn()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.factory_id IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM factories
            WHERE id = NEW.factory_id
              AND company_id = NEW.company_id
        ) THEN
            RAISE EXCEPTION
                'tam_permission_grants: factory_id % does not belong to company_id %',
                NEW.factory_id, NEW.company_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_tam_grants_validate_factory
    BEFORE INSERT ON tam_permission_grants
    FOR EACH ROW EXECUTE FUNCTION tam_grants_validate_factory_company_fn();

-- Append-only trigger
CREATE OR REPLACE FUNCTION tam_grants_immutability_fn()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'tam_permission_grants: UPDATE forbidden (append-only)';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'tam_permission_grants: DELETE forbidden (append-only)';
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER tam_grants_immutability_trg
    BEFORE UPDATE OR DELETE ON tam_permission_grants
    FOR EACH ROW EXECUTE FUNCTION tam_grants_immutability_fn();


-- ════════════════════════════════════════════════════════════════════
-- TABLE 3: tam_permission_revocations
-- 권한 철회 원장 — Append-only
-- 동일 Grant에 대한 중복 철회 금지: uq_tam_revocations_grant
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE tam_permission_revocations (
    revocation_id   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    grant_id        UUID        NOT NULL
                                REFERENCES tam_permission_grants(grant_id),
    revoked_by      UUID        NOT NULL,
    revoked_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason          TEXT        NOT NULL,
    idempotency_key UUID        UNIQUE NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 동일 Grant 중복 철회 방지 (§5.2)
CREATE UNIQUE INDEX uq_tam_revocations_grant
    ON tam_permission_revocations (grant_id);

-- Append-only trigger
CREATE OR REPLACE FUNCTION tam_revocations_immutability_fn()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'tam_permission_revocations: UPDATE forbidden (append-only)';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'tam_permission_revocations: DELETE forbidden (append-only)';
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER tam_revocations_immutability_trg
    BEFORE UPDATE OR DELETE ON tam_permission_revocations
    FOR EACH ROW EXECUTE FUNCTION tam_revocations_immutability_fn();
