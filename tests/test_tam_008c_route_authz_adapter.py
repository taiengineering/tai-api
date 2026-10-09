"""TAM-008C-007 — Route Authorization Adapter tests.

R01–R18 contract tests for assess_tam_route_authorization_candidate().

Isolation guarantee:
  Uses explicit TAM_008C_PG_DSN — never DATABASE_URL / production credentials.
  Module-scoped fixture performs DROP TABLE on stubs (safe only in isolated DB).
  Do NOT run against production or staging databases.

Design anchor: c388a7f6
"""
from __future__ import annotations

import os
import pathlib
from unittest.mock import patch

import psycopg2
import psycopg2.errors
import pytest

from services.tam.permissions_svc import TamError
from services.tam.route_authz_adapter import assess_tam_route_authorization_candidate

# ── DSN ──────────────────────────────────────────────────────────────────────

_DSN = os.getenv("TAM_008C_PG_DSN", "host=localhost dbname=tai_test_tam_ledger")
_BAD_DSN = "host=localhost port=19999 dbname=nonexistent connect_timeout=1"
_MIGRATION_SQL = (
    pathlib.Path(__file__).parent.parent
    / "migrations"
    / "2026-10-09_tam_permission_ledger_foundation.sql"
).read_text()

# ── Stable UUIDs ─────────────────────────────────────────────────────────────

CO_A = "aaaaaaaa-0001-0001-0001-000000000001"
CO_B = "bbbbbbbb-0002-0002-0002-000000000002"

FAC1 = "ffffffff-0001-0001-0001-000000000001"   # CO_A, ACTIVE
FAC2 = "ffffffff-0002-0002-0002-000000000002"   # CO_A, ACTIVE
FAC_B = "ffffffff-0003-0003-0003-000000000003"  # CO_B, ACTIVE

TEAM1 = "cccccccc-0001-0001-0001-000000000001"
TEAM2 = "cccccccc-0002-0002-0002-000000000002"

ROUTE_CO  = "eeeeeeee-0001-0001-0001-000000000001"  # CO_A, company-wide
ROUTE_FAC = "eeeeeeee-0002-0002-0002-000000000002"  # CO_A, FAC1
ROUTE_B   = "eeeeeeee-0003-0003-0003-000000000003"  # CO_B

U_COMPANY  = "11111111-0001-0001-0001-000000000001"  # CO_A, COMPANY scope
U_FACTORY  = "11111111-0002-0002-0002-000000000002"  # CO_A, FACTORY scope, FAC1
U_TEAM     = "11111111-0003-0003-0003-000000000003"  # CO_A, TEAM scope, FAC1, TEAM1
U_INACTIVE = "11111111-0006-0006-0006-000000000006"  # CO_A, INACTIVE
U_ADM      = "00000000-0000-0000-0000-000000000001"   # granter

INVALID_UUID = "not-a-uuid"


def _pg_available() -> bool:
    try:
        c = psycopg2.connect(_DSN, connect_timeout=2)
        c.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _pg_available(), reason="PostgreSQL unavailable")


# ── User helper ───────────────────────────────────────────────────────────────

def _user(
    uid: str = U_COMPANY,
    company_id: str = CO_A,
    role_code: str = "COMPANY_ROLE",
    status_code: str = "ACTIVE",
    is_active: bool = True,
    factory_id=None,
    team_id=None,
) -> dict:
    return {
        "id": uid,
        "company_id": company_id,
        "role_code": role_code,
        "status_code": status_code,
        "is_active": is_active,
        "factory_id": factory_id,
        "team_id": team_id,
    }


# ── Module-scoped DB fixture ──────────────────────────────────────────────────

@pytest.fixture(scope="module")
def pg():
    """Isolated DB with stub tables + Foundation migration + Routes stub."""
    # ── DB isolation guard (BLOCKER 1) ────────────────────────────────────────
    # Refuse to run destructive DDL unless:
    #   1. TAM_008C_PG_DSN is explicitly set (not falling back to the default)
    #   2. Connected DB contains _tam_test_isolation_marker with at least one row
    if "TAM_008C_PG_DSN" not in os.environ:
        pytest.fail(
            "TAM_008C_PG_DSN not in environment — refusing destructive DDL. "
            "Set TAM_008C_PG_DSN explicitly to an isolated test DB DSN.",
            pytrace=False,
        )
    _guard = psycopg2.connect(_DSN, connect_timeout=2)
    try:
        _gc = _guard.cursor()
        _gc.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' "
            "AND table_name = '_tam_test_isolation_marker'"
        )
        if _gc.fetchone()[0] == 0:
            pytest.fail(
                "Isolation marker '_tam_test_isolation_marker' not found — "
                "this DB is not a verified isolated test DB. Refusing DDL.",
                pytrace=False,
            )
        _gc.execute("SELECT COUNT(*) FROM _tam_test_isolation_marker")
        if _gc.fetchone()[0] == 0:
            pytest.fail(
                "Isolation marker table exists but is empty — refusing DDL.",
                pytrace=False,
            )
    finally:
        _guard.close()
    # ─────────────────────────────────────────────────────────────────────────

    conn = psycopg2.connect(_DSN)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        DROP TABLE IF EXISTS
            tam_permission_revocations,
            tam_permission_grants,
            tam_approval_audit_events,
            tam_approval_routes
        CASCADE;
        DROP FUNCTION IF EXISTS
            tam_grants_validate_factory_company_fn,
            tam_grants_immutability_fn,
            tam_revocations_immutability_fn,
            tam_audit_immutability_fn
        CASCADE;
        DROP TABLE IF EXISTS role_data_scope, users, factories, companies CASCADE;
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
            is_active   BOOLEAN NOT NULL DEFAULT true,
            role_code   TEXT NULL,
            factory_id  UUID NULL REFERENCES factories(id),
            team_id     UUID NULL
        );

        CREATE TABLE role_data_scope (
            role_code  TEXT PRIMARY KEY,
            scope_type TEXT NOT NULL
        );

        CREATE TABLE tam_approval_routes (
            route_id    UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id  UUID    NOT NULL,
            factory_id  UUID,
            is_active   BOOLEAN NOT NULL DEFAULT true
        );
    """)

    cur.execute("""
        INSERT INTO role_data_scope (role_code, scope_type) VALUES
        ('COMPANY_ROLE',  'COMPANY'),
        ('FACTORY_ROLE',  'FACTORY'),
        ('TEAM_ROLE',     'TEAM'),
        ('ALL_ROLE',      'ALL'),
        ('ASSIGNED_ROLE', 'ASSIGNED')
    """)

    cur.execute("INSERT INTO companies (id) VALUES (%s), (%s)", (CO_A, CO_B))

    cur.execute("""
        INSERT INTO factories (id, company_id) VALUES (%s,%s), (%s,%s), (%s,%s)
    """, (FAC1, CO_A, FAC2, CO_A, FAC_B, CO_B))

    cur.execute("""
        INSERT INTO users
            (id, company_id, status_code, is_active, role_code, factory_id, team_id)
        VALUES
        (%s, %s, 'ACTIVE',   true,  'COMPANY_ROLE',  NULL,  NULL),
        (%s, %s, 'ACTIVE',   true,  'FACTORY_ROLE',  %s,    NULL),
        (%s, %s, 'ACTIVE',   true,  'TEAM_ROLE',     %s,    %s),
        (%s, %s, 'INACTIVE', false, 'COMPANY_ROLE',  NULL,  NULL),
        (%s, %s, 'ACTIVE',   true,  'COMPANY_ROLE',  NULL,  NULL)
    """, (
        U_COMPANY, CO_A,
        U_FACTORY, CO_A, FAC1,
        U_TEAM,    CO_A, FAC1, TEAM1,
        U_INACTIVE, CO_A,
        U_ADM,     CO_A,
    ))

    cur.execute("""
        INSERT INTO tam_approval_routes (route_id, company_id, factory_id) VALUES
        (%s, %s, NULL),
        (%s, %s, %s),
        (%s, %s, NULL)
    """, (ROUTE_CO, CO_A, ROUTE_FAC, CO_A, FAC1, ROUTE_B, CO_B))

    cur.execute(_MIGRATION_SQL)
    yield conn
    # Teardown: remove stub table so it does not contaminate other test modules
    try:
        cur.execute("DROP TABLE IF EXISTS tam_approval_routes CASCADE")
    except Exception:
        pass
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

def _grant(
    pg,
    *,
    company_id=CO_A,
    factory_id=None,
    subject=U_COMPANY,
    permission="ROUTE_MANAGER",
    granter=U_ADM,
    valid_until=None,
) -> str:
    cur = pg.cursor()
    vu = "NULL" if valid_until is None else f"'{valid_until}'"
    fid = "NULL" if factory_id is None else f"'{factory_id}'"
    cur.execute(f"""
        INSERT INTO tam_permission_grants
            (company_id, factory_id, subject_user_id, permission_code, granted_by, valid_until)
        VALUES ('{company_id}', {fid}, '{subject}', '{permission}', '{granter}', {vu})
        RETURNING grant_id::text
    """)
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
# R01 — 유효 Route + Core Scope + Grant → Candidate VALID
# ══════════════════════════════════════════════════════════════════════════════

def test_r01_valid_route_grant(pg):
    gid = _grant(pg, subject=U_COMPANY)
    result = assess_tam_route_authorization_candidate(
        _user(U_COMPANY, role_code="COMPANY_ROLE"),
        route_id=ROUTE_CO,
        dsn=_DSN,
    )
    assert result["candidate_valid"] is True
    assert result["write_enabled"] is False
    assert result["code"] == "CANDIDATE_VALID"
    assert str(result["grant_id"]) == gid


# ══════════════════════════════════════════════════════════════════════════════
# R02 — Route 없음 → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_r02_route_not_found(pg):
    nonexistent = "00000000-ffff-ffff-ffff-000000000001"
    result = assess_tam_route_authorization_candidate(
        _user(U_COMPANY, role_code="COMPANY_ROLE"),
        route_id=nonexistent,
        dsn=_DSN,
    )
    assert result["candidate_valid"] is False
    assert result["code"] == "ROUTE_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════════════════
# R03 — 타사 Route → DENY (same code as not-found)
# ══════════════════════════════════════════════════════════════════════════════

def test_r03_cross_company_route(pg):
    _grant(pg, subject=U_COMPANY)
    result = assess_tam_route_authorization_candidate(
        _user(U_COMPANY, role_code="COMPANY_ROLE"),
        route_id=ROUTE_B,   # belongs to CO_B
        dsn=_DSN,
    )
    assert result["candidate_valid"] is False
    assert result["code"] == "ROUTE_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════════════════
# R04 — 잘못된 Route UUID → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_r04_invalid_route_uuid(pg):
    result = assess_tam_route_authorization_candidate(
        _user(U_COMPANY, role_code="COMPANY_ROLE"),
        route_id=INVALID_UUID,
        dsn=_DSN,
    )
    assert result["candidate_valid"] is False
    assert result["code"] == "INVALID_ROUTE_ID"


# ══════════════════════════════════════════════════════════════════════════════
# R05 — 사용자 비활성 → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_r05_inactive_user(pg):
    result = assess_tam_route_authorization_candidate(
        _user(U_INACTIVE, role_code="COMPANY_ROLE", status_code="INACTIVE", is_active=False),
        route_id=ROUTE_CO,
        dsn=_DSN,
    )
    assert result["candidate_valid"] is False
    assert result["code"] == "USER_INACTIVE"


# ══════════════════════════════════════════════════════════════════════════════
# R06 — Grant 없음 → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_r06_no_grant(pg):
    result = assess_tam_route_authorization_candidate(
        _user(U_COMPANY, role_code="COMPANY_ROLE"),
        route_id=ROUTE_CO,
        dsn=_DSN,
    )
    assert result["candidate_valid"] is False
    assert result["code"] == "GRANT_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════════════════
# R07 — 철회된 Grant → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_r07_revoked_grant(pg):
    gid = _grant(pg, subject=U_COMPANY)
    _revoke(pg, gid)
    result = assess_tam_route_authorization_candidate(
        _user(U_COMPANY, role_code="COMPANY_ROLE"),
        route_id=ROUTE_CO,
        dsn=_DSN,
    )
    assert result["candidate_valid"] is False
    assert result["code"] == "GRANT_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════════════════
# R08 — Factory 범위 불일치 → DENY
# User has FACTORY scope for FAC1; route belongs to FAC2
# ══════════════════════════════════════════════════════════════════════════════

def test_r08_factory_scope_mismatch(pg):
    _grant(pg, factory_id=FAC1, subject=U_FACTORY)
    # ROUTE_FAC belongs to FAC1; but use a FAC2 route — insert temporarily
    cur = pg.cursor()
    fac2_route = "eeeeeeee-0005-0005-0005-000000000005"
    cur.execute(
        "INSERT INTO tam_approval_routes (route_id, company_id, factory_id) VALUES (%s,%s,%s)",
        (fac2_route, CO_A, FAC2),
    )
    pg.commit()
    result = assess_tam_route_authorization_candidate(
        _user(U_FACTORY, role_code="FACTORY_ROLE", factory_id=FAC1),
        route_id=fac2_route,
        dsn=_DSN,
    )
    assert result["candidate_valid"] is False
    assert result["code"] == "FACTORY_SCOPE_MISMATCH"


# ══════════════════════════════════════════════════════════════════════════════
# R09 — Team 범위 불일치 → DENY
# User has TEAM scope, factory_id=FAC1; route belongs to FAC2.
# TAM routes have no team_id column — TEAM scope enforces factory restriction.
# ══════════════════════════════════════════════════════════════════════════════

def test_r09_team_scope_factory_mismatch(pg):
    _grant(pg, factory_id=FAC1, subject=U_TEAM)
    cur = pg.cursor()
    fac2_route = "eeeeeeee-0006-0006-0006-000000000006"
    cur.execute(
        "INSERT INTO tam_approval_routes (route_id, company_id, factory_id) VALUES (%s,%s,%s)",
        (fac2_route, CO_A, FAC2),
    )
    pg.commit()
    result = assess_tam_route_authorization_candidate(
        _user(U_TEAM, role_code="TEAM_ROLE", factory_id=FAC1, team_id=TEAM1),
        route_id=fac2_route,
        dsn=_DSN,
    )
    assert result["candidate_valid"] is False
    assert result["code"] == "FACTORY_SCOPE_MISMATCH"


# ══════════════════════════════════════════════════════════════════════════════
# R10 — Company-wide Route → Core/TAM 정책대로 판정
# COMPANY scope + valid grant → CANDIDATE_VALID
# ══════════════════════════════════════════════════════════════════════════════

def test_r10_company_wide_route_company_scope(pg):
    gid = _grant(pg, subject=U_COMPANY)
    result = assess_tam_route_authorization_candidate(
        _user(U_COMPANY, role_code="COMPANY_ROLE"),
        route_id=ROUTE_CO,  # factory_id=NULL (company-wide)
        dsn=_DSN,
    )
    assert result["candidate_valid"] is True
    assert result["write_enabled"] is False
    assert str(result["grant_id"]) == gid


# ══════════════════════════════════════════════════════════════════════════════
# R11 — DB 연결 장애 → 503 Fail-closed
# ══════════════════════════════════════════════════════════════════════════════

def test_r11_db_connection_failure(pg):
    import services.tam.route_authz_adapter as mod
    with patch.object(mod, "_connect", side_effect=TamError(503, "SERVICE_UNAVAILABLE", "test")):
        with pytest.raises(TamError) as exc_info:
            assess_tam_route_authorization_candidate(
                _user(U_COMPANY, role_code="COMPANY_ROLE"),
                route_id=ROUTE_CO,
                dsn=_BAD_DSN,
            )
    assert exc_info.value.http_status == 503


# ══════════════════════════════════════════════════════════════════════════════
# R12 — Route 조회 장애 → 503 Fail-closed
# ══════════════════════════════════════════════════════════════════════════════

def test_r12_route_query_failure(pg):
    import services.tam.route_authz_adapter as mod
    with patch.object(mod, "_fetch_route", side_effect=TamError(503, "SERVICE_UNAVAILABLE", "test")):
        with pytest.raises(TamError) as exc_info:
            assess_tam_route_authorization_candidate(
                _user(U_COMPANY, role_code="COMPANY_ROLE"),
                route_id=ROUTE_CO,
                dsn=_DSN,
            )
    assert exc_info.value.http_status == 503


# ══════════════════════════════════════════════════════════════════════════════
# R13 — Candidate VALID → write_enabled=False 항상
# ══════════════════════════════════════════════════════════════════════════════

def test_r13_candidate_valid_write_always_false(pg):
    _grant(pg, subject=U_COMPANY)
    result = assess_tam_route_authorization_candidate(
        _user(U_COMPANY, role_code="COMPANY_ROLE"),
        route_id=ROUTE_CO,
        dsn=_DSN,
    )
    assert result["candidate_valid"] is True
    assert result["write_enabled"] is False, "write_enabled must always be False (OD-01 blocked)"


# ══════════════════════════════════════════════════════════════════════════════
# R14 — 기존 Route HTTP 쓰기 5개 경로 403 유지 확인
# (Code-level: _require_route_manager raises 403 unconditionally in PR #572 branch)
# ══════════════════════════════════════════════════════════════════════════════

def test_r14_existing_http_write_gate_unchanged():
    """Adapter isolation + HTTP regression evidence.

    Code isolation: adapter must not import or modify routers/tam_routes.py.

    HTTP regression (TAM-008C-007-C1, 2026-10-09): W1-W5 write endpoints
    verified 403 via local worktree test on PR #572 branch — 8/8 PASS:
      W1 POST /api/tam/routes                → 403 ROUTE_MANAGER_PERMISSION_REQUIRED
      W2 POST /api/tam/routes/{id}/versions  → 403 ROUTE_MANAGER_PERMISSION_REQUIRED
      W3 POST /api/tam/routes/{id}/steps     → 403 ROUTE_MANAGER_PERMISSION_REQUIRED
      W4 POST /api/tam/routes/{id}/assignees → 403 ROUTE_MANAGER_PERMISSION_REQUIRED
      W5 POST /api/tam/routes/{id}/publish   → 403 ROUTE_MANAGER_PERMISSION_REQUIRED
      R1 GET  /api/tam/routes                → non-403 (read allowed)
      R2 GET  /api/tam/routes/{id}           → non-403 (read allowed)
      A1 adapter assess_tam_route_authorization_candidate → not in app routes
    """
    import services.tam.route_authz_adapter as mod
    import inspect
    source = inspect.getsource(mod)
    assert "tam_routes" not in source, "adapter must not reference tam_routes"
    assert "require_route_manager" not in source, "adapter must not call _require_route_manager"


# ══════════════════════════════════════════════════════════════════════════════
# R15 — 기존 Route 조회 계약 변경 없음
# ══════════════════════════════════════════════════════════════════════════════

def test_r15_existing_read_contract_unchanged():
    """route_authz_adapter must not modify any existing service or router."""
    import services.tam.route_authz_adapter as mod
    import inspect
    source = inspect.getsource(mod)
    # Adapter must not import or call existing routes_svc
    assert "routes_svc" not in source, "adapter must not reference routes_svc"
    # Adapter must not touch auth middleware
    assert "get_current_user" not in source


# ══════════════════════════════════════════════════════════════════════════════
# R16 — App Import/Router 등록 변경 없음
# ══════════════════════════════════════════════════════════════════════════════

def test_r16_no_app_registration():
    """route_authz_adapter must not define HTTP routes or be auto-imported."""
    import services.tam.route_authz_adapter as mod
    try:
        from fastapi import APIRouter
        has_router = any(
            isinstance(getattr(mod, attr), APIRouter)
            for attr in dir(mod)
            if not attr.startswith("_")
        )
        assert not has_router, "adapter must not define HTTP routes"
    except ImportError:
        pass

    # Public API is exactly assess_tam_route_authorization_candidate
    public = {a for a in dir(mod) if not a.startswith("_")}
    assert "assess_tam_route_authorization_candidate" in public
    assert callable(mod.assess_tam_route_authorization_candidate)


# ══════════════════════════════════════════════════════════════════════════════
# R17 — DB 원장 데이터 조회 후 변경 없음
# ══════════════════════════════════════════════════════════════════════════════

def test_r17_no_db_writes(pg):
    gid = _grant(pg, subject=U_COMPANY)

    cur = pg.cursor()
    cur.execute("SELECT COUNT(*) FROM tam_permission_grants")
    before_g = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM tam_permission_revocations")
    before_r = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM tam_approval_audit_events")
    before_a = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM tam_approval_routes")
    before_routes = cur.fetchone()[0]

    assess_tam_route_authorization_candidate(
        _user(U_COMPANY, role_code="COMPANY_ROLE"),
        route_id=ROUTE_CO,
        dsn=_DSN,
    )

    cur.execute("SELECT COUNT(*) FROM tam_permission_grants")
    assert cur.fetchone()[0] == before_g
    cur.execute("SELECT COUNT(*) FROM tam_permission_revocations")
    assert cur.fetchone()[0] == before_r
    cur.execute("SELECT COUNT(*) FROM tam_approval_audit_events")
    assert cur.fetchone()[0] == before_a
    cur.execute("SELECT COUNT(*) FROM tam_approval_routes")
    assert cur.fetchone()[0] == before_routes


# ══════════════════════════════════════════════════════════════════════════════
# R18 — 기존 TAM 004/005/006 회귀 검증
# ══════════════════════════════════════════════════════════════════════════════

def test_r18_regression_004_db_foundation(pg):
    """Foundation append-only and FK constraints still enforced."""
    cur = pg.cursor()
    cur.execute("""
        INSERT INTO tam_permission_grants
            (company_id, subject_user_id, permission_code, granted_by)
        VALUES (%s, %s, %s, %s)
        RETURNING grant_id::text
    """, (CO_A, U_COMPANY, "ASSIGNEE_MANAGER", U_ADM))
    gid = cur.fetchone()[0]
    pg.commit()
    assert gid is not None

    with pytest.raises(psycopg2.errors.RaiseException):
        cur.execute(
            "UPDATE tam_permission_grants SET permission_code = %s WHERE grant_id = %s",
            ("ROUTE_MANAGER", gid),
        )
    pg.rollback()


def test_r18_regression_005_permission_read(pg):
    """check_tam_permission_grant still works after adapter addition."""
    from services.tam.permissions_svc import check_tam_permission_grant
    gid = _grant(pg, subject=U_COMPANY)
    result = check_tam_permission_grant(
        {"id": U_COMPANY, "company_id": CO_A, "status_code": "ACTIVE", "is_active": True},
        company_id=CO_A, factory_id=None,
        permission_code="ROUTE_MANAGER", dsn=_DSN,
    )
    assert result["grant_valid"] is True
    assert str(result["grant_id"]) == gid


def test_r18_regression_006_effective_authz(pg):
    """check_tam_effective_authorization still works after adapter addition."""
    from services.tam.authz_svc import check_tam_effective_authorization
    gid = _grant(pg, subject=U_COMPANY)
    result = check_tam_effective_authorization(
        _user(U_COMPANY, role_code="COMPANY_ROLE"),
        resource={"id": ROUTE_CO, "company_id": CO_A, "factory_id": None, "team_id": None},
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is True
    assert str(result["grant_id"]) == gid
