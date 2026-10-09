"""TAM-008C DB Security tests.

S01-S07:  RLS enabled on all 7 TAM tables
S08-S14:  anon role has zero table privileges
S15-S21:  authenticated role has zero table privileges
S22-S28:  service_role has correct grants per table
S29-S35:  trigger function EXECUTE revoked from PUBLIC (verified via proacl)

Test environment:
  Local PostgreSQL via TAM_008C_PG_DSN env var
  (default: host=localhost dbname=tai_test_tam_ledger)
  Module-scoped fixture creates stub roles (anon/authenticated/service_role),
  stub reference tables, and applies the two security migrations.
  All DB tests are skipped if the DSN is unreachable.
"""
from __future__ import annotations

import os
import pathlib
import uuid

import psycopg2
import psycopg2.extras
import pytest

# ── DSN ───────────────────────────────────────────────────────────────────────

_DSN = os.getenv("TAM_008C_PG_DSN", "host=localhost dbname=tai_test_tam_ledger")

_MIGRATION_DIR = (
    pathlib.Path(__file__).parent.parent / "supabase" / "migrations"
)
_MIG_ROUTES = (
    _MIGRATION_DIR / "20261009010001_tam_approval_route_foundation_security.sql"
).read_text()
_MIG_LEDGER = (
    _MIGRATION_DIR / "20261009010002_tam_permission_ledger_foundation_security.sql"
).read_text()

# ── Table / function catalogs ──────────────────────────────────────────────────

_ROUTE_TABLES = [
    "tam_approval_routes",
    "tam_approval_route_versions",
    "tam_approval_route_steps",
    "tam_approval_step_assignees",
]
_LEDGER_TABLES = [
    "tam_approval_audit_events",
    "tam_permission_grants",
    "tam_permission_revocations",
]
_ALL_TAM_TABLES = _ROUTE_TABLES + _LEDGER_TABLES

_ROUTE_FUNCTIONS = [
    "tam_routes_published_guard_fn",
    "tam_version_immutability_fn",
    "tam_steps_draft_only_fn",
    "tam_assignees_draft_only_fn",
]
_LEDGER_FUNCTIONS = [
    "tam_audit_immutability_fn",
    "tam_grants_immutability_fn",
    "tam_revocations_immutability_fn",
]
_ALL_TAM_FUNCTIONS = _ROUTE_FUNCTIONS + _LEDGER_FUNCTIONS

# Expected service_role grants per table (append-only = SELECT+INSERT only)
_SERVICE_ROLE_GRANTS: dict[str, set[str]] = {
    "tam_approval_routes":         {"SELECT", "INSERT", "UPDATE"},
    "tam_approval_route_versions": {"SELECT", "INSERT", "UPDATE"},
    "tam_approval_route_steps":    {"SELECT", "INSERT", "UPDATE", "DELETE"},
    "tam_approval_step_assignees": {"SELECT", "INSERT", "UPDATE", "DELETE"},
    "tam_approval_audit_events":   {"SELECT", "INSERT"},
    "tam_permission_grants":       {"SELECT", "INSERT"},
    "tam_permission_revocations":  {"SELECT", "INSERT"},
}

_APPEND_ONLY_TABLES = {
    "tam_approval_audit_events",
    "tam_permission_grants",
    "tam_permission_revocations",
}

# ── Availability check ─────────────────────────────────────────────────────────

def _pg_available() -> bool:
    try:
        conn = psycopg2.connect(_DSN, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _pg_available(), reason="PostgreSQL unavailable")

# ── Stable UUIDs ──────────────────────────────────────────────────────────────

_CO_A = "aaaaaaaa-0001-0001-0001-000000000001"
_CO_B = "bbbbbbbb-0002-0002-0002-000000000002"
_FAC1 = "ffffffff-0001-0001-0001-000000000001"
_FAC2 = "ffffffff-0002-0002-0002-000000000002"

# ── Module-scoped fixture ──────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def pg():
    """Bootstrap: stub roles + stub tables + apply security migrations."""
    conn = psycopg2.connect(_DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Create Supabase-equivalent roles if absent
    for role in ("anon", "authenticated", "service_role"):
        cur.execute(
            f"""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    CREATE ROLE {role};
                END IF;
            END $$;
            """
        )

    # Drop existing TAM tables (dependency order)
    cur.execute("""
        DROP TABLE IF EXISTS
            tam_approval_step_assignees,
            tam_approval_route_steps,
            tam_approval_route_versions,
            tam_approval_routes,
            tam_permission_revocations,
            tam_permission_grants,
            tam_approval_audit_events
        CASCADE;
    """)

    # Drop existing TAM trigger functions
    cur.execute("""
        DROP FUNCTION IF EXISTS
            tam_routes_published_guard_fn,
            tam_version_immutability_fn,
            tam_steps_draft_only_fn,
            tam_assignees_draft_only_fn,
            tam_audit_immutability_fn,
            tam_grants_immutability_fn,
            tam_revocations_immutability_fn
        CASCADE;
    """)

    # Create stub reference tables (factories includes UNIQUE constraint
    # needed for tam_grants_factory_scope FK — same as 20261009010000)
    cur.execute("""
        DROP TABLE IF EXISTS users, factories, companies CASCADE;

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
            id         UUID PRIMARY KEY,
            company_id UUID NOT NULL REFERENCES companies(id)
        );
    """)

    cur.execute(
        "INSERT INTO companies (id) VALUES (%s), (%s)",
        (_CO_A, _CO_B),
    )
    cur.execute(
        "INSERT INTO factories (id, company_id) VALUES (%s, %s), (%s, %s)",
        (_FAC1, _CO_A, _FAC2, _CO_A),
    )

    # Apply security migrations
    cur.execute(_MIG_ROUTES)
    cur.execute(_MIG_LEDGER)

    yield cur

    # Teardown: remove route tables so ledger test D16 isolation is preserved
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

    conn.close()


# ── S01-S07: RLS enabled on all 7 TAM tables ──────────────────────────────────

@pytest.mark.parametrize("table,sid", [
    ("tam_approval_routes",         "S01"),
    ("tam_approval_route_versions", "S02"),
    ("tam_approval_route_steps",    "S03"),
    ("tam_approval_step_assignees", "S04"),
    ("tam_approval_audit_events",   "S05"),
    ("tam_permission_grants",       "S06"),
    ("tam_permission_revocations",  "S07"),
])
def test_rls_enabled(pg, table, sid):
    """RLS must be enabled on every TAM table."""
    pg.execute(
        "SELECT relrowsecurity FROM pg_class WHERE relname = %s AND relkind = 'r'",
        (table,),
    )
    row = pg.fetchone()
    assert row is not None, f"{sid}: table {table} not found in pg_class"
    assert row["relrowsecurity"] is True, f"{sid}: RLS not enabled on {table}"


# ── S08-S14: anon has zero table privileges ────────────────────────────────────

@pytest.mark.parametrize("table,sid", [
    ("tam_approval_routes",         "S08"),
    ("tam_approval_route_versions", "S09"),
    ("tam_approval_route_steps",    "S10"),
    ("tam_approval_step_assignees", "S11"),
    ("tam_approval_audit_events",   "S12"),
    ("tam_permission_grants",       "S13"),
    ("tam_permission_revocations",  "S14"),
])
def test_anon_no_privileges(pg, table, sid):
    """anon must have no SELECT/INSERT/UPDATE/DELETE on any TAM table."""
    for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        pg.execute(
            "SELECT has_table_privilege('anon', %s, %s)",
            (table, priv),
        )
        assert pg.fetchone()["has_table_privilege"] is False, (
            f"{sid}: anon should not have {priv} on {table}"
        )


# ── S15-S21: authenticated has zero table privileges ──────────────────────────

@pytest.mark.parametrize("table,sid", [
    ("tam_approval_routes",         "S15"),
    ("tam_approval_route_versions", "S16"),
    ("tam_approval_route_steps",    "S17"),
    ("tam_approval_step_assignees", "S18"),
    ("tam_approval_audit_events",   "S19"),
    ("tam_permission_grants",       "S20"),
    ("tam_permission_revocations",  "S21"),
])
def test_authenticated_no_privileges(pg, table, sid):
    """authenticated must have no SELECT/INSERT/UPDATE/DELETE on any TAM table."""
    for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        pg.execute(
            "SELECT has_table_privilege('authenticated', %s, %s)",
            (table, priv),
        )
        assert pg.fetchone()["has_table_privilege"] is False, (
            f"{sid}: authenticated should not have {priv} on {table}"
        )


# ── S22-S28: service_role has correct grants ───────────────────────────────────

@pytest.mark.parametrize("table,sid", [
    ("tam_approval_routes",         "S22"),
    ("tam_approval_route_versions", "S23"),
    ("tam_approval_route_steps",    "S24"),
    ("tam_approval_step_assignees", "S25"),
    ("tam_approval_audit_events",   "S26"),
    ("tam_permission_grants",       "S27"),
    ("tam_permission_revocations",  "S28"),
])
def test_service_role_grants(pg, table, sid):
    """service_role must have exactly the declared grants per table."""
    expected = _SERVICE_ROLE_GRANTS[table]
    for priv in expected:
        pg.execute(
            "SELECT has_table_privilege('service_role', %s, %s)",
            (table, priv),
        )
        assert pg.fetchone()["has_table_privilege"] is True, (
            f"{sid}: service_role should have {priv} on {table}"
        )
    # Append-only tables: UPDATE and DELETE must NOT be granted
    if table in _APPEND_ONLY_TABLES:
        for priv in ("UPDATE", "DELETE"):
            pg.execute(
                "SELECT has_table_privilege('service_role', %s, %s)",
                (table, priv),
            )
            assert pg.fetchone()["has_table_privilege"] is False, (
                f"{sid}: service_role must NOT have {priv} on append-only {table}"
            )


# ── S29-S35: trigger function EXECUTE revoked from PUBLIC ─────────────────────

@pytest.mark.parametrize("fn_name,sid", [
    ("tam_routes_published_guard_fn",   "S29"),
    ("tam_version_immutability_fn",     "S30"),
    ("tam_steps_draft_only_fn",         "S31"),
    ("tam_assignees_draft_only_fn",     "S32"),
    ("tam_audit_immutability_fn",       "S33"),
    ("tam_grants_immutability_fn",      "S34"),
    ("tam_revocations_immutability_fn", "S35"),
])
def test_trigger_fn_execute_revoked_from_public(pg, fn_name, sid):
    """EXECUTE must be revoked from PUBLIC for all TAM trigger functions.

    proacl IS NULL means the default ACL applies (PUBLIC has EXECUTE).
    After REVOKE EXECUTE ... FROM PUBLIC, proacl is explicitly set —
    the absence of a '=X...' entry confirms PUBLIC has no EXECUTE.
    """
    pg.execute(
        """
        SELECT
            proacl IS NOT NULL                                   AS acl_explicit,
            CASE
                WHEN proacl IS NULL THEN FALSE
                ELSE NOT EXISTS (
                    SELECT 1
                    FROM unnest(proacl) AS a
                    WHERE a::text ~ '^=[^/]*X'
                )
            END                                                  AS public_execute_revoked
        FROM pg_proc
        JOIN pg_namespace ON pg_namespace.oid = pg_proc.pronamespace
        WHERE proname = %s
          AND nspname = 'public'
        """,
        (fn_name,),
    )
    row = pg.fetchone()
    assert row is not None, f"{sid}: function {fn_name} not found in pg_proc"
    assert row["acl_explicit"] is True, (
        f"{sid}: proacl IS NULL for {fn_name} — REVOKE FROM PUBLIC was not applied"
    )
    assert row["public_execute_revoked"] is True, (
        f"{sid}: PUBLIC still has EXECUTE on {fn_name}"
    )
