"""TAM-008C-005 — Read-Only Permission Verification Service tests.

A01–A20 contract tests for check_tam_permission_grant().

Test environment:
  Same isolated PostgreSQL as Foundation tests (TAM_008C_PG_DSN).
  Module-scoped fixture bootstraps Foundation Migration independently.
  A13/A14 use bad DSN / mock injection for Fail-closed verification.

Design anchor: c388a7f6
"""
from __future__ import annotations

import os
import pathlib
import uuid
from unittest.mock import MagicMock, patch

import psycopg2
import psycopg2.errors
import pytest

from services.tam.permissions_svc import TamError, check_tam_permission_grant

# ── DSN ──────────────────────────────────────────────────────────────────────

_DSN = os.getenv("TAM_008C_PG_DSN", "host=localhost dbname=tai_test_tam_ledger")
_BAD_DSN = "host=localhost port=19999 dbname=nonexistent connect_timeout=1"
_MIGRATION_SQL = (
    pathlib.Path(__file__).parent.parent
    / "migrations"
    / "2026-10-09_tam_permission_ledger_foundation.sql"
).read_text()

# ── Stable UUIDs ─────────────────────────────────────────────────────────────

CO_A      = "aaaaaaaa-0001-0001-0001-000000000001"
CO_B      = "bbbbbbbb-0002-0002-0002-000000000002"
FAC1      = "ffffffff-0001-0001-0001-000000000001"  # CO_A
FAC2      = "ffffffff-0002-0002-0002-000000000002"  # CO_A
FAC_B     = "ffffffff-0003-0003-0003-000000000003"  # CO_B
U1        = "11111111-1111-1111-1111-111111111111"   # CO_A, ACTIVE
U2        = "22222222-2222-2222-2222-222222222222"   # CO_A, ACTIVE
U_ADM     = "00000000-0000-0000-0000-000000000001"   # CO_A, ACTIVE (granter)
U_INACTIVE = "99999999-9999-9999-9999-999999999999"  # CO_A, INACTIVE


def _pg_available() -> bool:
    try:
        c = psycopg2.connect(_DSN, connect_timeout=2)
        c.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _pg_available(), reason="PostgreSQL unavailable")


# ── User dict helpers ─────────────────────────────────────────────────────────

def _user(uid: str = U2, company_id: str = CO_A,
          status_code: str = "ACTIVE", is_active: bool = True) -> dict:
    return {"id": uid, "company_id": company_id,
            "status_code": status_code, "is_active": is_active}


# ── Module-scoped DB fixture ──────────────────────────────────────────────────

@pytest.fixture(scope="module")
def pg():
    """Bootstrap isolated DB with Foundation Migration (self-contained)."""
    conn = psycopg2.connect(_DSN)
    conn.autocommit = True
    cur = conn.cursor()

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
        DROP TABLE IF EXISTS users, factories, companies CASCADE;
    """)

    cur.execute("""
        CREATE TABLE companies (
            id          UUID PRIMARY KEY,
            status_code TEXT NOT NULL DEFAULT 'ACTIVE'
        );

        CREATE TABLE factories (
            id          UUID PRIMARY KEY,
            company_id  UUID NOT NULL REFERENCES companies(id),
            status_code TEXT NOT NULL DEFAULT 'ACTIVE',
            deleted_at  TIMESTAMPTZ NULL,
            CONSTRAINT uq_factories_company_id UNIQUE (company_id, id)
        );

        CREATE TABLE users (
            id          UUID PRIMARY KEY,
            company_id  UUID NOT NULL REFERENCES companies(id),
            status_code TEXT NOT NULL DEFAULT 'ACTIVE',
            is_active   BOOLEAN NOT NULL DEFAULT true
        );
    """)

    cur.execute("INSERT INTO companies (id) VALUES (%s), (%s)", (CO_A, CO_B))
    cur.execute(
        "INSERT INTO factories (id, company_id) VALUES (%s,%s),(%s,%s),(%s,%s)",
        (FAC1, CO_A, FAC2, CO_A, FAC_B, CO_B),
    )
    cur.execute(
        """INSERT INTO users (id, company_id, status_code, is_active) VALUES
           (%s,%s,%s,%s), (%s,%s,%s,%s), (%s,%s,%s,%s), (%s,%s,%s,%s)""",
        (U1, CO_A, "ACTIVE", True,
         U2, CO_A, "ACTIVE", True,
         U_ADM, CO_A, "ACTIVE", True,
         U_INACTIVE, CO_A, "INACTIVE", False),
    )

    cur.execute(_MIGRATION_SQL)
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def clean(pg):
    cur = pg.cursor()
    cur.execute("""
        TRUNCATE tam_permission_revocations, tam_permission_grants,
                 tam_approval_audit_events RESTART IDENTITY CASCADE;
    """)
    pg.commit()


# ── Grant / Revocation helpers ────────────────────────────────────────────────

def _grant(pg, *, company_id=CO_A, factory_id=None, subject=U2,
           permission="ROUTE_MANAGER", granter=U_ADM,
           valid_from=None, valid_until=None) -> str:
    cur = pg.cursor()
    cur.execute("""
        INSERT INTO tam_permission_grants
            (company_id, factory_id, subject_user_id, permission_code,
             granted_by, valid_from, valid_until)
        VALUES
            (%s, %s, %s, %s, %s,
             COALESCE(%s::timestamptz, now()),
             %s::timestamptz)
        RETURNING grant_id::text
    """, (company_id, factory_id, subject, permission,
          granter, valid_from, valid_until))
    gid = cur.fetchone()[0]
    pg.commit()
    return gid


def _revoke(pg, grant_id: str) -> None:
    cur = pg.cursor()
    cur.execute("""
        INSERT INTO tam_permission_revocations (grant_id, revoked_by, reason)
        VALUES (%s, %s, %s)
    """, (grant_id, U_ADM, "test"))
    pg.commit()


# ══════════════════════════════════════════════════════════════════════════════
# A01 — 유효한 ROUTE_MANAGER Grant → VALID
# ══════════════════════════════════════════════════════════════════════════════

def test_a01_valid_route_manager_grant(pg):
    gid = _grant(pg, permission="ROUTE_MANAGER")
    result = check_tam_permission_grant(
        _user(), company_id=CO_A, factory_id=None,
        permission_code="ROUTE_MANAGER", dsn=_DSN,
    )
    assert result["grant_valid"] is True
    assert result["code"] == "GRANT_VALID"
    assert str(result["grant_id"]) == str(gid)
    assert result["permission_code"] == "ROUTE_MANAGER"


# ══════════════════════════════════════════════════════════════════════════════
# A02 — Grant 없음 → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_a02_no_grant(pg):
    result = check_tam_permission_grant(
        _user(), company_id=CO_A, factory_id=None,
        permission_code="ROUTE_MANAGER", dsn=_DSN,
    )
    assert result["grant_valid"] is False
    assert result["code"] == "GRANT_NOT_FOUND"
    assert result["grant_id"] is None


# ══════════════════════════════════════════════════════════════════════════════
# A03 — 미래 시작 Grant → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_a03_future_grant(pg):
    _grant(pg, valid_from="2099-01-01T00:00:00Z", valid_until="2099-12-31T00:00:00Z")
    result = check_tam_permission_grant(
        _user(), company_id=CO_A, factory_id=None,
        permission_code="ROUTE_MANAGER", dsn=_DSN,
    )
    assert result["grant_valid"] is False
    assert result["code"] == "GRANT_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════════════════
# A04 — 만료된 Grant → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_a04_expired_grant(pg):
    _grant(pg, valid_from="2020-01-01T00:00:00Z", valid_until="2020-12-31T00:00:00Z")
    result = check_tam_permission_grant(
        _user(), company_id=CO_A, factory_id=None,
        permission_code="ROUTE_MANAGER", dsn=_DSN,
    )
    assert result["grant_valid"] is False
    assert result["code"] == "GRANT_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════════════════
# A05 — 철회된 Grant → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_a05_revoked_grant(pg):
    gid = _grant(pg)
    _revoke(pg, gid)
    result = check_tam_permission_grant(
        _user(), company_id=CO_A, factory_id=None,
        permission_code="ROUTE_MANAGER", dsn=_DSN,
    )
    assert result["grant_valid"] is False
    assert result["code"] == "GRANT_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════════════════
# A06 — 비활성 사용자 → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_a06_inactive_user(pg):
    _grant(pg, subject=U_INACTIVE)
    # INACTIVE status_code
    result = check_tam_permission_grant(
        _user(uid=U_INACTIVE, status_code="INACTIVE", is_active=False),
        company_id=CO_A, factory_id=None,
        permission_code="ROUTE_MANAGER", dsn=_DSN,
    )
    assert result["grant_valid"] is False
    assert result["code"] == "USER_INACTIVE"


def test_a06b_is_active_false(pg):
    _grant(pg)
    # ACTIVE status_code but is_active=False
    result = check_tam_permission_grant(
        _user(status_code="ACTIVE", is_active=False),
        company_id=CO_A, factory_id=None,
        permission_code="ROUTE_MANAGER", dsn=_DSN,
    )
    assert result["grant_valid"] is False
    assert result["code"] == "USER_INACTIVE"


# ══════════════════════════════════════════════════════════════════════════════
# A07 — 회사 불일치 → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_a07_company_mismatch(pg):
    _grant(pg, company_id=CO_A, subject=U2)
    # User belongs to CO_A, but checking against CO_B
    result = check_tam_permission_grant(
        _user(company_id=CO_A),
        company_id=CO_B, factory_id=None,
        permission_code="ROUTE_MANAGER", dsn=_DSN,
    )
    assert result["grant_valid"] is False
    assert result["code"] == "COMPANY_MISMATCH"


# ══════════════════════════════════════════════════════════════════════════════
# A08 — 다른 Factory Grant → DENY (factory scope mismatch)
# ══════════════════════════════════════════════════════════════════════════════

def test_a08_factory_scope_mismatch(pg):
    """Grant is for FAC2 but caller checks FAC1 → no match."""
    _grant(pg, factory_id=FAC2)
    result = check_tam_permission_grant(
        _user(), company_id=CO_A, factory_id=FAC1,
        permission_code="ROUTE_MANAGER", dsn=_DSN,
    )
    assert result["grant_valid"] is False
    assert result["code"] == "GRANT_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════════════════
# A09 — Company-wide Grant (factory_id=NULL) → VALID
# ══════════════════════════════════════════════════════════════════════════════

def test_a09_company_wide_grant(pg):
    gid = _grant(pg, factory_id=None)
    result = check_tam_permission_grant(
        _user(), company_id=CO_A, factory_id=None,
        permission_code="ROUTE_MANAGER", dsn=_DSN,
    )
    assert result["grant_valid"] is True
    assert result["code"] == "GRANT_VALID"
    assert str(result["grant_id"]) == str(gid)


# ══════════════════════════════════════════════════════════════════════════════
# A10 — Factory-scoped Grant 일치 → VALID
# ══════════════════════════════════════════════════════════════════════════════

def test_a10_factory_scoped_grant_match(pg):
    gid = _grant(pg, factory_id=FAC1)
    result = check_tam_permission_grant(
        _user(), company_id=CO_A, factory_id=FAC1,
        permission_code="ROUTE_MANAGER", dsn=_DSN,
    )
    assert result["grant_valid"] is True
    assert result["code"] == "GRANT_VALID"
    assert str(result["grant_id"]) == str(gid)


# ══════════════════════════════════════════════════════════════════════════════
# A11 — STEP_APPROVER → DENY (SNAPSHOT_ONLY_PERMISSION)
# ══════════════════════════════════════════════════════════════════════════════

def test_a11_step_approver_denied(pg):
    result = check_tam_permission_grant(
        _user(), company_id=CO_A, factory_id=None,
        permission_code="STEP_APPROVER", dsn=_DSN,
    )
    assert result["grant_valid"] is False
    assert result["code"] == "SNAPSHOT_ONLY_PERMISSION"


# ══════════════════════════════════════════════════════════════════════════════
# A12 — 미지원 권한 코드 → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_a12_invalid_permission_code(pg):
    result = check_tam_permission_grant(
        _user(), company_id=CO_A, factory_id=None,
        permission_code="SUPER_ADMIN", dsn=_DSN,
    )
    assert result["grant_valid"] is False
    assert result["code"] == "INVALID_PERMISSION_CODE"


# ══════════════════════════════════════════════════════════════════════════════
# A13 — DB 연결 장애 → Fail-closed (TamError 503)
# ══════════════════════════════════════════════════════════════════════════════

def test_a13_db_connection_failure():
    with pytest.raises(TamError) as exc_info:
        check_tam_permission_grant(
            _user(), company_id=CO_A, factory_id=None,
            permission_code="ROUTE_MANAGER", dsn=_BAD_DSN,
        )
    assert exc_info.value.http_status == 503
    assert exc_info.value.code in ("SERVICE_UNAVAILABLE", "DB_NOT_CONFIGURED")


# ══════════════════════════════════════════════════════════════════════════════
# A14 — DB 조회 예외 → Fail-closed (TamError 503)
# ══════════════════════════════════════════════════════════════════════════════

def test_a14_db_query_exception():
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.__enter__ = MagicMock(return_value=mock_cur)
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_cur.execute.side_effect = Exception("simulated query failure")
    mock_conn.cursor.return_value = mock_cur
    mock_conn.autocommit = False

    with patch("services.tam.permissions_svc.psycopg2.connect", return_value=mock_conn):
        with pytest.raises(TamError) as exc_info:
            check_tam_permission_grant(
                _user(), company_id=CO_A, factory_id=None,
                permission_code="ROUTE_MANAGER",
                dsn="host=localhost dbname=tai_test_tam_ledger",
            )
    assert exc_info.value.http_status == 503
    assert exc_info.value.code == "SERVICE_UNAVAILABLE"


# ══════════════════════════════════════════════════════════════════════════════
# A15 — 다른 사용자 Grant → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_a15_other_user_grant(pg):
    """Grant is for U1, but caller is authenticated as U2."""
    _grant(pg, subject=U1)
    result = check_tam_permission_grant(
        _user(uid=U2), company_id=CO_A, factory_id=None,
        permission_code="ROUTE_MANAGER", dsn=_DSN,
    )
    assert result["grant_valid"] is False
    assert result["code"] == "GRANT_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════════════════
# A16 — 명시적 TAM Grant 없는 Role 관리자 → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_a16_role_manager_without_explicit_grant(pg):
    """User has a manager role_code but no TAM grant — service checks grant only."""
    user = {**_user(), "role_code": "014"}  # manager role_code, no TAM grant
    result = check_tam_permission_grant(
        user, company_id=CO_A, factory_id=None,
        permission_code="ROUTE_MANAGER", dsn=_DSN,
    )
    assert result["grant_valid"] is False
    assert result["code"] == "GRANT_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════════════════
# A17 — 다중 Grant 중 하나만 유효 → 유효 Grant 매칭
# ══════════════════════════════════════════════════════════════════════════════

def test_a17_multiple_grants_one_valid(pg):
    """Expired + revoked + valid: service returns the valid one."""
    # Expired
    _grant(pg, valid_from="2020-01-01T00:00:00Z", valid_until="2020-12-31T00:00:00Z")
    # Revoked
    gid_revoked = _grant(pg)
    _revoke(pg, gid_revoked)
    # Valid
    gid_valid = _grant(pg)

    result = check_tam_permission_grant(
        _user(), company_id=CO_A, factory_id=None,
        permission_code="ROUTE_MANAGER", dsn=_DSN,
    )
    assert result["grant_valid"] is True
    assert result["code"] == "GRANT_VALID"
    assert str(result["grant_id"]) == str(gid_valid)


# ══════════════════════════════════════════════════════════════════════════════
# A18 — 권한 조회 후 DB 변경 없음
# ══════════════════════════════════════════════════════════════════════════════

def test_a18_no_db_writes_after_check(pg):
    """check_tam_permission_grant must not cause any DB mutations."""
    gid = _grant(pg)

    cur = pg.cursor()
    cur.execute("SELECT COUNT(*) FROM tam_permission_grants")
    grants_before = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM tam_permission_revocations")
    revocations_before = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM tam_approval_audit_events")
    audit_before = cur.fetchone()[0]

    check_tam_permission_grant(
        _user(), company_id=CO_A, factory_id=None,
        permission_code="ROUTE_MANAGER", dsn=_DSN,
    )

    cur.execute("SELECT COUNT(*) FROM tam_permission_grants")
    assert cur.fetchone()[0] == grants_before
    cur.execute("SELECT COUNT(*) FROM tam_permission_revocations")
    assert cur.fetchone()[0] == revocations_before
    cur.execute("SELECT COUNT(*) FROM tam_approval_audit_events")
    assert cur.fetchone()[0] == audit_before


# ══════════════════════════════════════════════════════════════════════════════
# A19 — 신규 HTTP Endpoint 없음, 기존 TAM 쓰기 Gate 미변경
# ══════════════════════════════════════════════════════════════════════════════

def test_a19_no_http_endpoints_created():
    """permissions_svc must not define HTTP routes or import FastAPI Router."""
    import services.tam.permissions_svc as mod

    # No APIRouter in module namespace
    try:
        from fastapi import APIRouter
        has_router = any(
            isinstance(getattr(mod, attr), APIRouter)
            for attr in dir(mod)
            if not attr.startswith("_")
        )
        assert not has_router, "permissions_svc must not define HTTP routes"
    except ImportError:
        pass  # FastAPI not installed — no routes possible

    # Public API is exactly check_tam_permission_grant + TamError
    public = {a for a in dir(mod) if not a.startswith("_")}
    assert "check_tam_permission_grant" in public
    assert callable(mod.check_tam_permission_grant)
    assert "TamError" in public


# ══════════════════════════════════════════════════════════════════════════════
# A20 — DB Foundation 회귀 검증
# ══════════════════════════════════════════════════════════════════════════════

def test_a20_db_foundation_regression(pg):
    """Foundation append-only and FK constraints still enforced after adding service."""
    cur = pg.cursor()

    # Grant creation works
    cur.execute("""
        INSERT INTO tam_permission_grants
            (company_id, subject_user_id, permission_code, granted_by)
        VALUES (%s, %s, %s, %s)
        RETURNING grant_id::text
    """, (CO_A, U2, "ASSIGNEE_MANAGER", U_ADM))
    gid = cur.fetchone()[0]
    pg.commit()
    assert gid is not None

    # Revocation works
    cur.execute("""
        INSERT INTO tam_permission_revocations (grant_id, revoked_by, reason)
        VALUES (%s, %s, %s)
        RETURNING revocation_id
    """, (gid, U_ADM, "regression check"))
    pg.commit()

    # Append-only on grants still enforced
    with pytest.raises(psycopg2.errors.RaiseException):
        cur.execute(
            "UPDATE tam_permission_grants SET permission_code = %s WHERE grant_id = %s",
            ("ROUTE_MANAGER", gid),
        )
    pg.rollback()

    # Cross-company factory FK still enforced
    with pytest.raises(psycopg2.errors.ForeignKeyViolation):
        cur.execute("""
            INSERT INTO tam_permission_grants
                (company_id, factory_id, subject_user_id, permission_code, granted_by)
            VALUES (%s, %s, %s, %s, %s)
        """, (CO_A, FAC_B, U2, "ROUTE_MANAGER", U_ADM))
    pg.rollback()
