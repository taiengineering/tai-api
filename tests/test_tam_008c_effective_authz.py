"""TAM-008C-006 — Effective Authorization Integration tests.

C01–C26 contract tests for check_tam_effective_authorization().

C01–C24: authz_svc contract
C25: regression — check_tam_permission_grant still works
C26: regression — DB Foundation append-only + FK still enforced

Test environment:
  Isolated PostgreSQL (TAM_008C_PG_DSN).
  Module-scoped fixture creates all required stubs + Foundation migration.

Design anchor: c388a7f6
"""
from __future__ import annotations

import os
import pathlib
from unittest.mock import MagicMock, patch

import psycopg2
import psycopg2.errors
import pytest

from services.tam.authz_svc import check_tam_effective_authorization
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

CO_A  = "aaaaaaaa-0001-0001-0001-000000000001"
CO_B  = "bbbbbbbb-0002-0002-0002-000000000002"

FAC1         = "ffffffff-0001-0001-0001-000000000001"   # CO_A, ACTIVE
FAC2         = "ffffffff-0002-0002-0002-000000000002"   # CO_A, ACTIVE
FAC_B        = "ffffffff-0003-0003-0003-000000000003"   # CO_B, ACTIVE
FAC_SOFT_DEL = "ffffffff-0004-0004-0004-000000000004"   # CO_A, ACTIVE but deleted_at set

TEAM1 = "cccccccc-0001-0001-0001-000000000001"
TEAM2 = "cccccccc-0002-0002-0002-000000000002"

U_COMPANY  = "11111111-0001-0001-0001-000000000001"  # CO_A, COMPANY scope
U_FACTORY  = "11111111-0002-0002-0002-000000000002"  # CO_A, FACTORY scope, FAC1
U_TEAM     = "11111111-0003-0003-0003-000000000003"  # CO_A, TEAM scope, FAC1, TEAM1
U_ALL      = "11111111-0004-0004-0004-000000000004"  # CO_A, ALL scope
U_ASSIGNED = "11111111-0005-0005-0005-000000000005"  # CO_A, ASSIGNED scope
U_INACTIVE = "11111111-0006-0006-0006-000000000006"  # CO_A, INACTIVE
U_NO_ROLE  = "11111111-0007-0007-0007-000000000007"  # CO_A, NULL role_code
U_ADM      = "00000000-0000-0000-0000-000000000001"   # granter


def _pg_available() -> bool:
    try:
        c = psycopg2.connect(_DSN, connect_timeout=2)
        c.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _pg_available(), reason="PostgreSQL unavailable")

# ── User / resource helpers ───────────────────────────────────────────────────


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


def _res(
    company_id: str = CO_A,
    factory_id=None,
    team_id=None,
    rid: str = "dddddddd-0001-0001-0001-000000000001",
) -> dict:
    return {
        "id": rid,
        "company_id": company_id,
        "factory_id": factory_id,
        "team_id": team_id,
    }


# ── Module-scoped DB fixture ──────────────────────────────────────────────────

@pytest.fixture(scope="module")
def pg():
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
        INSERT INTO factories (id, company_id, status_code, deleted_at) VALUES
        (%s, %s, 'ACTIVE',   NULL),
        (%s, %s, 'ACTIVE',   NULL),
        (%s, %s, 'ACTIVE',   NULL),
        (%s, %s, 'ACTIVE',   '2020-01-01')
    """, (FAC1, CO_A, FAC2, CO_A, FAC_B, CO_B, FAC_SOFT_DEL, CO_A))

    cur.execute("""
        INSERT INTO users
            (id, company_id, status_code, is_active, role_code, factory_id, team_id)
        VALUES
        (%s, %s, 'ACTIVE',   true,  'COMPANY_ROLE',  NULL,  NULL),
        (%s, %s, 'ACTIVE',   true,  'FACTORY_ROLE',  %s,    NULL),
        (%s, %s, 'ACTIVE',   true,  'TEAM_ROLE',     %s,    %s),
        (%s, %s, 'ACTIVE',   true,  'ALL_ROLE',      NULL,  NULL),
        (%s, %s, 'ACTIVE',   true,  'ASSIGNED_ROLE', %s,    NULL),
        (%s, %s, 'INACTIVE', false, 'COMPANY_ROLE',  NULL,  NULL),
        (%s, %s, 'ACTIVE',   true,  NULL,            NULL,  NULL),
        (%s, %s, 'ACTIVE',   true,  'COMPANY_ROLE',  NULL,  NULL)
    """, (
        U_COMPANY, CO_A,
        U_FACTORY, CO_A, FAC1,
        U_TEAM,    CO_A, FAC1, TEAM1,
        U_ALL,     CO_A,
        U_ASSIGNED,CO_A, FAC1,
        U_INACTIVE,CO_A,
        U_NO_ROLE, CO_A,
        U_ADM,     CO_A,
    ))

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

def _grant(
    pg,
    *,
    company_id=CO_A,
    factory_id=None,
    subject=U_COMPANY,
    permission="ROUTE_MANAGER",
    granter=U_ADM,
    valid_from="CURRENT_TIMESTAMP",
    valid_until=None,
) -> str:
    cur = pg.cursor()
    vf = "CURRENT_TIMESTAMP" if valid_from == "CURRENT_TIMESTAMP" else f"'{valid_from}'"
    vu = "NULL" if valid_until is None else f"'{valid_until}'"
    fid = "NULL" if factory_id is None else f"'{factory_id}'"
    cur.execute(f"""
        INSERT INTO tam_permission_grants
            (company_id, factory_id, subject_user_id, permission_code, granted_by,
             valid_from, valid_until)
        VALUES
            ('{company_id}', {fid}, '{subject}', '{permission}', '{granter}',
             {vf}, {vu})
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
    """, (grant_id, U_ADM, "test revocation"))
    pg.commit()


# ══════════════════════════════════════════════════════════════════════════════
# C01 — COMPANY + 유효 Grant + 같은 회사 → ALLOW
# ══════════════════════════════════════════════════════════════════════════════

def test_c01_company_scope_valid_grant(pg):
    gid = _grant(pg, subject=U_COMPANY)
    result = check_tam_effective_authorization(
        _user(U_COMPANY, role_code="COMPANY_ROLE"),
        resource=_res(),
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is True
    assert result["code"] == "AUTHORIZED"
    assert str(result["grant_id"]) == gid


# ══════════════════════════════════════════════════════════════════════════════
# C02 — COMPANY + Grant 없음 → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_c02_company_scope_no_grant(pg):
    result = check_tam_effective_authorization(
        _user(U_COMPANY, role_code="COMPANY_ROLE"),
        resource=_res(),
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is False
    assert result["code"] == "GRANT_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════════════════
# C03 — COMPANY + 철회된 Grant → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_c03_revoked_grant(pg):
    gid = _grant(pg, subject=U_COMPANY)
    _revoke(pg, gid)
    result = check_tam_effective_authorization(
        _user(U_COMPANY, role_code="COMPANY_ROLE"),
        resource=_res(),
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is False
    assert result["code"] == "GRANT_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════════════════
# C04 — ALL + 다른 회사 객체 → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_c04_all_scope_cross_company(pg):
    _grant(pg, subject=U_ALL)
    result = check_tam_effective_authorization(
        _user(U_ALL, role_code="ALL_ROLE"),
        resource=_res(company_id=CO_B),
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is False
    assert result["code"] == "COMPANY_MISMATCH"


# ══════════════════════════════════════════════════════════════════════════════
# C05 — ALL + TAM Grant 없음 → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_c05_all_scope_no_grant(pg):
    result = check_tam_effective_authorization(
        _user(U_ALL, role_code="ALL_ROLE"),
        resource=_res(),
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is False
    assert result["code"] == "GRANT_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════════════════
# C06 — FACTORY + 동일 사업장 → ALLOW
# ══════════════════════════════════════════════════════════════════════════════

def test_c06_factory_scope_same_factory(pg):
    gid = _grant(pg, factory_id=FAC1, subject=U_FACTORY)
    result = check_tam_effective_authorization(
        _user(U_FACTORY, role_code="FACTORY_ROLE", factory_id=FAC1),
        resource=_res(factory_id=FAC1),
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is True
    assert result["code"] == "AUTHORIZED"
    assert str(result["grant_id"]) == gid


# ══════════════════════════════════════════════════════════════════════════════
# C07 — FACTORY + 다른 사업장 → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_c07_factory_scope_different_factory(pg):
    _grant(pg, factory_id=FAC1, subject=U_FACTORY)
    result = check_tam_effective_authorization(
        _user(U_FACTORY, role_code="FACTORY_ROLE", factory_id=FAC1),
        resource=_res(factory_id=FAC2),
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is False
    assert result["code"] == "FACTORY_SCOPE_MISMATCH"


# ══════════════════════════════════════════════════════════════════════════════
# C08 — FACTORY + Company-wide 객체 → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_c08_factory_scope_company_wide_resource(pg):
    _grant(pg, subject=U_FACTORY)
    result = check_tam_effective_authorization(
        _user(U_FACTORY, role_code="FACTORY_ROLE", factory_id=FAC1),
        resource=_res(factory_id=None),
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is False
    assert result["code"] == "FACTORY_SCOPE_MISMATCH"


# ══════════════════════════════════════════════════════════════════════════════
# C09 — TEAM + 동일 Factory/Team → ALLOW
# ══════════════════════════════════════════════════════════════════════════════

def test_c09_team_scope_same_factory_team(pg):
    gid = _grant(pg, factory_id=FAC1, subject=U_TEAM)
    result = check_tam_effective_authorization(
        _user(U_TEAM, role_code="TEAM_ROLE", factory_id=FAC1, team_id=TEAM1),
        resource=_res(factory_id=FAC1, team_id=TEAM1),
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is True
    assert result["code"] == "AUTHORIZED"
    assert str(result["grant_id"]) == gid


# ══════════════════════════════════════════════════════════════════════════════
# C10 — TEAM + 다른 Team → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_c10_team_scope_different_team(pg):
    _grant(pg, factory_id=FAC1, subject=U_TEAM)
    result = check_tam_effective_authorization(
        _user(U_TEAM, role_code="TEAM_ROLE", factory_id=FAC1, team_id=TEAM1),
        resource=_res(factory_id=FAC1, team_id=TEAM2),
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is False
    assert result["code"] == "TEAM_SCOPE_MISMATCH"


# ══════════════════════════════════════════════════════════════════════════════
# C11 — TEAM + Team 범위 없는 동일 Factory 객체 → ALLOW
# ══════════════════════════════════════════════════════════════════════════════

def test_c11_team_scope_no_team_on_resource(pg):
    gid = _grant(pg, factory_id=FAC1, subject=U_TEAM)
    result = check_tam_effective_authorization(
        _user(U_TEAM, role_code="TEAM_ROLE", factory_id=FAC1, team_id=TEAM1),
        resource=_res(factory_id=FAC1, team_id=None),
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is True
    assert result["code"] == "AUTHORIZED"
    assert str(result["grant_id"]) == gid


# ══════════════════════════════════════════════════════════════════════════════
# C12 — TEAM + Company-wide 객체 → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_c12_team_scope_company_wide_resource(pg):
    result = check_tam_effective_authorization(
        _user(U_TEAM, role_code="TEAM_ROLE", factory_id=FAC1, team_id=TEAM1),
        resource=_res(factory_id=None, team_id=None),
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is False
    assert result["code"] == "FACTORY_SCOPE_MISMATCH"


# ══════════════════════════════════════════════════════════════════════════════
# C13 — ASSIGNED Scope → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_c13_assigned_scope_denied(pg):
    result = check_tam_effective_authorization(
        _user(U_ASSIGNED, role_code="ASSIGNED_ROLE", factory_id=FAC1),
        resource=_res(factory_id=FAC1),
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is False
    assert result["code"] == "ASSIGNMENT_SCOPE_NOT_READY"


# ══════════════════════════════════════════════════════════════════════════════
# C14 — Role Scope 미정의 → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_c14_role_scope_undefined(pg):
    result = check_tam_effective_authorization(
        _user(U_COMPANY, role_code="NONEXISTENT_ROLE"),
        resource=_res(),
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is False
    assert result["code"] == "ROLE_SCOPE_UNDEFINED"


# ══════════════════════════════════════════════════════════════════════════════
# C15 — Role Scope DB 조회 실패 → 503
# ══════════════════════════════════════════════════════════════════════════════

def test_c15_scope_db_failure_raises_503(pg):
    import services.tam.authz_svc as mod
    with patch.object(mod, "_connect", side_effect=TamError(503, "SERVICE_UNAVAILABLE", "test")):
        with pytest.raises(TamError) as exc_info:
            check_tam_effective_authorization(
                _user(U_COMPANY, role_code="COMPANY_ROLE"),
                resource=_res(),
                permission_code="ROUTE_MANAGER",
                dsn=_BAD_DSN,
            )
    assert exc_info.value.http_status == 503


# ══════════════════════════════════════════════════════════════════════════════
# C16 — 비활성 사용자 → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_c16_inactive_user(pg):
    result = check_tam_effective_authorization(
        _user(U_INACTIVE, role_code="COMPANY_ROLE", status_code="INACTIVE", is_active=False),
        resource=_res(),
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is False
    assert result["code"] == "USER_INACTIVE"


# ══════════════════════════════════════════════════════════════════════════════
# C17 — 유효하지 않은 Factory 회사 소속 → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_c17_factory_wrong_company_ownership(pg):
    # FAC_B belongs to CO_B; resource claims CO_A with factory=FAC_B
    result = check_tam_effective_authorization(
        _user(U_COMPANY, role_code="COMPANY_ROLE"),
        resource=_res(company_id=CO_A, factory_id=FAC_B),
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is False
    assert result["code"] == "FACTORY_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════════════════
# C18 — 소프트 삭제 Factory → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_c18_soft_deleted_factory(pg):
    result = check_tam_effective_authorization(
        _user(U_COMPANY, role_code="COMPANY_ROLE"),
        resource=_res(factory_id=FAC_SOFT_DEL),
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is False
    assert result["code"] == "FACTORY_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════════════════
# C19 — TAM Grant 만료 → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_c19_expired_grant(pg):
    _grant(pg, subject=U_COMPANY,
           valid_from="2020-01-01", valid_until="2020-12-31")
    result = check_tam_effective_authorization(
        _user(U_COMPANY, role_code="COMPANY_ROLE"),
        resource=_res(),
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is False
    assert result["code"] == "GRANT_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════════════════
# C20 — STEP_APPROVER → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_c20_step_approver_denied(pg):
    _grant(pg, subject=U_COMPANY, permission="ROUTE_MANAGER")
    result = check_tam_effective_authorization(
        _user(U_COMPANY, role_code="COMPANY_ROLE"),
        resource=_res(),
        permission_code="STEP_APPROVER",
        dsn=_DSN,
    )
    assert result["authorized"] is False
    assert result["code"] == "SNAPSHOT_ONLY_PERMISSION"


# ══════════════════════════════════════════════════════════════════════════════
# C21 — Resource 필수 Scope 누락 → DENY
# ══════════════════════════════════════════════════════════════════════════════

def test_c21_resource_missing_required_key(pg):
    incomplete = {"id": "dddddddd-0001-0001-0001-000000000001",
                  "company_id": CO_A, "factory_id": None}  # team_id missing
    result = check_tam_effective_authorization(
        _user(U_COMPANY, role_code="COMPANY_ROLE"),
        resource=incomplete,
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is False
    assert result["code"] == "RESOURCE_SCOPE_MISSING"


# ══════════════════════════════════════════════════════════════════════════════
# C22 — Core 범위 통과, TAM 권한 실패 → DENY
# (Core scope passes; TAM grant absent — two distinct conditions clearly separated)
# ══════════════════════════════════════════════════════════════════════════════

def test_c22_scope_pass_tam_fail(pg):
    # No grant inserted
    result = check_tam_effective_authorization(
        _user(U_COMPANY, role_code="COMPANY_ROLE"),
        resource=_res(),
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is False
    assert result["code"] == "GRANT_NOT_FOUND"  # TAM leg failed, not scope


# ══════════════════════════════════════════════════════════════════════════════
# C23 — Core 범위 실패, TAM Grant 유효 → DENY
# (TAM grant exists but scope check blocks first — TAM grant is never queried)
# ══════════════════════════════════════════════════════════════════════════════

def test_c23_scope_fail_tam_grant_present(pg):
    # Grant for FAC1; user has FACTORY scope for FAC1 but resource says FAC2
    _grant(pg, factory_id=FAC1, subject=U_FACTORY)
    result = check_tam_effective_authorization(
        _user(U_FACTORY, role_code="FACTORY_ROLE", factory_id=FAC1),
        resource=_res(factory_id=FAC2),
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is False
    assert result["code"] == "FACTORY_SCOPE_MISMATCH"  # scope blocked, not TAM


# ══════════════════════════════════════════════════════════════════════════════
# C24 — 읽기 수행 후 DB 원장 변경 없음
# ══════════════════════════════════════════════════════════════════════════════

def test_c24_no_db_writes_after_authorization(pg):
    gid = _grant(pg, subject=U_COMPANY)

    cur = pg.cursor()
    cur.execute("SELECT COUNT(*) FROM tam_permission_grants")
    grants_before = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM tam_permission_revocations")
    revocations_before = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM tam_approval_audit_events")
    audit_before = cur.fetchone()[0]

    result = check_tam_effective_authorization(
        _user(U_COMPANY, role_code="COMPANY_ROLE"),
        resource=_res(),
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["authorized"] is True

    cur.execute("SELECT COUNT(*) FROM tam_permission_grants")
    assert cur.fetchone()[0] == grants_before
    cur.execute("SELECT COUNT(*) FROM tam_permission_revocations")
    assert cur.fetchone()[0] == revocations_before
    cur.execute("SELECT COUNT(*) FROM tam_approval_audit_events")
    assert cur.fetchone()[0] == audit_before


# ══════════════════════════════════════════════════════════════════════════════
# C25 — 기존 TAM Permission Read 회귀 검증
# ══════════════════════════════════════════════════════════════════════════════

def test_c25_permission_read_regression(pg):
    """check_tam_permission_grant still works after authz_svc addition."""
    gid = _grant(pg, subject=U_COMPANY)

    result = check_tam_permission_grant(
        {"id": U_COMPANY, "company_id": CO_A, "status_code": "ACTIVE", "is_active": True},
        company_id=CO_A,
        factory_id=None,
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result["grant_valid"] is True
    assert str(result["grant_id"]) == gid

    # Revoke and verify DENY
    _revoke(pg, gid)
    result2 = check_tam_permission_grant(
        {"id": U_COMPANY, "company_id": CO_A, "status_code": "ACTIVE", "is_active": True},
        company_id=CO_A,
        factory_id=None,
        permission_code="ROUTE_MANAGER",
        dsn=_DSN,
    )
    assert result2["grant_valid"] is False
    assert result2["code"] == "GRANT_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════════════════
# C26 — 기존 TAM DB Foundation 회귀 검증
# ══════════════════════════════════════════════════════════════════════════════

def test_c26_db_foundation_regression(pg):
    """Foundation append-only and FK constraints still enforced."""
    cur = pg.cursor()

    # Grant creation works
    cur.execute("""
        INSERT INTO tam_permission_grants
            (company_id, subject_user_id, permission_code, granted_by)
        VALUES (%s, %s, %s, %s)
        RETURNING grant_id::text
    """, (CO_A, U_COMPANY, "ASSIGNEE_MANAGER", U_ADM))
    gid = cur.fetchone()[0]
    pg.commit()
    assert gid is not None

    # Append-only: UPDATE blocked
    with pytest.raises(psycopg2.errors.RaiseException):
        cur.execute(
            "UPDATE tam_permission_grants SET permission_code = %s WHERE grant_id = %s",
            ("ROUTE_MANAGER", gid),
        )
    pg.rollback()

    # Composite FK: cross-company factory rejected
    with pytest.raises(psycopg2.errors.ForeignKeyViolation):
        cur.execute("""
            INSERT INTO tam_permission_grants
                (company_id, factory_id, subject_user_id, permission_code, granted_by)
            VALUES (%s, %s, %s, %s, %s)
        """, (CO_A, FAC_B, U_COMPANY, "ROUTE_MANAGER", U_ADM))
    pg.rollback()
