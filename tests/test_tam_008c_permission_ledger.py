"""TAM-008C-004 — Authorization Ledger DB Foundation tests.

D01–D16 contract tests for tam_permission_grants, tam_permission_revocations,
tam_approval_audit_events.

Test environment:
  Local PostgreSQL via TAM_008C_PG_DSN env var
  (default: host=localhost dbname=tai_test_tam_ledger)
  Module-scoped fixture bootstraps schema: companies + factories + users stubs
  + Option A UNIQUE(company_id, id) on factories + migration SQL.
  All DB tests are skipped if the DSN is unreachable.

Design reference: docs/tam/TAI_WO_TAM_008C_AUTHORIZATION_LEDGER_DESIGN.md
Design anchor:    c388a7f6
"""
from __future__ import annotations

import os
import pathlib
import threading
import time
import uuid

import psycopg2
import psycopg2.extras
import pytest

# ── DSN ───────────────────────────────────────────────────────────────────────

_DSN = os.getenv("TAM_008C_PG_DSN", "host=localhost dbname=tai_test_tam_ledger")
_MIGRATION_SQL = (
    pathlib.Path(__file__).parent.parent
    / "migrations"
    / "2026-10-09_tam_permission_ledger_foundation.sql"
).read_text()

# ── Stable UUIDs ──────────────────────────────────────────────────────────────

CO_A  = "aaaaaaaa-0001-0001-0001-000000000001"
CO_B  = "bbbbbbbb-0002-0002-0002-000000000002"
FAC1  = "ffffffff-0001-0001-0001-000000000001"  # belongs to CO_A
FAC2  = "ffffffff-0002-0002-0002-000000000002"  # belongs to CO_A
FAC_B = "ffffffff-0003-0003-0003-000000000003"  # belongs to CO_B
U1    = "11111111-1111-1111-1111-111111111111"   # CO_A user
U2    = "22222222-2222-2222-2222-222222222222"   # CO_A user
U_ADM = "00000000-0000-0000-0000-000000000001"   # platform admin (granter)

# ── Availability check ─────────────────────────────────────────────────────────

def _pg_available() -> bool:
    try:
        conn = psycopg2.connect(_DSN, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False

pytestmark = pytest.mark.skipif(not _pg_available(), reason="PostgreSQL unavailable")


# ── Module-scoped schema fixture ───────────────────────────────────────────────

@pytest.fixture(scope="module")
def pg():
    """Bootstrap test DB: stubs + Option A UNIQUE on factories + migration SQL."""
    conn = psycopg2.connect(_DSN)
    conn.autocommit = True
    cur = conn.cursor()

    # Drop TAM permission ledger tables and functions
    cur.execute("""
        DROP TABLE IF EXISTS
            tam_permission_revocations,
            tam_permission_grants,
            tam_approval_audit_events
        CASCADE;
        DROP FUNCTION IF EXISTS
            tam_grants_validate_factory_company_fn,
            tam_grants_immutability_fn,
            tam_revocations_immutability_fn,
            tam_audit_immutability_fn
        CASCADE;
    """)

    # Recreate stub reference tables
    cur.execute("""
        DROP TABLE IF EXISTS users, factories, companies CASCADE;

        CREATE TABLE companies (
            id          UUID PRIMARY KEY,
            status_code TEXT NOT NULL DEFAULT 'ACTIVE'
        );

        -- Option A: UNIQUE(company_id, id) enabled in isolated test DB
        -- This satisfies CHECK-A2/A3 for test environment
        CREATE TABLE factories (
            id          UUID PRIMARY KEY,
            company_id  UUID NOT NULL REFERENCES companies(id),
            status_code TEXT NOT NULL DEFAULT 'ACTIVE',
            deleted_at  TIMESTAMPTZ NULL
        );
        CREATE UNIQUE INDEX uq_factories_company_id
            ON factories (company_id, id);

        CREATE TABLE users (
            id          UUID PRIMARY KEY,
            company_id  UUID NOT NULL REFERENCES companies(id),
            status_code TEXT NOT NULL DEFAULT 'ACTIVE',
            is_active   BOOLEAN NOT NULL DEFAULT true
        );
    """)

    # Seed reference data
    cur.execute(
        "INSERT INTO companies (id) VALUES (%s), (%s)",
        (CO_A, CO_B),
    )
    cur.execute(
        """INSERT INTO factories (id, company_id) VALUES
           (%s, %s), (%s, %s), (%s, %s)""",
        (FAC1, CO_A, FAC2, CO_A, FAC_B, CO_B),
    )
    cur.execute(
        """INSERT INTO users (id, company_id) VALUES (%s, %s), (%s, %s), (%s, %s)""",
        (U1, CO_A, U2, CO_A, U_ADM, CO_A),
    )

    # Apply migration
    cur.execute(_MIGRATION_SQL)
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def clean(pg):
    """Truncate ledger tables before each test."""
    cur = pg.cursor()
    cur.execute("""
        TRUNCATE tam_permission_revocations, tam_permission_grants,
                 tam_approval_audit_events RESTART IDENTITY CASCADE;
    """)
    pg.commit()


# ── Helper ────────────────────────────────────────────────────────────────────

def _grant(pg, *, company_id=CO_A, factory_id=None, subject=U2, permission="ROUTE_MANAGER",
           granter=U_ADM, valid_from=None, valid_until=None, reason=None, idem=None):
    """Insert a grant row and return grant_id."""
    cur = pg.cursor()
    cur.execute("""
        INSERT INTO tam_permission_grants
            (company_id, factory_id, subject_user_id, permission_code,
             granted_by, valid_from, valid_until, grant_reason, idempotency_key)
        VALUES
            (%s, %s, %s, %s,
             %s, COALESCE(%s::timestamptz, now()),
             %s::timestamptz, %s, %s::uuid)
        RETURNING grant_id
    """, (company_id, factory_id, subject, permission,
          granter, valid_from, valid_until, reason, idem))
    gid = cur.fetchone()[0]
    pg.commit()
    return gid


def _revoke(pg, grant_id, *, revoker=U_ADM, reason="test revoke", idem=None):
    """Insert a revocation row and return revocation_id."""
    cur = pg.cursor()
    cur.execute("""
        INSERT INTO tam_permission_revocations
            (grant_id, revoked_by, reason, idempotency_key)
        VALUES (%s, %s, %s, %s::uuid)
        RETURNING revocation_id
    """, (grant_id, revoker, reason, idem))
    rid = cur.fetchone()[0]
    pg.commit()
    return rid


# ══════════════════════════════════════════════════════════════════════════════
# D01 — Grant 생성 성공
# ══════════════════════════════════════════════════════════════════════════════

def test_d01_grant_create(pg):
    gid = _grant(pg)
    cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM tam_permission_grants WHERE grant_id = %s", (gid,))
    row = cur.fetchone()
    assert row is not None
    assert row["permission_code"] == "ROUTE_MANAGER"
    assert str(row["company_id"]) == CO_A
    assert str(row["subject_user_id"]) == U2
    assert str(row["granted_by"]) == U_ADM


# ══════════════════════════════════════════════════════════════════════════════
# D02 — 허용되지 않는 permission_code 거부
# ══════════════════════════════════════════════════════════════════════════════

def test_d02_invalid_permission_code(pg):
    cur = pg.cursor()
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute("""
            INSERT INTO tam_permission_grants
                (company_id, subject_user_id, permission_code, granted_by)
            VALUES (%s, %s, %s, %s)
        """, (CO_A, U2, "INVALID_CODE", U_ADM))
    pg.rollback()


# ══════════════════════════════════════════════════════════════════════════════
# D03 — STEP_APPROVER Grant 등록 거부
# ══════════════════════════════════════════════════════════════════════════════

def test_d03_step_approver_rejected(pg):
    cur = pg.cursor()
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute("""
            INSERT INTO tam_permission_grants
                (company_id, subject_user_id, permission_code, granted_by)
            VALUES (%s, %s, %s, %s)
        """, (CO_A, U2, "STEP_APPROVER", U_ADM))
    pg.rollback()


# ══════════════════════════════════════════════════════════════════════════════
# D04 — 잘못된 유효기간 거부 (valid_until <= valid_from)
# ══════════════════════════════════════════════════════════════════════════════

def test_d04_invalid_period(pg):
    cur = pg.cursor()
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute("""
            INSERT INTO tam_permission_grants
                (company_id, subject_user_id, permission_code, granted_by,
                 valid_from, valid_until)
            VALUES (%s, %s, %s, %s,
                    '2026-01-02T00:00:00Z'::timestamptz,
                    '2026-01-01T00:00:00Z'::timestamptz)
        """, (CO_A, U2, "ROUTE_MANAGER", U_ADM))
    pg.rollback()


# ══════════════════════════════════════════════════════════════════════════════
# D05 — Grant UPDATE 거부 (append-only)
# ══════════════════════════════════════════════════════════════════════════════

def test_d05_grant_update_rejected(pg):
    gid = _grant(pg)
    cur = pg.cursor()
    with pytest.raises(psycopg2.errors.RaiseException):
        cur.execute("""
            UPDATE tam_permission_grants
            SET permission_code = 'ASSIGNEE_MANAGER'
            WHERE grant_id = %s
        """, (gid,))
    pg.rollback()


# ══════════════════════════════════════════════════════════════════════════════
# D06 — Grant DELETE 거부 (append-only)
# ══════════════════════════════════════════════════════════════════════════════

def test_d06_grant_delete_rejected(pg):
    gid = _grant(pg)
    cur = pg.cursor()
    with pytest.raises(psycopg2.errors.RaiseException):
        cur.execute("DELETE FROM tam_permission_grants WHERE grant_id = %s", (gid,))
    pg.rollback()


# ══════════════════════════════════════════════════════════════════════════════
# D07 — Revocation 생성 성공
# ══════════════════════════════════════════════════════════════════════════════

def test_d07_revocation_create(pg):
    gid = _grant(pg)
    rid = _revoke(pg, gid)
    cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM tam_permission_revocations WHERE revocation_id = %s", (rid,))
    row = cur.fetchone()
    assert row is not None
    assert str(row["grant_id"]) == str(gid)
    assert str(row["revoked_by"]) == U_ADM


# ══════════════════════════════════════════════════════════════════════════════
# D08 — 동일 Grant 중복 철회 거부 (uq_tam_revocations_grant)
# ══════════════════════════════════════════════════════════════════════════════

def test_d08_duplicate_revocation_rejected(pg):
    gid = _grant(pg)
    _revoke(pg, gid)
    cur = pg.cursor()
    with pytest.raises(psycopg2.errors.UniqueViolation):
        cur.execute("""
            INSERT INTO tam_permission_revocations (grant_id, revoked_by, reason)
            VALUES (%s, %s, %s)
        """, (gid, U_ADM, "second attempt"))
    pg.rollback()


# ══════════════════════════════════════════════════════════════════════════════
# D09 — Revocation UPDATE / DELETE 거부 (append-only)
# ══════════════════════════════════════════════════════════════════════════════

def test_d09_revocation_update_rejected(pg):
    gid = _grant(pg)
    rid = _revoke(pg, gid)
    cur = pg.cursor()
    with pytest.raises(psycopg2.errors.RaiseException):
        cur.execute("""
            UPDATE tam_permission_revocations SET reason = 'tampered' WHERE revocation_id = %s
        """, (rid,))
    pg.rollback()


def test_d09b_revocation_delete_rejected(pg):
    gid = _grant(pg)
    rid = _revoke(pg, gid)
    cur = pg.cursor()
    with pytest.raises(psycopg2.errors.RaiseException):
        cur.execute("DELETE FROM tam_permission_revocations WHERE revocation_id = %s", (rid,))
    pg.rollback()


# ══════════════════════════════════════════════════════════════════════════════
# D10 — Audit UPDATE / DELETE 거부 (append-only)
# ══════════════════════════════════════════════════════════════════════════════

def test_d10_audit_update_rejected(pg):
    cur = pg.cursor()
    cur.execute("""
        INSERT INTO tam_approval_audit_events
            (company_id, event_type, actor_user_id, event_data)
        VALUES (%s, %s, %s, %s::jsonb)
        RETURNING audit_id
    """, (CO_A, "PERMISSION_GRANTED", U_ADM, '{"test": true}'))
    aid = cur.fetchone()[0]
    pg.commit()
    with pytest.raises(psycopg2.errors.RaiseException):
        cur.execute("""
            UPDATE tam_approval_audit_events SET event_type = 'TAMPERED' WHERE audit_id = %s
        """, (aid,))
    pg.rollback()


def test_d10b_audit_delete_rejected(pg):
    cur = pg.cursor()
    cur.execute("""
        INSERT INTO tam_approval_audit_events
            (company_id, event_type, actor_user_id, event_data)
        VALUES (%s, %s, %s, %s::jsonb)
        RETURNING audit_id
    """, (CO_A, "PERMISSION_REVOKED", U_ADM, '{"test": true}'))
    aid = cur.fetchone()[0]
    pg.commit()
    with pytest.raises(psycopg2.errors.RaiseException):
        cur.execute("DELETE FROM tam_approval_audit_events WHERE audit_id = %s", (aid,))
    pg.rollback()


# ══════════════════════════════════════════════════════════════════════════════
# D11 — 다른 회사 Factory 참조 거부
# ══════════════════════════════════════════════════════════════════════════════

def test_d11_cross_company_factory_rejected(pg):
    """CO_A Grant with FAC_B (belongs to CO_B) → trigger rejects."""
    cur = pg.cursor()
    with pytest.raises(psycopg2.errors.RaiseException):
        cur.execute("""
            INSERT INTO tam_permission_grants
                (company_id, factory_id, subject_user_id, permission_code, granted_by)
            VALUES (%s, %s, %s, %s, %s)
        """, (CO_A, FAC_B, U2, "ROUTE_MANAGER", U_ADM))
    pg.rollback()


# ══════════════════════════════════════════════════════════════════════════════
# D12 — 올바른 Company/Factory 조합 성공
# ══════════════════════════════════════════════════════════════════════════════

def test_d12_valid_factory_combination(pg):
    """CO_A Grant with FAC1 (belongs to CO_A) → success."""
    gid = _grant(pg, company_id=CO_A, factory_id=FAC1)
    cur = pg.cursor()
    cur.execute("SELECT factory_id FROM tam_permission_grants WHERE grant_id = %s", (gid,))
    row = cur.fetchone()
    assert str(row[0]) == FAC1


def test_d12b_company_wide_grant(pg):
    """Grant with factory_id=NULL (company-wide) → success."""
    gid = _grant(pg, company_id=CO_A, factory_id=None)
    cur = pg.cursor()
    cur.execute("SELECT factory_id FROM tam_permission_grants WHERE grant_id = %s", (gid,))
    row = cur.fetchone()
    assert row[0] is None


# ══════════════════════════════════════════════════════════════════════════════
# D13 — 감사 이벤트 타입 검사 (권한 이벤트 타입 INSERT 성공)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("event_type", [
    "PERMISSION_GRANTED",
    "PERMISSION_REVOKED",
    "PERMISSION_GRANT_EXPIRED",
    "PERMISSION_USE_DENIED",
])
def test_d13_audit_permission_event_types(pg, event_type):
    cur = pg.cursor()
    cur.execute("""
        INSERT INTO tam_approval_audit_events
            (company_id, event_type, actor_user_id, event_data)
        VALUES (%s, %s, %s, %s::jsonb)
        RETURNING audit_id
    """, (CO_A, event_type, U_ADM, '{"grant_id": "test"}'))
    aid = cur.fetchone()[0]
    pg.commit()
    assert aid is not None


# ══════════════════════════════════════════════════════════════════════════════
# D14 — 중복 Idempotency Key 거부
# ══════════════════════════════════════════════════════════════════════════════

def test_d14_duplicate_idempotency_key_grant(pg):
    idem = str(uuid.uuid4())
    _grant(pg, idem=idem)
    cur = pg.cursor()
    with pytest.raises(psycopg2.errors.UniqueViolation):
        cur.execute("""
            INSERT INTO tam_permission_grants
                (company_id, subject_user_id, permission_code, granted_by, idempotency_key)
            VALUES (%s, %s, %s, %s, %s::uuid)
        """, (CO_A, U1, "ASSIGNEE_MANAGER", U_ADM, idem))
    pg.rollback()


def test_d14b_duplicate_idempotency_key_revocation(pg):
    gid1 = _grant(pg, subject=U1)
    gid2 = _grant(pg, subject=U2)
    idem = str(uuid.uuid4())
    _revoke(pg, gid1, idem=idem)
    cur = pg.cursor()
    with pytest.raises(psycopg2.errors.UniqueViolation):
        cur.execute("""
            INSERT INTO tam_permission_revocations (grant_id, revoked_by, reason, idempotency_key)
            VALUES (%s, %s, %s, %s::uuid)
        """, (gid2, U_ADM, "dup key test", idem))
    pg.rollback()


# ══════════════════════════════════════════════════════════════════════════════
# D15 — 회사 단위 행 잠금 (Company FOR UPDATE blocks concurrent writes)
# ══════════════════════════════════════════════════════════════════════════════

def test_d15_company_row_lock_serialization(pg):
    """Verify that SELECT ... FOR UPDATE on companies row blocks a second connection.

    Simulates the TAM serialization contract (§4.6.2):
    Tx A acquires FOR UPDATE on CO_A → Tx B blocks until A commits.
    """
    results: list = []
    barrier = threading.Barrier(2)

    def tx_a():
        conn_a = psycopg2.connect(_DSN)
        conn_a.autocommit = False
        cur = conn_a.cursor()
        cur.execute("SELECT id FROM companies WHERE id = %s FOR UPDATE", (CO_A,))
        barrier.wait()          # Signal B to start
        time.sleep(0.15)        # Hold lock
        results.append("A_COMMIT")
        conn_a.commit()
        conn_a.close()

    def tx_b():
        conn_b = psycopg2.connect(_DSN)
        conn_b.autocommit = False
        cur = conn_b.cursor()
        barrier.wait()          # Wait for A to hold lock
        time.sleep(0.05)        # Ensure A holds lock first
        # This SELECT FOR UPDATE will block until A commits
        cur.execute("SELECT id FROM companies WHERE id = %s FOR UPDATE", (CO_A,))
        results.append("B_ACQUIRED")
        conn_b.commit()
        conn_b.close()

    t_a = threading.Thread(target=tx_a)
    t_b = threading.Thread(target=tx_b)
    t_a.start()
    t_b.start()
    t_a.join(timeout=5)
    t_b.join(timeout=5)

    # B must acquire lock AFTER A commits → "A_COMMIT" precedes "B_ACQUIRED"
    assert results == ["A_COMMIT", "B_ACQUIRED"], f"Lock order violated: {results}"


# ══════════════════════════════════════════════════════════════════════════════
# D16 — 기존 TAM-008B 객체명 충돌 없음
# ══════════════════════════════════════════════════════════════════════════════

def test_d16_no_name_collision_with_tam_008b(pg):
    """TAM-008C tables and functions use distinct names from TAM-008B."""
    cur = pg.cursor()

    # TAM-008C tables must exist
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name IN (
              'tam_permission_grants',
              'tam_permission_revocations',
              'tam_approval_audit_events'
          )
    """)
    found_tables = {row[0] for row in cur.fetchall()}
    assert "tam_permission_grants" in found_tables
    assert "tam_permission_revocations" in found_tables
    assert "tam_approval_audit_events" in found_tables

    # TAM-008B tables must NOT exist in this isolated test DB
    # (we only applied TAM-008C migration, not TAM-008B)
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name IN (
              'tam_approval_routes',
              'tam_approval_route_versions',
              'tam_approval_route_steps',
              'tam_approval_step_assignees'
          )
    """)
    conflict_tables = {row[0] for row in cur.fetchall()}
    assert len(conflict_tables) == 0, f"Unexpected TAM-008B tables: {conflict_tables}"

    # TAM-008C functions must exist
    cur.execute("""
        SELECT routine_name FROM information_schema.routines
        WHERE routine_schema = 'public'
          AND routine_name IN (
              'tam_grants_validate_factory_company_fn',
              'tam_grants_immutability_fn',
              'tam_revocations_immutability_fn',
              'tam_audit_immutability_fn'
          )
    """)
    found_fns = {row[0] for row in cur.fetchall()}
    assert "tam_grants_validate_factory_company_fn" in found_fns
    assert "tam_grants_immutability_fn" in found_fns
    assert "tam_revocations_immutability_fn" in found_fns
    assert "tam_audit_immutability_fn" in found_fns
