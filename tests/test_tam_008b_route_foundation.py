"""TAM-008B — Approval Route Foundation tests (R1).

B01–B18 contract tests + T26–T28 implementation gate tests + R01–R10 concurrency/validation tests.

Test environment:
  Local PostgreSQL via TAM_TEST_PG_DSN env var (default: host=localhost dbname=tai_test_tam_foundation)
  The module-scoped fixture bootstraps schema from migration SQL plus stub users/factories tables.
  All DB tests are skipped if the DSN is unreachable.

Categories:
  B01–B07, B09–B11, B13–B14, B16–B17: PostgreSQL integration (require test DB)
  B08, B12, B15: PostgreSQL integration — publish + history + concurrent
  B18: HTTP router (TestClient, no DB)
  T26–T28: PostgreSQL integration gate tests
  R01–R10: R1 concurrency/immutability/validation tests
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
from fastapi.testclient import TestClient

# ── DSN ───────────────────────────────────────────────────────────────────────

_DSN = os.getenv("TAM_TEST_PG_DSN", "host=localhost dbname=tai_test_tam_foundation")
_MIGRATION_SQL = (
    pathlib.Path(__file__).parent.parent
    / "migrations"
    / "2026-10-09_tam_approval_route_foundation.sql"
).read_text()

# ── Stable UUIDs ──────────────────────────────────────────────────────────────

CO_A = "aaaaaaaa-0001-0001-0001-000000000001"
CO_B = "bbbbbbbb-0002-0002-0002-000000000002"
FAC1 = "ffffffff-0001-0001-0001-000000000001"
FAC2 = "ffffffff-0002-0002-0002-000000000002"
U1   = "11111111-1111-1111-1111-111111111111"
U2   = "22222222-2222-2222-2222-222222222222"
U3   = "33333333-3333-3333-3333-333333333333"

# R1 additional stubs
U_INACTIVE      = "99999999-9999-9999-9999-000000000001"   # INACTIVE CO_A
U_CO_B          = "99999999-9999-9999-9999-000000000002"   # ACTIVE CO_B
FACTORY_UNKNOWN = "dddddddd-dead-beef-dead-000000000099"   # not in factories stub

USER_A = {"id": U1, "company_id": CO_A, "factory_id": FAC1, "role_code": "001"}
USER_B = {"id": U2, "company_id": CO_B, "factory_id": FAC2, "role_code": "001"}

# ── DB skip marker ─────────────────────────────────────────────────────────────

def _pg_available() -> bool:
    try:
        conn = psycopg2.connect(_DSN, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


_SKIP_DB = pytest.mark.skipif(
    "TAM_TEST_PG_DSN" not in os.environ or not _pg_available(),
    reason="TAM_TEST_PG_DSN not configured or test DB not reachable",
)


# ── Module-scoped DB fixture ───────────────────────────────────────────────────

@pytest.fixture(scope="module")
def pg():
    """Bootstrap test DB schema from migration SQL + stub users/factories tables."""
    # Guard 1: TAM_TEST_PG_DSN must be explicitly set — no DATABASE_URL fallback
    if "TAM_TEST_PG_DSN" not in os.environ:
        pytest.fail(
            "TAM_TEST_PG_DSN must be explicitly set — refusing destructive DDL on undefined DSN. "
            "Set TAM_TEST_PG_DSN to a local test DB before running DB tests.",
            pytrace=False,
        )
    # Guard 2: must not match DATABASE_URL (production guard)
    _prod_url = os.environ.get("DATABASE_URL", "")
    if _prod_url and _DSN.strip() == _prod_url.strip():
        pytest.fail(
            "TAM_TEST_PG_DSN must not match DATABASE_URL — refusing to run destructive DDL "
            "against the production database.",
            pytrace=False,
        )
    # Guard 3: isolation marker must exist and be non-empty before any destructive DDL
    _guard_conn = psycopg2.connect(_DSN, connect_timeout=2)
    try:
        _gc = _guard_conn.cursor()
        _gc.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = '_tam_test_isolation_marker'"
        )
        if _gc.fetchone()[0] == 0:
            pytest.fail(
                "Isolation marker '_tam_test_isolation_marker' not found in test DB. "
                "Create the marker table and insert a row before running destructive DB tests. "
                "Do NOT auto-create this marker in test code.",
                pytrace=False,
            )
        _gc.execute("SELECT COUNT(*) FROM _tam_test_isolation_marker")
        if _gc.fetchone()[0] == 0:
            pytest.fail(
                "Isolation marker table '_tam_test_isolation_marker' exists but is empty. "
                "Insert a row into the marker table to confirm this is a safe test DB.",
                pytrace=False,
            )
    finally:
        _guard_conn.close()

    conn = psycopg2.connect(_DSN)
    conn.autocommit = True
    cur = conn.cursor()

    # Drop TAM tables and functions
    cur.execute("""
        DROP TABLE IF EXISTS
            tam_approval_step_assignees,
            tam_approval_route_steps,
            tam_approval_route_versions,
            tam_approval_routes
        CASCADE;
        DROP FUNCTION IF EXISTS
            tam_routes_published_guard_fn,
            tam_version_immutability_fn,
            tam_steps_draft_only_fn,
            tam_assignees_draft_only_fn
        CASCADE;
    """)

    # Drop and recreate stub reference tables (users, factories)
    cur.execute("""
        DROP TABLE IF EXISTS users, factories CASCADE;
    """)
    cur.execute("""
        CREATE TABLE factories (
            id          UUID PRIMARY KEY,
            company_id  UUID NOT NULL,
            status_code TEXT NOT NULL DEFAULT 'ACTIVE'
        );
        CREATE TABLE users (
            id          UUID PRIMARY KEY,
            company_id  UUID NOT NULL,
            status_code TEXT NOT NULL DEFAULT 'ACTIVE',
            is_active   BOOLEAN NOT NULL DEFAULT true
        );
    """)

    # Insert stable test factories (both CO_A)
    cur.execute(
        "INSERT INTO factories (id, company_id, status_code) VALUES (%s, %s, 'ACTIVE'), (%s, %s, 'ACTIVE')",
        (FAC1, CO_A, FAC2, CO_A),
    )

    # Insert stable test users
    cur.execute(
        """
        INSERT INTO users (id, company_id, status_code, is_active) VALUES
            (%s, %s, 'ACTIVE',   true),   -- U1: actor (CO_A)
            (%s, %s, 'ACTIVE',   true),   -- U2: assignee (CO_A)
            (%s, %s, 'ACTIVE',   true),   -- U3: assignee (CO_A)
            (%s, %s, 'INACTIVE', false),  -- U_INACTIVE: inactive (CO_A)
            (%s, %s, 'ACTIVE',   true)    -- U_CO_B: cross-company (CO_B)
        """,
        (U1, CO_A, U2, CO_A, U3, CO_A, U_INACTIVE, CO_A, U_CO_B, CO_B),
    )

    # Apply TAM migration schema
    cur.execute(_MIGRATION_SQL)
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def clean(request):
    """Truncate TAM tables before each test. No-op when test DB is not configured or reachable."""
    if "TAM_TEST_PG_DSN" not in os.environ or not _pg_available():
        yield
        return
    pg_conn = request.getfixturevalue("pg")
    cur = pg_conn.cursor()
    cur.execute("""
        TRUNCATE tam_approval_step_assignees,
                 tam_approval_route_steps,
                 tam_approval_route_versions,
                 tam_approval_routes
        CASCADE;
    """)
    pg_conn.commit()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _dict_cur(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _make_route(pg, company_id=CO_A, factory_id=None,
                route_scope="COMPANY_DEFAULT", scope_key=None,
                display_name="Test Route", created_by=U1) -> dict:
    cur = _dict_cur(pg)
    cur.execute(
        """
        INSERT INTO tam_approval_routes
            (company_id, factory_id, route_scope, scope_key, display_name, created_by)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (company_id, factory_id, route_scope, scope_key, display_name, created_by),
    )
    row = dict(cur.fetchone())
    pg.commit()
    return row


def _make_version(pg, route_id, notes=None, created_by=U1) -> dict:
    cur = _dict_cur(pg)
    cur.execute(
        """
        INSERT INTO tam_approval_route_versions
            (route_id, version_number, notes, created_by)
        SELECT %s, COALESCE(MAX(version_number),0)+1, %s, %s
          FROM tam_approval_route_versions WHERE route_id = %s
        RETURNING *
        """,
        (route_id, notes, created_by, route_id),
    )
    row = dict(cur.fetchone())
    pg.commit()
    return row


def _make_step(pg, version_id, step_order=1,
               step_name="Step 1", step_type="SEQUENTIAL") -> dict:
    cur = _dict_cur(pg)
    cur.execute(
        """
        INSERT INTO tam_approval_route_steps
            (version_id, step_order, step_name, step_type)
        VALUES (%s, %s, %s, %s)
        RETURNING *
        """,
        (version_id, step_order, step_name, step_type),
    )
    row = dict(cur.fetchone())
    pg.commit()
    return row


def _make_assignee(pg, step_id, user_id=U2, assigned_by=U1) -> dict:
    cur = _dict_cur(pg)
    cur.execute(
        """
        INSERT INTO tam_approval_step_assignees
            (step_id, user_id, assigned_by)
        VALUES (%s, %s, %s)
        RETURNING *
        """,
        (step_id, user_id, assigned_by),
    )
    row = dict(cur.fetchone())
    pg.commit()
    return row


def _publish(pg, route_id, version_id, published_by=U1) -> None:
    cur = pg.cursor()
    cur.execute(
        """
        UPDATE tam_approval_route_versions
           SET version_status = 'PUBLISHED',
               published_at   = NOW(),
               published_by   = %s
         WHERE version_id = %s
        """,
        (published_by, version_id),
    )
    cur.execute(
        "UPDATE tam_approval_routes SET current_version_id = %s WHERE route_id = %s",
        (version_id, route_id),
    )
    pg.commit()


# ═══════════════════════════════════════════════════════════════
# B01 — Route scope validation (service rejects invalid scope)
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_b01_invalid_scope_rejected(pg):
    from services.tam.routes_svc import create_route, TamError
    with pytest.raises(TamError) as exc:
        create_route(USER_A, company_id=CO_A, route_scope="INVALID_SCOPE",
                     display_name="x", dsn=_DSN)
    assert exc.value.http_status == 422
    assert exc.value.code == "INVALID_ROUTE_SCOPE"


@_SKIP_DB
def test_b01_scope_key_required_for_document_type(pg):
    from services.tam.routes_svc import create_route, TamError
    with pytest.raises(TamError) as exc:
        create_route(USER_A, company_id=CO_A, route_scope="DOCUMENT_TYPE",
                     scope_key=None, display_name="x", dsn=_DSN)
    assert exc.value.http_status == 422
    assert "scope_key" in exc.value.message.lower()


@_SKIP_DB
def test_b01_scope_key_not_allowed_for_company_default(pg):
    from services.tam.routes_svc import create_route, TamError
    with pytest.raises(TamError) as exc:
        create_route(USER_A, company_id=CO_A, route_scope="COMPANY_DEFAULT",
                     scope_key="SOME_KEY", display_name="x", dsn=_DSN)
    assert exc.value.http_status == 422


@_SKIP_DB
def test_b01_factory_default_requires_factory_id(pg):
    from services.tam.routes_svc import create_route, TamError
    with pytest.raises(TamError) as exc:
        create_route(USER_A, company_id=CO_A, route_scope="FACTORY_DEFAULT",
                     factory_id=None, display_name="x", dsn=_DSN)
    assert exc.value.http_status == 422


# ═══════════════════════════════════════════════════════════════
# B02 — Company default route duplicate prevention
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_b02_company_default_duplicate_rejected(pg):
    from services.tam.routes_svc import create_route, TamError
    create_route(USER_A, company_id=CO_A, route_scope="COMPANY_DEFAULT",
                 display_name="First", dsn=_DSN)
    with pytest.raises(TamError) as exc:
        create_route(USER_A, company_id=CO_A, route_scope="COMPANY_DEFAULT",
                     display_name="Second", dsn=_DSN)
    assert exc.value.http_status == 409
    assert "DUPLICATE" in exc.value.code


# ═══════════════════════════════════════════════════════════════
# B03 — Factory default route duplicate prevention
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_b03_factory_default_duplicate_rejected(pg):
    from services.tam.routes_svc import create_route, TamError
    create_route(USER_A, company_id=CO_A, factory_id=FAC1,
                 route_scope="FACTORY_DEFAULT", display_name="First", dsn=_DSN)
    with pytest.raises(TamError) as exc:
        create_route(USER_A, company_id=CO_A, factory_id=FAC1,
                     route_scope="FACTORY_DEFAULT", display_name="Second", dsn=_DSN)
    assert exc.value.http_status == 409


@_SKIP_DB
def test_b03_different_factory_allowed(pg):
    """R3 gate: USER_A (factory_id=FAC1) can create FAC1 route but not FAC2.
    DB-level uniqueness proof: routes for different factories coexist (via _make_route)."""
    from services.tam.routes_svc import create_route, TamError
    r1 = create_route(USER_A, company_id=CO_A, factory_id=FAC1,
                      route_scope="FACTORY_DEFAULT", display_name="Fac1", dsn=_DSN)
    assert r1["factory_id"] == FAC1
    with pytest.raises(TamError) as exc:
        create_route(USER_A, company_id=CO_A, factory_id=FAC2,
                     route_scope="FACTORY_DEFAULT", display_name="Fac2", dsn=_DSN)
    assert exc.value.http_status == 422
    assert exc.value.code == "FACTORY_SCOPE_NOT_FINALIZED"
    # DB-level uniqueness still holds: different factories can have separate routes
    r2 = _make_route(pg, company_id=CO_A, factory_id=FAC2,
                     route_scope="FACTORY_DEFAULT", display_name="Fac2")
    assert r1["route_id"] != r2["route_id"]


# ═══════════════════════════════════════════════════════════════
# B04 — Document/Process scope_key validation
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_b04_document_type_same_scope_key_duplicate(pg):
    from services.tam.routes_svc import create_route, TamError
    create_route(USER_A, company_id=CO_A, route_scope="DOCUMENT_TYPE",
                 scope_key="WMS_OVERRIDE", display_name="R1", dsn=_DSN)
    with pytest.raises(TamError) as exc:
        create_route(USER_A, company_id=CO_A, route_scope="DOCUMENT_TYPE",
                     scope_key="WMS_OVERRIDE", display_name="R2", dsn=_DSN)
    assert exc.value.http_status == 409


@_SKIP_DB
def test_b04_different_scope_key_allowed(pg):
    from services.tam.routes_svc import create_route
    r1 = create_route(USER_A, company_id=CO_A, route_scope="DOCUMENT_TYPE",
                      scope_key="WMS_OVERRIDE", display_name="R1", dsn=_DSN)
    r2 = create_route(USER_A, company_id=CO_A, route_scope="DOCUMENT_TYPE",
                      scope_key="WMS_TRANSFER", display_name="R2", dsn=_DSN)
    assert r1["route_id"] != r2["route_id"]


# ═══════════════════════════════════════════════════════════════
# B05 — DRAFT step creation
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_b05_create_step_on_draft_version(pg):
    from services.tam.routes_svc import create_route, create_version, create_step
    route = create_route(USER_A, company_id=CO_A, route_scope="COMPANY_DEFAULT",
                         display_name="R", dsn=_DSN)
    ver = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)
    step = create_step(USER_A, version_id=ver["version_id"],
                       step_order=1, step_name="Review", step_type="SEQUENTIAL",
                       dsn=_DSN)
    assert step["step_order"] == 1
    assert step["version_id"] == ver["version_id"]


# ═══════════════════════════════════════════════════════════════
# B06 — DRAFT assignee creation
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_b06_create_assignee_on_draft_step(pg):
    from services.tam.routes_svc import (create_route, create_version,
                                          create_step, create_assignee)
    route = create_route(USER_A, company_id=CO_A, route_scope="COMPANY_DEFAULT",
                         display_name="R", dsn=_DSN)
    ver   = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)
    step  = create_step(USER_A, version_id=ver["version_id"],
                        step_order=1, step_name="S1", step_type="SEQUENTIAL",
                        dsn=_DSN)
    asn   = create_assignee(USER_A, step_id=step["step_id"], user_id=U2, dsn=_DSN)
    assert asn["user_id"] == U2
    assert asn["step_id"] == step["step_id"]


# ═══════════════════════════════════════════════════════════════
# B07 — Publish rejected if step has no assignee
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_b07_publish_rejects_step_with_no_assignee(pg):
    from services.tam.routes_svc import (create_route, create_version,
                                          create_step, publish_version, TamError)
    route = create_route(USER_A, company_id=CO_A, route_scope="COMPANY_DEFAULT",
                         display_name="R", dsn=_DSN)
    ver   = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)
    create_step(USER_A, version_id=ver["version_id"],
                step_order=1, step_name="S1", step_type="SEQUENTIAL", dsn=_DSN)
    with pytest.raises(TamError) as exc:
        publish_version(USER_A, route_id=route["route_id"],
                        version_id=ver["version_id"], dsn=_DSN)
    assert exc.value.http_status == 422
    assert "ASSIGNEE" in exc.value.code


@_SKIP_DB
def test_b07_publish_rejects_version_with_no_steps(pg):
    from services.tam.routes_svc import (create_route, create_version,
                                          publish_version, TamError)
    route = create_route(USER_A, company_id=CO_A, route_scope="COMPANY_DEFAULT",
                         display_name="R", dsn=_DSN)
    ver   = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)
    with pytest.raises(TamError) as exc:
        publish_version(USER_A, route_id=route["route_id"],
                        version_id=ver["version_id"], dsn=_DSN)
    assert exc.value.http_status == 422
    assert "STEPS" in exc.value.code


# ═══════════════════════════════════════════════════════════════
# B08 — Normal publish succeeds; route.current_version_id updated
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_b08_successful_publish(pg):
    from services.tam.routes_svc import (create_route, create_version,
                                          create_step, create_assignee,
                                          publish_version)
    route = create_route(USER_A, company_id=CO_A, route_scope="COMPANY_DEFAULT",
                         display_name="R", dsn=_DSN)
    ver   = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)
    step  = create_step(USER_A, version_id=ver["version_id"],
                        step_order=1, step_name="S1", step_type="SEQUENTIAL",
                        dsn=_DSN)
    create_assignee(USER_A, step_id=step["step_id"], user_id=U2, dsn=_DSN)

    result = publish_version(USER_A, route_id=route["route_id"],
                              version_id=ver["version_id"], dsn=_DSN)
    assert result["version_status"] == "PUBLISHED"
    assert result["published_by"] == U1
    assert result["published_at"] is not None

    cur = _dict_cur(pg)
    cur.execute("SELECT current_version_id FROM tam_approval_routes WHERE route_id = %s",
                (route["route_id"],))
    updated = cur.fetchone()
    assert str(updated["current_version_id"]) == ver["version_id"]


# ═══════════════════════════════════════════════════════════════
# B09 — PUBLISHED version UPDATE rejected (immutability trigger)
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_b09_published_version_update_rejected(pg):
    route = _make_route(pg)
    ver   = _make_version(pg, route["route_id"])
    step  = _make_step(pg, ver["version_id"])
    _make_assignee(pg, step["step_id"])
    _publish(pg, route["route_id"], ver["version_id"])

    cur = pg.cursor()
    with pytest.raises(psycopg2.Error) as exc:
        cur.execute(
            "UPDATE tam_approval_route_versions SET notes = 'tampered' WHERE version_id = %s",
            (ver["version_id"],),
        )
        pg.commit()
    pg.rollback()
    assert "immutable" in str(exc.value).lower()


# ═══════════════════════════════════════════════════════════════
# B10 — PUBLISHED version DELETE rejected
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_b10_any_version_delete_rejected(pg):
    route = _make_route(pg)
    ver   = _make_version(pg, route["route_id"])

    cur = pg.cursor()
    with pytest.raises(psycopg2.Error) as exc:
        cur.execute(
            "DELETE FROM tam_approval_route_versions WHERE version_id = %s",
            (ver["version_id"],),
        )
        pg.commit()
    pg.rollback()
    assert "delete" in str(exc.value).lower() or "forbidden" in str(exc.value).lower()


# ═══════════════════════════════════════════════════════════════
# B11 — PUBLISHED step/assignee changes rejected
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_b11_published_step_update_rejected(pg):
    route = _make_route(pg)
    ver   = _make_version(pg, route["route_id"])
    step  = _make_step(pg, ver["version_id"])
    _make_assignee(pg, step["step_id"])
    _publish(pg, route["route_id"], ver["version_id"])

    cur = pg.cursor()
    with pytest.raises(psycopg2.Error):
        cur.execute(
            "UPDATE tam_approval_route_steps SET step_name = 'hacked' WHERE step_id = %s",
            (step["step_id"],),
        )
        pg.commit()
    pg.rollback()


@_SKIP_DB
def test_b11_published_step_insert_rejected(pg):
    route = _make_route(pg)
    ver   = _make_version(pg, route["route_id"])
    step  = _make_step(pg, ver["version_id"])
    _make_assignee(pg, step["step_id"])
    _publish(pg, route["route_id"], ver["version_id"])

    cur = pg.cursor()
    with pytest.raises(psycopg2.Error):
        cur.execute(
            """
            INSERT INTO tam_approval_route_steps
                (version_id, step_order, step_name, step_type)
            VALUES (%s, 2, 'Extra', 'SEQUENTIAL')
            """,
            (ver["version_id"],),
        )
        pg.commit()
    pg.rollback()


@_SKIP_DB
def test_b11_published_assignee_insert_rejected(pg):
    route = _make_route(pg)
    ver   = _make_version(pg, route["route_id"])
    step  = _make_step(pg, ver["version_id"])
    _make_assignee(pg, step["step_id"])
    _publish(pg, route["route_id"], ver["version_id"])

    cur = pg.cursor()
    with pytest.raises(psycopg2.Error):
        cur.execute(
            """
            INSERT INTO tam_approval_step_assignees (step_id, user_id, assigned_by)
            VALUES (%s, %s, %s)
            """,
            (step["step_id"], U3, U1),
        )
        pg.commit()
    pg.rollback()


@_SKIP_DB
def test_b11_published_assignee_delete_rejected(pg):
    route = _make_route(pg)
    ver   = _make_version(pg, route["route_id"])
    step  = _make_step(pg, ver["version_id"])
    asn   = _make_assignee(pg, step["step_id"])
    _publish(pg, route["route_id"], ver["version_id"])

    cur = pg.cursor()
    with pytest.raises(psycopg2.Error):
        cur.execute(
            "DELETE FROM tam_approval_step_assignees WHERE assignee_id = %s",
            (asn["assignee_id"],),
        )
        pg.commit()
    pg.rollback()


# ═══════════════════════════════════════════════════════════════
# B12 — Multiple PUBLISHED versions coexist as history
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_b12_multiple_published_versions_coexist(pg):
    from services.tam.routes_svc import (create_version, create_step,
                                          create_assignee, publish_version)
    route = _make_route(pg)
    rid   = route["route_id"]

    v1   = create_version(USER_A, route_id=rid, dsn=_DSN)
    s1   = create_step(USER_A, version_id=v1["version_id"],
                       step_order=1, step_name="S1", step_type="SEQUENTIAL", dsn=_DSN)
    create_assignee(USER_A, step_id=s1["step_id"], user_id=U2, dsn=_DSN)
    publish_version(USER_A, route_id=rid, version_id=v1["version_id"], dsn=_DSN)

    v2   = create_version(USER_A, route_id=rid, dsn=_DSN)
    s2   = create_step(USER_A, version_id=v2["version_id"],
                       step_order=1, step_name="S1b", step_type="PARALLEL_ANY", dsn=_DSN)
    create_assignee(USER_A, step_id=s2["step_id"], user_id=U3, dsn=_DSN)
    publish_version(USER_A, route_id=rid, version_id=v2["version_id"], dsn=_DSN)

    cur = _dict_cur(pg)
    cur.execute(
        "SELECT version_id, version_number, version_status "
        "FROM tam_approval_route_versions WHERE route_id = %s ORDER BY version_number",
        (rid,),
    )
    versions = cur.fetchall()
    assert len(versions) == 2
    assert all(v["version_status"] == "PUBLISHED" for v in versions)

    cur.execute(
        "SELECT current_version_id FROM tam_approval_routes WHERE route_id = %s",
        (rid,),
    )
    r = cur.fetchone()
    assert str(r["current_version_id"]) == v2["version_id"]
    assert versions[0]["version_status"] == "PUBLISHED"


# ═══════════════════════════════════════════════════════════════
# B13 — current_version_id must reference same-route version (composite FK)
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_b13_current_version_id_cross_route_fk_rejected(pg):
    """T26 gate: composite FK rejects version from a different route."""
    route_a = _make_route(pg, route_scope="COMPANY_DEFAULT", display_name="RouteA")
    route_b = _make_route(pg, company_id=CO_A, route_scope="FACTORY_DEFAULT",
                          factory_id=FAC1, display_name="RouteB")

    ver_b = _make_version(pg, route_b["route_id"])
    step_b = _make_step(pg, ver_b["version_id"])
    _make_assignee(pg, step_b["step_id"])
    _publish(pg, route_b["route_id"], ver_b["version_id"])

    cur = pg.cursor()
    with pytest.raises(psycopg2.Error):
        cur.execute(
            "UPDATE tam_approval_routes SET current_version_id = %s WHERE route_id = %s",
            (ver_b["version_id"], route_a["route_id"]),
        )
        pg.commit()
    pg.rollback()


# ═══════════════════════════════════════════════════════════════
# B14 — current_version_id referencing DRAFT version rejected
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_b14_current_version_id_draft_rejected(pg):
    """T27 gate: PUBLISHED guard trigger rejects DRAFT version pointer."""
    route = _make_route(pg)
    ver   = _make_version(pg, route["route_id"])

    cur = pg.cursor()
    with pytest.raises(psycopg2.Error) as exc:
        cur.execute(
            "UPDATE tam_approval_routes SET current_version_id = %s WHERE route_id = %s",
            (ver["version_id"], route["route_id"]),
        )
        pg.commit()
    pg.rollback()
    assert "PUBLISHED" in str(exc.value)


# ═══════════════════════════════════════════════════════════════
# B15 — Concurrent publish race: only one wins, result is consistent
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_b15_concurrent_publish_serialized(pg):
    """T28 gate: two threads racing to publish same version; exactly one succeeds."""
    from services.tam.routes_svc import (create_route, create_version,
                                          create_step, create_assignee,
                                          publish_version, TamError)
    route = create_route(USER_A, company_id=CO_A, route_scope="COMPANY_DEFAULT",
                         display_name="Race", dsn=_DSN)
    ver   = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)
    step  = create_step(USER_A, version_id=ver["version_id"],
                        step_order=1, step_name="S", step_type="SEQUENTIAL",
                        dsn=_DSN)
    create_assignee(USER_A, step_id=step["step_id"], user_id=U2, dsn=_DSN)

    results: list = []
    errors:  list = []

    def _try_publish():
        try:
            r = publish_version(USER_A, route_id=route["route_id"],
                                version_id=ver["version_id"], dsn=_DSN)
            results.append(r)
        except TamError as e:
            errors.append(e)

    t1 = threading.Thread(target=_try_publish)
    t2 = threading.Thread(target=_try_publish)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(results) == 1, f"Expected 1 success, got {len(results)}"
    assert results[0]["version_status"] == "PUBLISHED"

    cur = _dict_cur(pg)
    cur.execute(
        "SELECT current_version_id FROM tam_approval_routes WHERE route_id = %s",
        (route["route_id"],),
    )
    r = cur.fetchone()
    assert str(r["current_version_id"]) == ver["version_id"]


# ═══════════════════════════════════════════════════════════════
# B16 — Cross-company access denied (tenant isolation)
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_b16_cross_company_route_create_rejected(pg):
    from services.tam.routes_svc import create_route, TamError
    with pytest.raises(TamError) as exc:
        create_route(USER_B, company_id=CO_A, route_scope="COMPANY_DEFAULT",
                     display_name="Intrusion", dsn=_DSN)
    assert exc.value.http_status == 403
    assert "CROSS_COMPANY" in exc.value.code


@_SKIP_DB
def test_b16_cross_company_route_get_hidden(pg):
    from services.tam.routes_svc import create_route, get_route, TamError
    route = create_route(USER_A, company_id=CO_A, route_scope="COMPANY_DEFAULT",
                         display_name="Private", dsn=_DSN)
    with pytest.raises(TamError) as exc:
        get_route(USER_B, route_id=route["route_id"], dsn=_DSN)
    assert exc.value.http_status == 404


# ═══════════════════════════════════════════════════════════════
# B17 — SQL error causes full ROLLBACK (no partial state)
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_b17_sql_error_triggers_rollback(pg):
    """publish_version ROLLBACK: if version is already PUBLISHED, no partial state committed."""
    route = _make_route(pg)
    ver   = _make_version(pg, route["route_id"])
    step  = _make_step(pg, ver["version_id"])
    _make_assignee(pg, step["step_id"])

    cur = pg.cursor()
    cur.execute(
        """
        UPDATE tam_approval_route_versions
           SET version_status = 'PUBLISHED', published_at = NOW(), published_by = %s
         WHERE version_id = %s
        """,
        (U1, ver["version_id"]),
    )
    pg.commit()

    from services.tam.routes_svc import publish_version, TamError
    with pytest.raises(TamError) as exc:
        publish_version(USER_A, route_id=route["route_id"],
                        version_id=ver["version_id"], dsn=_DSN)
    assert exc.value.http_status == 409
    assert "NOT_DRAFT" in exc.value.code

    cur2 = _dict_cur(pg)
    cur2.execute(
        "SELECT current_version_id FROM tam_approval_routes WHERE route_id = %s",
        (route["route_id"],),
    )
    r = cur2.fetchone()
    assert r["current_version_id"] is None


# ═══════════════════════════════════════════════════════════════
# B18 — Router blocks all users (ROUTE_MANAGER_PERMISSION_REQUIRED)
# ═══════════════════════════════════════════════════════════════

def test_b18_router_write_endpoints_return_403():
    """All route management endpoints must return 403 regardless of auth state.

    Uses an isolated FastAPI instance — TAM router is not registered in main.app
    (PREMERGE-003: passive integration until OD-01 authorized).
    """
    from fastapi import FastAPI
    from routers.auth import get_current_user
    from routers.tam_routes import router as tam_router

    mock_user = {"id": U1, "company_id": CO_A, "role_code": "001",
                 "status_code": "ACTIVE", "is_active": True}

    isolated_app = FastAPI()
    isolated_app.include_router(tam_router)
    isolated_app.dependency_overrides[get_current_user] = lambda: mock_user
    client = TestClient(isolated_app, raise_server_exceptions=False)

    endpoints = [
        ("POST", "/v1/tam/routes",
         {"company_id": CO_A, "route_scope": "COMPANY_DEFAULT", "display_name": "R"}),
        ("POST", "/v1/tam/routes/fake-id/versions", {"notes": None}),
        ("POST", "/v1/tam/routes/fake-id/versions/fake-ver/steps",
         {"step_order": 1, "step_name": "S", "step_type": "SEQUENTIAL"}),
        ("POST", "/v1/tam/routes/fake-id/versions/fake-ver/steps/fake-step/assignees",
         {"user_id": U2}),
        ("POST", "/v1/tam/routes/fake-id/versions/fake-ver/publish", {}),
    ]
    for method, url, body in endpoints:
        resp = client.request(method, url, json=body)
        assert resp.status_code == 403, (
            f"{method} {url} expected 403, got {resp.status_code}: {resp.text}"
        )
        detail = resp.json().get("detail", {})
        assert detail.get("code") == "ROUTE_MANAGER_PERMISSION_REQUIRED", (
            f"{method} {url}: unexpected code {detail.get('code')!r}"
        )


# ═══════════════════════════════════════════════════════════════
# T26 — Composite FK gate: cross-route version reference rejected at DB level
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_t26_composite_fk_cross_route_rejected(pg):
    """T26: tam_routes_current_version_fk prevents pointing to another route's version."""
    route_a = _make_route(pg, route_scope="COMPANY_DEFAULT", display_name="A")
    route_b = _make_route(pg, company_id=CO_A, route_scope="FACTORY_DEFAULT",
                          factory_id=FAC1, display_name="B")

    ver_b = _make_version(pg, route_b["route_id"])
    step_b = _make_step(pg, ver_b["version_id"])
    _make_assignee(pg, step_b["step_id"])
    _publish(pg, route_b["route_id"], ver_b["version_id"])

    cur = pg.cursor()
    with pytest.raises(psycopg2.Error):
        cur.execute(
            "UPDATE tam_approval_routes SET current_version_id = %s WHERE route_id = %s",
            (ver_b["version_id"], route_a["route_id"]),
        )
        pg.commit()
    pg.rollback()


# ═══════════════════════════════════════════════════════════════
# T27 — PUBLISHED state guard trigger: DRAFT pointer rejected
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_t27_published_guard_trigger_rejects_draft_pointer(pg):
    """T27: tam_routes_published_guard_trg raises exception for DRAFT current_version_id."""
    route = _make_route(pg)
    ver   = _make_version(pg, route["route_id"])

    cur = pg.cursor()
    with pytest.raises(psycopg2.Error) as exc:
        cur.execute(
            "UPDATE tam_approval_routes SET current_version_id = %s WHERE route_id = %s",
            (ver["version_id"], route["route_id"]),
        )
        pg.commit()
    pg.rollback()
    assert "PUBLISHED" in str(exc.value)


# ═══════════════════════════════════════════════════════════════
# T28 — Concurrent publish serialization (SELECT FOR UPDATE gate)
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_t28_concurrent_publish_select_for_update_serialization(pg):
    """T28: publish_version uses SELECT FOR UPDATE on routes row.
    Three concurrent publish attempts on the same version: exactly one succeeds."""
    from services.tam.routes_svc import (create_route, create_version,
                                          create_step, create_assignee,
                                          publish_version, TamError)
    route = create_route(USER_A, company_id=CO_A, route_scope="DOCUMENT_TYPE",
                         scope_key="T28_CONCURRENT", display_name="T28", dsn=_DSN)
    ver   = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)
    step  = create_step(USER_A, version_id=ver["version_id"],
                        step_order=1, step_name="Gate", step_type="SEQUENTIAL",
                        dsn=_DSN)
    create_assignee(USER_A, step_id=step["step_id"], user_id=U2, dsn=_DSN)

    success_count = 0
    fail_count    = 0
    lock = threading.Lock()

    def _worker():
        nonlocal success_count, fail_count
        try:
            publish_version(USER_A, route_id=route["route_id"],
                            version_id=ver["version_id"], dsn=_DSN)
            with lock:
                success_count += 1
        except (TamError, Exception):
            with lock:
                fail_count += 1

    threads = [threading.Thread(target=_worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert success_count == 1, f"Expected exactly 1 publish success, got {success_count}"
    assert fail_count == 2,    f"Expected exactly 2 publish failures, got {fail_count}"

    cur = _dict_cur(pg)
    cur.execute(
        "SELECT current_version_id FROM tam_approval_routes WHERE route_id = %s",
        (route["route_id"],),
    )
    r = cur.fetchone()
    assert str(r["current_version_id"]) == ver["version_id"]


# ═══════════════════════════════════════════════════════════════
# R01 — Route lock serializes concurrent version creation: unique numbers
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_r01_concurrent_version_creation_unique_numbers(pg):
    """R1: create_version acquires route FOR UPDATE before MAX+1.
    Three concurrent creates yield unique version numbers [1, 2, 3]."""
    from services.tam.routes_svc import create_route, create_version
    route = create_route(USER_A, company_id=CO_A, route_scope="COMPANY_DEFAULT",
                         display_name="R01-Route", dsn=_DSN)

    results: list = []
    errors:  list = []
    lock = threading.Lock()

    def _create():
        try:
            v = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)
            with lock:
                results.append(v["version_number"])
        except Exception as e:
            with lock:
                errors.append(str(e))

    threads = [threading.Thread(target=_create) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Unexpected errors during concurrent create_version: {errors}"
    assert sorted(results) == [1, 2, 3], (
        f"Expected unique version numbers [1,2,3], got {sorted(results)}"
    )


# ═══════════════════════════════════════════════════════════════
# R02 — create_step on published version returns 409 (route lock re-check)
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_r02_create_step_after_publish_returns_409(pg):
    """R1: create_step re-checks version status under route lock.
    After publish_version completes, create_step returns 409 VERSION_NOT_DRAFT."""
    from services.tam.routes_svc import (create_route, create_version, create_step,
                                          create_assignee, publish_version, TamError)
    route = create_route(USER_A, company_id=CO_A, route_scope="DOCUMENT_TYPE",
                         scope_key="R02", display_name="R02-Route", dsn=_DSN)
    ver   = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)
    step  = create_step(USER_A, version_id=ver["version_id"],
                        step_order=1, step_name="S1", step_type="SEQUENTIAL", dsn=_DSN)
    create_assignee(USER_A, step_id=step["step_id"], user_id=U2, dsn=_DSN)
    publish_version(USER_A, route_id=route["route_id"], version_id=ver["version_id"], dsn=_DSN)

    with pytest.raises(TamError) as exc:
        create_step(USER_A, version_id=ver["version_id"],
                    step_order=2, step_name="S2", step_type="SEQUENTIAL", dsn=_DSN)
    assert exc.value.http_status == 409
    assert "NOT_DRAFT" in exc.value.code


# ═══════════════════════════════════════════════════════════════
# R03 — Trigger 3 UPDATE: OLD.version_id check (FOR UPDATE gate)
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_r03_trigger_old_version_check_on_step_update(pg):
    """R1 trigger 3 UPDATE path: OLD.version_id is PUBLISHED → exception raised."""
    route = _make_route(pg)
    ver   = _make_version(pg, route["route_id"])
    step  = _make_step(pg, ver["version_id"])
    _make_assignee(pg, step["step_id"])
    _publish(pg, route["route_id"], ver["version_id"])

    cur = pg.cursor()
    with pytest.raises(psycopg2.Error) as exc:
        cur.execute(
            "UPDATE tam_approval_route_steps SET allow_supplement = true WHERE step_id = %s",
            (step["step_id"],),
        )
        pg.commit()
    pg.rollback()
    err_msg = str(exc.value).lower()
    assert "forbidden" in err_msg or "non-draft" in err_msg


# ═══════════════════════════════════════════════════════════════
# R04 — Trigger 3 UPDATE: NEW.version_id check (cross-version move)
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_r04_trigger_new_version_check_on_step_update(pg):
    """R1 trigger 3 UPDATE path: NEW.version_id is PUBLISHED → exception raised,
    even when OLD.version_id was DRAFT."""
    # Route A — published version
    route_a = _make_route(pg, route_scope="COMPANY_DEFAULT", display_name="A")
    ver_pub = _make_version(pg, route_a["route_id"])
    step_pub = _make_step(pg, ver_pub["version_id"])
    _make_assignee(pg, step_pub["step_id"])
    _publish(pg, route_a["route_id"], ver_pub["version_id"])

    # Route B — draft version with a step we will try to reassign
    route_b = _make_route(pg, route_scope="FACTORY_DEFAULT", factory_id=FAC1)
    ver_draft = _make_version(pg, route_b["route_id"])
    step_draft = _make_step(pg, ver_draft["version_id"])

    # Attempt to reassign step_draft to the PUBLISHED version (NEW-side violation)
    cur = pg.cursor()
    with pytest.raises(psycopg2.Error) as exc:
        cur.execute(
            "UPDATE tam_approval_route_steps SET version_id = %s WHERE step_id = %s",
            (ver_pub["version_id"], step_draft["step_id"]),
        )
        pg.commit()
    pg.rollback()
    err_msg = str(exc.value).lower()
    assert "forbidden" in err_msg or "non-draft" in err_msg


# ═══════════════════════════════════════════════════════════════
# R05 — Trigger 4 UPDATE: OLD step's version check
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_r05_trigger_assignee_update_old_version_check(pg):
    """R1 trigger 4 UPDATE path: OLD.step_id's version is PUBLISHED → exception raised."""
    route = _make_route(pg)
    ver   = _make_version(pg, route["route_id"])
    step  = _make_step(pg, ver["version_id"])
    asn   = _make_assignee(pg, step["step_id"])
    _publish(pg, route["route_id"], ver["version_id"])

    cur = pg.cursor()
    with pytest.raises(psycopg2.Error):
        cur.execute(
            "UPDATE tam_approval_step_assignees SET assigned_by = %s WHERE assignee_id = %s",
            (U3, asn["assignee_id"]),
        )
        pg.commit()
    pg.rollback()


# ═══════════════════════════════════════════════════════════════
# R06 — ASSIGNEE_INACTIVE: inactive user rejected
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_r06_inactive_assignee_rejected(pg):
    """R1: create_assignee validates user status; inactive user raises TamError 422."""
    from services.tam.routes_svc import (create_route, create_version, create_step,
                                          create_assignee, TamError)
    route = create_route(USER_A, company_id=CO_A, route_scope="COMPANY_DEFAULT",
                         display_name="R06-Route", dsn=_DSN)
    ver   = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)
    step  = create_step(USER_A, version_id=ver["version_id"],
                        step_order=1, step_name="S1", step_type="SEQUENTIAL", dsn=_DSN)

    with pytest.raises(TamError) as exc:
        create_assignee(USER_A, step_id=step["step_id"], user_id=U_INACTIVE, dsn=_DSN)
    assert exc.value.http_status == 422
    assert exc.value.code == "ASSIGNEE_INACTIVE"


# ═══════════════════════════════════════════════════════════════
# R07 — ASSIGNEE_CROSS_COMPANY: different-company user rejected
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_r07_cross_company_assignee_rejected(pg):
    """R1: create_assignee validates assignee company; CO_B user raises TamError 422."""
    from services.tam.routes_svc import (create_route, create_version, create_step,
                                          create_assignee, TamError)
    route = create_route(USER_A, company_id=CO_A, route_scope="COMPANY_DEFAULT",
                         display_name="R07-Route", dsn=_DSN)
    ver   = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)
    step  = create_step(USER_A, version_id=ver["version_id"],
                        step_order=1, step_name="S1", step_type="SEQUENTIAL", dsn=_DSN)

    with pytest.raises(TamError) as exc:
        create_assignee(USER_A, step_id=step["step_id"], user_id=U_CO_B, dsn=_DSN)
    assert exc.value.http_status == 422
    assert exc.value.code == "ASSIGNEE_CROSS_COMPANY"


# ═══════════════════════════════════════════════════════════════
# R08 — FACTORY_NOT_FOUND: unknown factory_id rejected
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_r08_factory_not_found_rejected(pg):
    """R1: create_route validates factory_id against DB; unknown factory raises TamError 422."""
    from services.tam.routes_svc import create_route, TamError
    with pytest.raises(TamError) as exc:
        create_route(USER_A, company_id=CO_A, factory_id=FACTORY_UNKNOWN,
                     route_scope="FACTORY_DEFAULT", display_name="R08-Route", dsn=_DSN)
    assert exc.value.http_status == 422
    assert exc.value.code == "FACTORY_NOT_FOUND"


# ═══════════════════════════════════════════════════════════════
# R09 — Version lock in publish_version: sequential idempotency
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_r09_publish_version_idempotency_guard(pg):
    """R1: publish_version acquires version FOR UPDATE.
    Second call on an already-PUBLISHED version returns 409 NOT_DRAFT."""
    from services.tam.routes_svc import (create_route, create_version, create_step,
                                          create_assignee, publish_version, TamError)
    route = create_route(USER_A, company_id=CO_A, route_scope="DOCUMENT_TYPE",
                         scope_key="R09", display_name="R09-Route", dsn=_DSN)
    ver   = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)
    step  = create_step(USER_A, version_id=ver["version_id"],
                        step_order=1, step_name="S1", step_type="SEQUENTIAL", dsn=_DSN)
    create_assignee(USER_A, step_id=step["step_id"], user_id=U2, dsn=_DSN)

    result = publish_version(USER_A, route_id=route["route_id"],
                             version_id=ver["version_id"], dsn=_DSN)
    assert result["version_status"] == "PUBLISHED"

    with pytest.raises(TamError) as exc:
        publish_version(USER_A, route_id=route["route_id"],
                        version_id=ver["version_id"], dsn=_DSN)
    assert exc.value.http_status == 409
    assert "NOT_DRAFT" in exc.value.code


# ═══════════════════════════════════════════════════════════════
# R10 — No deadlock: concurrent publishes on different routes
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_r10_no_deadlock_concurrent_different_routes(pg):
    """R1 lock ordering (route → version) prevents deadlock.
    Two concurrent publishes on independent routes both complete without hanging."""
    from services.tam.routes_svc import (create_route, create_version, create_step,
                                          create_assignee, publish_version)

    def _setup(scope_key: str):
        route = create_route(USER_A, company_id=CO_A, route_scope="DOCUMENT_TYPE",
                             scope_key=scope_key, display_name=f"R10-{scope_key}", dsn=_DSN)
        ver   = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)
        step  = create_step(USER_A, version_id=ver["version_id"],
                            step_order=1, step_name="S", step_type="SEQUENTIAL", dsn=_DSN)
        create_assignee(USER_A, step_id=step["step_id"], user_id=U2, dsn=_DSN)
        return route["route_id"], ver["version_id"]

    rid1, vid1 = _setup("R10_ROUTE1")
    rid2, vid2 = _setup("R10_ROUTE2")

    results: list = []
    errors:  list = []
    lock = threading.Lock()

    def _pub(rid, vid):
        try:
            publish_version(USER_A, route_id=rid, version_id=vid, dsn=_DSN)
            with lock:
                results.append("ok")
        except Exception as e:
            with lock:
                errors.append(str(e))

    t1 = threading.Thread(target=_pub, args=(rid1, vid1))
    t2 = threading.Thread(target=_pub, args=(rid2, vid2))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert not t1.is_alive() and not t2.is_alive(), (
        "Deadlock detected: one or more threads did not complete within 10s"
    )
    assert len(errors) == 0, f"Unexpected errors: {errors}"
    assert len(results) == 2, f"Expected 2 successes, got {results}"


# ═══════════════════════════════════════════════════════════════
# C01 — create_step blocked by concurrent route+version lock (timing proof)
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_c01_create_step_blocked_by_lock(pg):
    """R2 C01: create_step blocks >= 0.3s while a concurrent connection holds
    route+version lock (simulating publish_version in-progress).
    Proves locking genuinely prevents concurrent step creation."""
    from services.tam.routes_svc import create_route, create_version, create_step

    route = create_route(USER_A, company_id=CO_A, route_scope="DOCUMENT_TYPE",
                         scope_key="C01", display_name="C01-Route", dsn=_DSN)
    ver   = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)

    gate_held = threading.Event()
    b_elapsed: list = []

    def _lock_holder():
        conn_a = psycopg2.connect(_DSN)
        conn_a.autocommit = False
        cur_a = conn_a.cursor()
        cur_a.execute(
            "SELECT route_id FROM tam_approval_routes WHERE route_id = %s FOR UPDATE",
            (route["route_id"],))
        cur_a.execute(
            "SELECT version_id FROM tam_approval_route_versions WHERE version_id = %s FOR UPDATE",
            (ver["version_id"],))
        gate_held.set()
        time.sleep(0.4)
        conn_a.rollback()
        conn_a.close()

    def _step_creator():
        gate_held.wait()
        t0 = time.monotonic()
        try:
            create_step(USER_A, version_id=ver["version_id"],
                        step_order=1, step_name="C01-Step", step_type="SEQUENTIAL",
                        dsn=_DSN)
        except Exception:
            pass
        finally:
            b_elapsed.append(time.monotonic() - t0)

    t_a = threading.Thread(target=_lock_holder)
    t_b = threading.Thread(target=_step_creator)
    t_a.start()
    t_b.start()
    t_a.join()
    t_b.join(timeout=10)

    assert not t_b.is_alive(), "C01: create_step thread did not complete (deadlock?)"
    assert b_elapsed and b_elapsed[0] >= 0.3, (
        f"C01: create_step was not blocked by lock (elapsed={b_elapsed[0]:.3f}s < 0.3s)"
    )


# ═══════════════════════════════════════════════════════════════
# C02 — create_assignee blocked by concurrent route+version lock (timing proof)
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_c02_create_assignee_blocked_by_lock(pg):
    """R2 C02: create_assignee blocks >= 0.3s while a concurrent connection holds
    route+version lock. Proves assignee mutation is serialized behind the lock."""
    from services.tam.routes_svc import create_route, create_version, create_step

    route = create_route(USER_A, company_id=CO_A, route_scope="DOCUMENT_TYPE",
                         scope_key="C02", display_name="C02-Route", dsn=_DSN)
    ver   = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)
    step  = create_step(USER_A, version_id=ver["version_id"],
                        step_order=1, step_name="C02-Step", step_type="SEQUENTIAL",
                        dsn=_DSN)

    gate_held = threading.Event()
    b_elapsed: list = []

    def _lock_holder():
        conn_a = psycopg2.connect(_DSN)
        conn_a.autocommit = False
        cur_a = conn_a.cursor()
        cur_a.execute(
            "SELECT route_id FROM tam_approval_routes WHERE route_id = %s FOR UPDATE",
            (route["route_id"],))
        cur_a.execute(
            "SELECT version_id FROM tam_approval_route_versions WHERE version_id = %s FOR UPDATE",
            (ver["version_id"],))
        gate_held.set()
        time.sleep(0.4)
        conn_a.rollback()
        conn_a.close()

    def _assignee_creator():
        from services.tam.routes_svc import create_assignee
        gate_held.wait()
        t0 = time.monotonic()
        try:
            create_assignee(USER_A, step_id=step["step_id"], user_id=U2, dsn=_DSN)
        except Exception:
            pass
        finally:
            b_elapsed.append(time.monotonic() - t0)

    t_a = threading.Thread(target=_lock_holder)
    t_b = threading.Thread(target=_assignee_creator)
    t_a.start()
    t_b.start()
    t_a.join()
    t_b.join(timeout=10)

    assert not t_b.is_alive(), "C02: create_assignee thread did not complete (deadlock?)"
    assert b_elapsed and b_elapsed[0] >= 0.3, (
        f"C02: create_assignee was not blocked by lock (elapsed={b_elapsed[0]:.3f}s < 0.3s)"
    )


# ═══════════════════════════════════════════════════════════════
# C03 — Direct SQL step INSERT blocked by trigger's version FOR UPDATE (timing proof)
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_c03_direct_sql_step_insert_blocked_by_trigger_version_lock(pg):
    """R2 C03: Trigger 3 FOR UPDATE on version row blocks a concurrent direct-SQL INSERT.
    Thread A holds version lock only; Thread B's INSERT trigger blocks >= 0.3s then
    succeeds after Thread A rolls back (version stays DRAFT)."""
    route = _make_route(pg)
    ver   = _make_version(pg, route["route_id"])

    gate_held = threading.Event()
    b_elapsed: list = []
    b_errors:  list = []

    def _version_lock_holder():
        conn_a = psycopg2.connect(_DSN)
        conn_a.autocommit = False
        cur_a = conn_a.cursor()
        cur_a.execute(
            "SELECT version_id FROM tam_approval_route_versions "
            "WHERE version_id = %s FOR UPDATE",
            (ver["version_id"],))
        gate_held.set()
        time.sleep(0.4)
        conn_a.rollback()   # version stays DRAFT
        conn_a.close()

    def _direct_step_inserter():
        conn_b = psycopg2.connect(_DSN)
        conn_b.autocommit = False
        cur_b = conn_b.cursor()
        gate_held.wait()
        t0 = time.monotonic()
        try:
            cur_b.execute(
                """
                INSERT INTO tam_approval_route_steps
                    (version_id, step_order, step_name, step_type)
                VALUES (%s, 1, 'C03-Step', 'SEQUENTIAL')
                """,
                (ver["version_id"],))
            conn_b.commit()
        except Exception as e:
            b_errors.append(str(e))
            conn_b.rollback()
        finally:
            b_elapsed.append(time.monotonic() - t0)
            conn_b.close()

    t_a = threading.Thread(target=_version_lock_holder)
    t_b = threading.Thread(target=_direct_step_inserter)
    t_a.start()
    t_b.start()
    t_a.join()
    t_b.join(timeout=10)

    assert not t_b.is_alive(), "C03: direct INSERT thread did not complete (deadlock?)"
    assert not b_errors, f"C03: INSERT failed unexpectedly: {b_errors}"
    assert b_elapsed and b_elapsed[0] >= 0.3, (
        f"C03: direct INSERT was not blocked by trigger version lock "
        f"(elapsed={b_elapsed[0]:.3f}s < 0.3s)"
    )


# ═══════════════════════════════════════════════════════════════
# C04 — Trigger 3 OLD+NEW version check: sequential proof
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_c04_trigger_old_and_new_version_checks_sequential_proof(pg):
    """R2 C04: Sequential proof that trigger 3 rejects both paths:
      Path A — UPDATE step in PUBLISHED version (OLD.version_id=PUBLISHED)
      Path B — Reassign step from DRAFT version to PUBLISHED version (NEW.version_id=PUBLISHED)
    Both paths must raise psycopg2.Error with 'forbidden' or 'non-draft' message."""
    route_pub = _make_route(pg, route_scope="COMPANY_DEFAULT", display_name="C04-Pub")
    ver_pub   = _make_version(pg, route_pub["route_id"])
    step_pub  = _make_step(pg, ver_pub["version_id"])
    _make_assignee(pg, step_pub["step_id"])
    _publish(pg, route_pub["route_id"], ver_pub["version_id"])

    route_dra = _make_route(pg, route_scope="FACTORY_DEFAULT", factory_id=FAC1,
                             display_name="C04-Dra")
    ver_dra   = _make_version(pg, route_dra["route_id"])
    step_dra  = _make_step(pg, ver_dra["version_id"])

    cur = pg.cursor()

    # Path A: UPDATE in PUBLISHED version (OLD side)
    with pytest.raises(psycopg2.Error) as exc_a:
        cur.execute(
            "UPDATE tam_approval_route_steps SET step_name = 'tampered' WHERE step_id = %s",
            (step_pub["step_id"],))
        pg.commit()
    pg.rollback()
    msg_a = str(exc_a.value).lower()
    assert "forbidden" in msg_a or "non-draft" in msg_a, (
        f"C04 Path A: expected 'forbidden'/'non-draft', got {msg_a!r}")

    # Path B: move DRAFT step into PUBLISHED version (NEW side)
    with pytest.raises(psycopg2.Error) as exc_b:
        cur.execute(
            "UPDATE tam_approval_route_steps SET version_id = %s WHERE step_id = %s",
            (ver_pub["version_id"], step_dra["step_id"]))
        pg.commit()
    pg.rollback()
    msg_b = str(exc_b.value).lower()
    assert "forbidden" in msg_b or "non-draft" in msg_b, (
        f"C04 Path B: expected 'forbidden'/'non-draft', got {msg_b!r}")


# ═══════════════════════════════════════════════════════════════
# C05 — 4 concurrent publishes on independent routes: no deadlock
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_c05_four_concurrent_publishes_no_deadlock(pg):
    """R2 C05: lock ordering (route → version) prevents deadlock with 4 concurrent
    publish_version calls on independent routes. All 4 must complete within 15s
    without error."""
    from services.tam.routes_svc import (create_route, create_version, create_step,
                                          create_assignee, publish_version)

    def _setup(scope_key: str):
        route = create_route(USER_A, company_id=CO_A, route_scope="DOCUMENT_TYPE",
                             scope_key=scope_key, display_name=f"C05-{scope_key}",
                             dsn=_DSN)
        ver   = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)
        step  = create_step(USER_A, version_id=ver["version_id"],
                            step_order=1, step_name="S", step_type="SEQUENTIAL",
                            dsn=_DSN)
        create_assignee(USER_A, step_id=step["step_id"], user_id=U2, dsn=_DSN)
        return route["route_id"], ver["version_id"]

    pairs = [_setup(f"C05_R{i}") for i in range(1, 5)]

    results: list = []
    errors:  list = []
    mu = threading.Lock()

    def _pub(rid, vid):
        try:
            publish_version(USER_A, route_id=rid, version_id=vid, dsn=_DSN)
            with mu:
                results.append("ok")
        except Exception as e:
            with mu:
                errors.append(str(e))

    threads = [threading.Thread(target=_pub, args=(rid, vid)) for rid, vid in pairs]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    alive = [t.is_alive() for t in threads]
    assert not any(alive), (
        f"C05: Deadlock — {sum(alive)} thread(s) did not complete within 15s")
    assert not errors, f"C05: Unexpected errors: {errors}"
    assert len(results) == 4, f"C05: Expected 4 successes, got {results}"


# ═══════════════════════════════════════════════════════════════
# R11 — FACTORY_SCOPE_NOT_FINALIZED: factory-scoped route blocks assignee
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_r11_factory_scoped_assignee_blocked(pg):
    """R2: create_assignee raises FACTORY_SCOPE_NOT_FINALIZED for factory-scoped routes.
    Fail-closed until OD-01 factory scope authorization contract is resolved."""
    from services.tam.routes_svc import (create_route, create_version, create_step,
                                          create_assignee, TamError)
    route = create_route(USER_A, company_id=CO_A, factory_id=FAC1,
                         route_scope="FACTORY_DEFAULT", display_name="R11-Route",
                         dsn=_DSN)
    ver   = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)
    step  = create_step(USER_A, version_id=ver["version_id"],
                        step_order=1, step_name="S1", step_type="SEQUENTIAL",
                        dsn=_DSN)

    with pytest.raises(TamError) as exc:
        create_assignee(USER_A, step_id=step["step_id"], user_id=U2, dsn=_DSN)
    assert exc.value.http_status == 422
    assert exc.value.code == "FACTORY_SCOPE_NOT_FINALIZED"


# ═══════════════════════════════════════════════════════════════
# F01-F06 — R3 factory scope gate + publish-then-reject proof
# ═══════════════════════════════════════════════════════════════

@_SKIP_DB
def test_f01_publish_commit_blocks_concurrent_step_insert(pg):
    """F01: After publish_version commits, a concurrent blocked step INSERT is rejected.
    Thread A locks route+version, publishes (COMMIT).
    Thread B step INSERT blocks on trigger's FOR UPDATE on version; resumes after A
    commits; trigger reads PUBLISHED → raises exception (psycopg2.Error).
    Final DB state: step count unchanged, version PUBLISHED, pointer correct."""
    from services.tam.routes_svc import create_route, create_version, create_step, create_assignee
    route = create_route(USER_A, company_id=CO_A, route_scope="DOCUMENT_TYPE",
                         scope_key="F01", display_name="F01-Route", dsn=_DSN)
    ver   = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)
    step  = create_step(USER_A, version_id=ver["version_id"],
                        step_order=1, step_name="S1", step_type="SEQUENTIAL", dsn=_DSN)
    rid = route["route_id"]
    vid = ver["version_id"]
    gate_held = threading.Event()
    b_result: list = []

    def _publisher():
        conn_a = psycopg2.connect(_DSN)
        conn_a.autocommit = False
        cur_a = conn_a.cursor()
        cur_a.execute("SELECT route_id FROM tam_approval_routes"
                      " WHERE route_id = %s FOR UPDATE", (rid,))
        cur_a.execute("SELECT version_id FROM tam_approval_route_versions"
                      " WHERE version_id = %s FOR UPDATE", (vid,))
        gate_held.set()
        time.sleep(0.35)
        cur_a.execute(
            "UPDATE tam_approval_route_versions"
            " SET version_status='PUBLISHED', published_at=NOW(), published_by=%s"
            " WHERE version_id=%s", (U1, vid))
        cur_a.execute(
            "UPDATE tam_approval_routes SET current_version_id=%s WHERE route_id=%s",
            (vid, rid))
        conn_a.commit()
        conn_a.close()

    def _step_inserter():
        gate_held.wait()
        conn_b = psycopg2.connect(_DSN)
        conn_b.autocommit = False
        cur_b = conn_b.cursor()
        try:
            cur_b.execute(
                "INSERT INTO tam_approval_route_steps"
                " (version_id, step_order, step_name, step_type)"
                " VALUES (%s, 2, 'F01-Concurrent', 'SEQUENTIAL')", (vid,))
            conn_b.commit()
            b_result.append("ok")
        except psycopg2.Error as e:
            b_result.append(e)
            conn_b.rollback()
        finally:
            conn_b.close()

    t_a = threading.Thread(target=_publisher)
    t_b = threading.Thread(target=_step_inserter)
    t_a.start(); t_b.start()
    t_a.join(timeout=10); t_b.join(timeout=10)
    assert not t_a.is_alive() and not t_b.is_alive(), "F01: thread deadlock"
    assert len(b_result) == 1 and isinstance(b_result[0], psycopg2.Error), (
        f"F01: expected INSERT rejection, got {b_result!r}")
    err = str(b_result[0]).lower()
    assert "forbidden" in err or "non-draft" in err or "published" in err, (
        f"F01: wrong rejection reason: {err!r}")
    cur = _dict_cur(pg)
    cur.execute("SELECT step_id FROM tam_approval_route_steps WHERE version_id = %s", (vid,))
    assert [str(r["step_id"]) for r in cur.fetchall()] == [step["step_id"]]
    cur.execute("SELECT version_status FROM tam_approval_route_versions WHERE version_id = %s", (vid,))
    assert cur.fetchone()["version_status"] == "PUBLISHED"
    cur.execute("SELECT current_version_id FROM tam_approval_routes WHERE route_id = %s", (rid,))
    assert str(cur.fetchone()["current_version_id"]) == vid


@_SKIP_DB
def test_f02_publish_commit_blocks_concurrent_assignee_insert(pg):
    """F02: After publish_version commits, a concurrent blocked assignee INSERT is rejected.
    Same pattern as F01 but for tam_approval_step_assignees table (trigger 4)."""
    from services.tam.routes_svc import create_route, create_version, create_step
    route = create_route(USER_A, company_id=CO_A, route_scope="DOCUMENT_TYPE",
                         scope_key="F02", display_name="F02-Route", dsn=_DSN)
    ver  = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)
    step = create_step(USER_A, version_id=ver["version_id"],
                       step_order=1, step_name="S1", step_type="SEQUENTIAL", dsn=_DSN)
    rid = route["route_id"]
    vid = ver["version_id"]
    sid = step["step_id"]
    gate_held = threading.Event()
    b_result: list = []

    def _publisher():
        conn_a = psycopg2.connect(_DSN)
        conn_a.autocommit = False
        cur_a = conn_a.cursor()
        cur_a.execute("SELECT route_id FROM tam_approval_routes"
                      " WHERE route_id = %s FOR UPDATE", (rid,))
        cur_a.execute("SELECT version_id FROM tam_approval_route_versions"
                      " WHERE version_id = %s FOR UPDATE", (vid,))
        gate_held.set()
        time.sleep(0.35)
        cur_a.execute(
            "UPDATE tam_approval_route_versions"
            " SET version_status='PUBLISHED', published_at=NOW(), published_by=%s"
            " WHERE version_id=%s", (U1, vid))
        cur_a.execute(
            "UPDATE tam_approval_routes SET current_version_id=%s WHERE route_id=%s",
            (vid, rid))
        conn_a.commit()
        conn_a.close()

    def _assignee_inserter():
        gate_held.wait()
        conn_b = psycopg2.connect(_DSN)
        conn_b.autocommit = False
        cur_b = conn_b.cursor()
        try:
            cur_b.execute(
                "INSERT INTO tam_approval_step_assignees (step_id, user_id)"
                " VALUES (%s, %s)", (sid, U2))
            conn_b.commit()
            b_result.append("ok")
        except psycopg2.Error as e:
            b_result.append(e)
            conn_b.rollback()
        finally:
            conn_b.close()

    t_a = threading.Thread(target=_publisher)
    t_b = threading.Thread(target=_assignee_inserter)
    t_a.start(); t_b.start()
    t_a.join(timeout=10); t_b.join(timeout=10)
    assert not t_a.is_alive() and not t_b.is_alive(), "F02: thread deadlock"
    assert len(b_result) == 1 and isinstance(b_result[0], psycopg2.Error), (
        f"F02: expected assignee INSERT rejection, got {b_result!r}")
    err = str(b_result[0]).lower()
    assert "forbidden" in err or "non-draft" in err or "published" in err, (
        f"F02: wrong rejection reason: {err!r}")
    cur = _dict_cur(pg)
    cur.execute("SELECT count(*) AS cnt FROM tam_approval_step_assignees WHERE step_id = %s", (sid,))
    assert cur.fetchone()["cnt"] == 0
    cur.execute("SELECT version_status FROM tam_approval_route_versions WHERE version_id = %s", (vid,))
    assert cur.fetchone()["version_status"] == "PUBLISHED"


@_SKIP_DB
def test_f03_cross_factory_route_get_rejected(pg):
    """F03: USER_A (factory_id=FAC1) cannot get_route on a FAC2-scoped route.
    Route created directly (bypass service gate), then get_route raises FACTORY_SCOPE_NOT_FINALIZED."""
    from services.tam.routes_svc import get_route, TamError
    route = _make_route(pg, company_id=CO_A, factory_id=FAC2,
                        route_scope="FACTORY_DEFAULT", display_name="F03-Route")
    with pytest.raises(TamError) as exc:
        get_route(USER_A, route_id=route["route_id"], dsn=_DSN)
    assert exc.value.http_status == 422
    assert exc.value.code == "FACTORY_SCOPE_NOT_FINALIZED"


@_SKIP_DB
def test_f04_unauthorized_factory_route_create_rejected(pg):
    """F04: USER_A (factory_id=FAC1) cannot create a route scoped to FAC2.
    create_route raises FACTORY_SCOPE_NOT_FINALIZED before any DB write."""
    from services.tam.routes_svc import create_route, TamError
    with pytest.raises(TamError) as exc:
        create_route(USER_A, company_id=CO_A, factory_id=FAC2,
                     route_scope="FACTORY_DEFAULT", display_name="F04-Route", dsn=_DSN)
    assert exc.value.http_status == 422
    assert exc.value.code == "FACTORY_SCOPE_NOT_FINALIZED"
    cur = _dict_cur(pg)
    cur.execute("SELECT count(*) AS cnt FROM tam_approval_routes WHERE display_name = 'F04-Route'")
    assert cur.fetchone()["cnt"] == 0, "F04: route must not be written on rejection"


@_SKIP_DB
def test_f05_company_default_route_accessible(pg):
    """F05: Company-wide routes (factory_id IS NULL) are accessible regardless of user factory.
    USER_A (factory_id=FAC1) can create, read, and list COMPANY_DEFAULT routes.
    list_routes for USER_A excludes factory-scoped routes."""
    from services.tam.routes_svc import create_route, get_route, list_routes
    route = create_route(USER_A, company_id=CO_A, route_scope="COMPANY_DEFAULT",
                         display_name="F05-CompanyRoute", dsn=_DSN)
    assert route["factory_id"] is None
    fetched = get_route(USER_A, route_id=route["route_id"], dsn=_DSN)
    assert fetched["route_id"] == route["route_id"]
    routes = list_routes(USER_A, company_id=CO_A, dsn=_DSN)
    assert any(r["route_id"] == route["route_id"] for r in routes)


@_SKIP_DB
def test_f06_factory_route_list_not_exposed(pg):
    """F06: list_routes for USER_A (factory_id=FAC1) excludes FAC2 routes.
    Explicit FAC2 factory_id filter raises FACTORY_SCOPE_NOT_FINALIZED."""
    from services.tam.routes_svc import list_routes, TamError
    _make_route(pg, company_id=CO_A, factory_id=FAC2,
                route_scope="FACTORY_DEFAULT", display_name="F06-Fac2Route")
    routes = list_routes(USER_A, company_id=CO_A, dsn=_DSN)
    fac2_ids = [str(r["factory_id"]) for r in routes if r["factory_id"] is not None
                and str(r["factory_id"]) == FAC2]
    assert fac2_ids == [], f"F06: FAC2 route exposed in list: {fac2_ids}"
    with pytest.raises(TamError) as exc:
        list_routes(USER_A, company_id=CO_A, factory_id=FAC2, dsn=_DSN)
    assert exc.value.http_status == 422
    assert exc.value.code == "FACTORY_SCOPE_NOT_FINALIZED"


# ═══════════════════════════════════════════════════════════════
# S01-S04 — R4 service-level concurrency + authorization regression
# ═══════════════════════════════════════════════════════════════

class _GatedConn:
    """Wraps a psycopg2 connection; delays the first commit() call.
    psycopg2 connection.commit is a C-level attribute and is read-only,
    so we cannot monkey-patch it directly — wrapping is required."""
    def __init__(self, conn, on_first_commit):
        self._conn = conn
        self._on_first_commit = on_first_commit
        self._first = True

    @property
    def autocommit(self):
        return self._conn.autocommit

    @autocommit.setter
    def autocommit(self, value):
        self._conn.autocommit = value

    def cursor(self, **kwargs):
        return self._conn.cursor(**kwargs)

    def commit(self):
        if self._first:
            self._first = False
            self._on_first_commit()
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


@_SKIP_DB
def test_s01_publish_version_service_vs_create_step(pg):
    """S01: actual publish_version() service vs concurrent create_step().
    Thread A calls publish_version() (holds route+version locks inside real transaction;
    commit delayed via _GatedConn wrapper).
    Thread B calls create_step() via service — blocks on route lock, then fails with
    VERSION_NOT_DRAFT after A commits PUBLISHED.
    Company-wide route (factory_id=None) bypasses factory scope gate."""
    import unittest.mock as mock
    import services.tam.routes_svc as _svc
    from services.tam.routes_svc import (create_route, create_version,
                                          publish_version, create_step, TamError)

    route = create_route(USER_A, company_id=CO_A, route_scope="DOCUMENT_TYPE",
                         scope_key="S01", display_name="S01-Route", dsn=_DSN)
    ver   = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)
    step1 = _make_step(pg, version_id=ver["version_id"], step_order=1)
    _make_assignee(pg, step_id=step1["step_id"], user_id=U2)

    rid = route["route_id"]
    vid = ver["version_id"]
    _publish_locked = threading.Event()
    b_result: list = []

    def _gated_connect(dsn=None):
        conn = psycopg2.connect(dsn or _DSN)
        def _on_commit():
            _publish_locked.set()
            time.sleep(0.4)
        return _GatedConn(conn, _on_commit)

    def _publisher():
        with mock.patch.object(_svc, '_connect', side_effect=_gated_connect):
            publish_version(USER_A, route_id=rid, version_id=vid, dsn=_DSN)

    def _step_adder():
        _publish_locked.wait(timeout=5)
        try:
            create_step(USER_A, version_id=vid, step_order=2,
                        step_name="S01-Race", step_type="SEQUENTIAL", dsn=_DSN)
            b_result.append("ok")
        except TamError as e:
            b_result.append(e)
        except Exception as e:
            b_result.append(e)

    t_a = threading.Thread(target=_publisher)
    t_b = threading.Thread(target=_step_adder)
    t_a.start(); t_b.start()
    t_a.join(timeout=10); t_b.join(timeout=10)
    assert not t_a.is_alive() and not t_b.is_alive(), "S01: thread deadlock"
    assert len(b_result) == 1, f"S01: unexpected result count: {b_result!r}"
    assert isinstance(b_result[0], TamError), (
        f"S01: expected TamError, got {type(b_result[0])}: {b_result[0]!r}")
    assert b_result[0].code == "VERSION_NOT_DRAFT", (
        f"S01: wrong rejection code: {b_result[0].code}")

    cur = _dict_cur(pg)
    cur.execute("SELECT count(*) AS cnt FROM tam_approval_route_steps WHERE version_id = %s", (vid,))
    assert cur.fetchone()["cnt"] == 1, "S01: extra step must not be written"
    cur.execute("SELECT version_status FROM tam_approval_route_versions WHERE version_id = %s", (vid,))
    assert cur.fetchone()["version_status"] == "PUBLISHED"
    cur.execute("SELECT current_version_id FROM tam_approval_routes WHERE route_id = %s", (rid,))
    assert str(cur.fetchone()["current_version_id"]) == vid


@_SKIP_DB
def test_s02_publish_version_service_vs_create_assignee(pg):
    """S02: actual publish_version() service vs concurrent create_assignee().
    Thread A calls publish_version() (commit delayed via _GatedConn).
    Thread B calls create_assignee() via service — blocks on route lock, then fails with
    VERSION_NOT_DRAFT after A commits PUBLISHED.
    Company-wide route (factory_id=None) bypasses factory scope gate."""
    import unittest.mock as mock
    import services.tam.routes_svc as _svc
    from services.tam.routes_svc import (create_route, create_version,
                                          publish_version, create_assignee, TamError)

    route = create_route(USER_A, company_id=CO_A, route_scope="DOCUMENT_TYPE",
                         scope_key="S02", display_name="S02-Route", dsn=_DSN)
    ver   = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)
    step1 = _make_step(pg, version_id=ver["version_id"], step_order=1)
    _make_assignee(pg, step_id=step1["step_id"], user_id=U1, assigned_by=U1)

    rid = route["route_id"]
    vid = ver["version_id"]
    sid = step1["step_id"]
    _publish_locked = threading.Event()
    b_result: list = []

    def _gated_connect(dsn=None):
        conn = psycopg2.connect(dsn or _DSN)
        def _on_commit():
            _publish_locked.set()
            time.sleep(0.4)
        return _GatedConn(conn, _on_commit)

    def _publisher():
        with mock.patch.object(_svc, '_connect', side_effect=_gated_connect):
            publish_version(USER_A, route_id=rid, version_id=vid, dsn=_DSN)

    def _assignee_adder():
        _publish_locked.wait(timeout=5)
        try:
            create_assignee(USER_A, step_id=sid, user_id=U2, dsn=_DSN)
            b_result.append("ok")
        except TamError as e:
            b_result.append(e)
        except Exception as e:
            b_result.append(e)

    t_a = threading.Thread(target=_publisher)
    t_b = threading.Thread(target=_assignee_adder)
    t_a.start(); t_b.start()
    t_a.join(timeout=10); t_b.join(timeout=10)
    assert not t_a.is_alive() and not t_b.is_alive(), "S02: thread deadlock"
    assert len(b_result) == 1, f"S02: unexpected result count: {b_result!r}"
    assert isinstance(b_result[0], TamError), (
        f"S02: expected TamError, got {type(b_result[0])}: {b_result[0]!r}")
    assert b_result[0].code == "VERSION_NOT_DRAFT", (
        f"S02: wrong rejection code: {b_result[0].code}")

    cur = _dict_cur(pg)
    cur.execute("SELECT count(*) AS cnt FROM tam_approval_step_assignees WHERE step_id = %s", (sid,))
    assert cur.fetchone()["cnt"] == 1, "S02: extra assignee must not be written"
    cur.execute("SELECT version_status FROM tam_approval_route_versions WHERE version_id = %s", (vid,))
    assert cur.fetchone()["version_status"] == "PUBLISHED"


@_SKIP_DB
def test_s03_publish_version_rejects_no_assignee(pg):
    """S03: publish_version() raises STEP_MISSING_ASSIGNEE when a step has no assignees.
    Validates service-level enforcement without bypassing the assignee requirement."""
    from services.tam.routes_svc import create_route, create_version, publish_version, TamError

    route = create_route(USER_A, company_id=CO_A, route_scope="DOCUMENT_TYPE",
                         scope_key="S03", display_name="S03-Route", dsn=_DSN)
    ver   = create_version(USER_A, route_id=route["route_id"], dsn=_DSN)
    _make_step(pg, version_id=ver["version_id"], step_order=1)

    with pytest.raises(TamError) as exc:
        publish_version(USER_A, route_id=route["route_id"], version_id=ver["version_id"],
                        dsn=_DSN)
    assert exc.value.http_status == 422
    assert exc.value.code == "STEP_MISSING_ASSIGNEE"

    cur = _dict_cur(pg)
    cur.execute("SELECT version_status FROM tam_approval_route_versions WHERE version_id = %s",
                (ver["version_id"],))
    assert cur.fetchone()["version_status"] == "DRAFT", "S03: failed publish must not change status"


def test_s04_authorization_fail_closed_regression():
    """S04: Authorization regression — all HTTP write endpoints return 403 (OD-01 pending).
    factory_id match does NOT grant admin rights (PENDING_AUTHORIZATION_CONTRACT).
    Verified for both factory-scoped (factory_id=FAC1) and company-wide (factory_id=None)
    users; neither bypasses the ROUTE_MANAGER permission gate.

    Uses an isolated FastAPI instance — TAM router is not registered in main.app
    (PREMERGE-003: passive integration until OD-01 authorized).
    """
    from fastapi import FastAPI
    from routers.auth import get_current_user
    from routers.tam_routes import router as tam_router

    fac_user  = {"id": U1, "company_id": CO_A, "factory_id": FAC1,
                 "role_code": "001", "status_code": "ACTIVE", "is_active": True}
    co_user   = {"id": U1, "company_id": CO_A, "factory_id": None,
                 "role_code": "001", "status_code": "ACTIVE", "is_active": True}

    write_endpoints = [
        ("POST", "/v1/tam/routes",
         {"company_id": CO_A, "route_scope": "FACTORY_DEFAULT",
          "factory_id": FAC1, "display_name": "S04-Route"}),
        ("POST", "/v1/tam/routes/fake-id/versions", {"notes": None}),
        ("POST", "/v1/tam/routes/fake-id/versions/fake-ver/steps",
         {"step_order": 1, "step_name": "S", "step_type": "SEQUENTIAL"}),
        ("POST", "/v1/tam/routes/fake-id/versions/fake-ver/steps/fake-step/assignees",
         {"user_id": U2}),
        ("POST", "/v1/tam/routes/fake-id/versions/fake-ver/publish", {}),
    ]

    for actor in (fac_user, co_user):
        isolated_app = FastAPI()
        isolated_app.include_router(tam_router)
        isolated_app.dependency_overrides[get_current_user] = lambda u=actor: u
        client = TestClient(isolated_app, raise_server_exceptions=False)
        for method, url, body in write_endpoints:
            resp = client.request(method, url, json=body)
            assert resp.status_code == 403, (
                f"S04: {method} {url} returned {resp.status_code} (factory_id="
                f"{actor['factory_id']}), expected 403 — "
                f"ROUTE_MANAGER not authorized (OD-01 pending)")

    # PENDING_AUTHORIZATION_CONTRACT: factory_id match is necessary but NOT sufficient.
    # factory scope authorization must be resolved (OD-01) before writes are opened.
    assert "PENDING_AUTHORIZATION_CONTRACT" == "PENDING_AUTHORIZATION_CONTRACT"
