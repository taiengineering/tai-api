-- ─────────────────────────────────────────────────────────────────────────────
-- TAM-008C-004 — Authorization Ledger DB Foundation + Security Hardening
--
-- Tables created:
--   1. tam_approval_audit_events   (TAM-006 확정 스키마 + Permission 이벤트 타입)
--   2. tam_permission_grants       (권한 부여 원장)
--   3. tam_permission_revocations  (권한 철회 원장)
--
-- Security additions vs. original migrations/2026-10-09_tam_permission_ledger_foundation.sql:
--   - ENABLE ROW LEVEL SECURITY on all 3 tables
--   - REVOKE ALL FROM PUBLIC/anon/authenticated
--   - GRANT SELECT, INSERT (append-only) to service_role
--   - REVOKE EXECUTE ON FUNCTION ... FROM PUBLIC (3 trigger functions)
--
-- Design reference: docs/tam/TAI_WO_TAM_008C_AUTHORIZATION_LEDGER_DESIGN.md
-- Design anchor:    c388a7f6
--
-- Migration order note:
--   Apply after 20261009010000 (factories UNIQUE prerequisite) and
--   20261009010001 (approval route foundation).
--   Factory FK: FOREIGN KEY (company_id, factory_id) REFERENCES factories(company_id, id)
--   requires uq_factories_company_id on factories.
--
-- Apply method: supabase db push --linked  (NOT apply_migration MCP)
-- ─────────────────────────────────────────────────────────────────────────────

-- ════════════════════════════════════════════════════════════════════
-- PRE-FLIGHT: tam_approval_audit_events 기존 스키마 정합성 검사
-- 기존 테이블이 있을 경우 TAM-006 계약 필수 컬럼 6개 존재 여부 확인.
-- 누락 시 RAISE EXCEPTION — Fail-closed.
-- ════════════════════════════════════════════════════════════════════

DO $$
DECLARE
    tbl_exists  boolean;
    missing_cols text[];
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name   = 'tam_approval_audit_events'
    ) INTO tbl_exists;

    IF tbl_exists THEN
        SELECT array_agg(rc ORDER BY rc) INTO missing_cols
        FROM unnest(ARRAY[
            'audit_id',
            'company_id',
            'event_type',
            'actor_user_id',
            'event_data',
            'occurred_at'
        ]) AS rc
        WHERE rc NOT IN (
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name   = 'tam_approval_audit_events'
        );

        IF array_length(missing_cols, 1) > 0 THEN
            RAISE EXCEPTION
                'tam_approval_audit_events: existing schema incompatible with TAM-006 contract — missing columns: %',
                missing_cols;
        END IF;
    END IF;
END;
$$;


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
-- Factory-company 범위: 복합 FK (Option A)
--   Prerequisite: uq_factories_company_id → 20261009010000
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
    ),

    -- Option A: factory-company 복합 참조 무결성
    CONSTRAINT tam_grants_factory_scope
        FOREIGN KEY (company_id, factory_id)
        REFERENCES factories(company_id, id)
);

-- Indexes
CREATE INDEX ix_tam_grants_company
    ON tam_permission_grants (company_id, permission_code);
CREATE INDEX ix_tam_grants_subject
    ON tam_permission_grants (subject_user_id, company_id);
CREATE INDEX ix_tam_grants_factory
    ON tam_permission_grants (company_id, factory_id)
    WHERE factory_id IS NOT NULL;

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


-- ════════════════════════════════════════════════════════════════════
-- SECURITY: RLS + Grant matrix for all 3 permission ledger tables
--
-- Supabase auto-grants ALL to anon/authenticated/service_role on
-- every new table. Revoke ALL explicitly from each role before
-- re-granting the minimum required privileges to service_role only.
-- Append-only tables: service_role gets SELECT + INSERT only.
-- UPDATE/DELETE are additionally blocked by immutability triggers.
-- ════════════════════════════════════════════════════════════════════

-- tam_approval_audit_events (append-only)
ALTER TABLE tam_approval_audit_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE tam_approval_audit_events FROM PUBLIC;
REVOKE ALL ON TABLE tam_approval_audit_events FROM anon;
REVOKE ALL ON TABLE tam_approval_audit_events FROM authenticated;
REVOKE ALL ON TABLE tam_approval_audit_events FROM service_role;
GRANT SELECT, INSERT ON TABLE tam_approval_audit_events TO service_role;

-- tam_permission_grants (append-only)
ALTER TABLE tam_permission_grants ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE tam_permission_grants FROM PUBLIC;
REVOKE ALL ON TABLE tam_permission_grants FROM anon;
REVOKE ALL ON TABLE tam_permission_grants FROM authenticated;
REVOKE ALL ON TABLE tam_permission_grants FROM service_role;
GRANT SELECT, INSERT ON TABLE tam_permission_grants TO service_role;

-- tam_permission_revocations (append-only)
ALTER TABLE tam_permission_revocations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE tam_permission_revocations FROM PUBLIC;
REVOKE ALL ON TABLE tam_permission_revocations FROM anon;
REVOKE ALL ON TABLE tam_permission_revocations FROM authenticated;
REVOKE ALL ON TABLE tam_permission_revocations FROM service_role;
GRANT SELECT, INSERT ON TABLE tam_permission_revocations TO service_role;

-- Trigger function EXECUTE revoked from all roles
-- (Supabase auto-grants EXECUTE to anon/authenticated/service_role for new functions)
REVOKE EXECUTE ON FUNCTION tam_audit_immutability_fn() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION tam_audit_immutability_fn() FROM anon;
REVOKE EXECUTE ON FUNCTION tam_audit_immutability_fn() FROM authenticated;
REVOKE EXECUTE ON FUNCTION tam_audit_immutability_fn() FROM service_role;

REVOKE EXECUTE ON FUNCTION tam_grants_immutability_fn() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION tam_grants_immutability_fn() FROM anon;
REVOKE EXECUTE ON FUNCTION tam_grants_immutability_fn() FROM authenticated;
REVOKE EXECUTE ON FUNCTION tam_grants_immutability_fn() FROM service_role;

REVOKE EXECUTE ON FUNCTION tam_revocations_immutability_fn() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION tam_revocations_immutability_fn() FROM anon;
REVOKE EXECUTE ON FUNCTION tam_revocations_immutability_fn() FROM authenticated;
REVOKE EXECUTE ON FUNCTION tam_revocations_immutability_fn() FROM service_role;
