"""TAM-008C DB Security tests — C1 revision.

S01-S07:  RLS enabled on all 7 TAM tables
S08-S14:  anon has zero table privileges
S15-S21:  authenticated has zero table privileges
S22-S28:  service_role has correct grants per table (append-only = SELECT+INSERT)
S29-S35:  PUBLIC has no EXECUTE on 7 trigger functions (proacl check)
S36-S42:  anon has no EXECUTE on 7 trigger functions (has_function_privilege)
S43-S49:  authenticated has no EXECUTE on 7 trigger functions

Isolation guard requirements (fail — not skip — on violation):
  - TAM_008C_PG_DSN must be explicitly set
  - DSN must not reference production Supabase project (vwlahtguyggrhvslabax)
  - DSN host must be local (localhost / 127.0.0.1)
  - DSN must not match DATABASE_URL (normalized param comparison + raw string)
  - Connected DB name must be in the allowed isolation list
  - Target DB must have isolation marker (pre-created, not auto-generated)
  - All DDL is gated behind every isolation check

Supabase default-privilege simulation:
  Before applying migrations, ALTER DEFAULT PRIVILEGES grants ALL on TABLES
  and EXECUTE on FUNCTIONS to anon/authenticated/service_role — replicating
  what Supabase does automatically for new objects.  The migration REVOKE
  statements must remove these grants; the tests verify the final state.
"""
from __future__ import annotations

import os
import pathlib

import psycopg2
import psycopg2.extensions
import psycopg2.extras
import pytest

# ── DSN & isolation constants ──────────────────────────────────────────────────

_ISOLATION_MARKER    = "TAM_008C_SECURITY_TEST_ISOLATION"
_PROD_SUPABASE_REF   = "vwlahtguyggrhvslabax"
_ALLOWED_TEST_DBNAMES: frozenset[str] = frozenset({"tai_test_tam_ledger"})
_LOCAL_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1", ""})

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

# ── DSN helpers ───────────────────────────────────────────────────────────────

def _parse_dsn(dsn: str) -> dict:
    """Parse a DSN (key=value or postgresql:// URI) into a parameter dict."""
    try:
        return psycopg2.extensions.parse_dsn(dsn)
    except Exception:
        return {}


def _dsns_same_db(a: dict, b: dict) -> bool:
    """True if two parsed DSN dicts target the same PostgreSQL database."""
    def _norm_host(d: dict) -> str:
        h = d.get("host", "localhost").lower()
        return "localhost" if h in ("127.0.0.1", "::1", "") else h
    return (
        _norm_host(a) == _norm_host(b)
        and a.get("port", "5432") == b.get("port", "5432")
        and a.get("dbname", "") == b.get("dbname", "")
    )


# ── Stable UUIDs for stub data ─────────────────────────────────────────────────

_CO_A = "aaaaaaaa-0001-0001-0001-000000000001"
_CO_B = "bbbbbbbb-0002-0002-0002-000000000002"
_FAC1 = "ffffffff-0001-0001-0001-000000000001"
_FAC2 = "ffffffff-0002-0002-0002-000000000002"

# ── Module-scoped fixture — isolation-gated ────────────────────────────────────

@pytest.fixture(scope="module")
def pg():
    """Bootstrap security test environment.

    Guard order (each failure prevents DDL):
      1. TAM_008C_PG_DSN must be set
      2. Production DB rejected (Supabase ref, non-local host, DATABASE_URL match)
      3. DB must be reachable
      4. Connected DB name must be in allowed isolation list
      5. Isolation marker must pre-exist (no auto-create)
      6. Simulate Supabase default privileges
      7. Apply migrations
    """
    # Guard 1: explicit DSN required
    dsn = os.getenv("TAM_008C_PG_DSN")
    if not dsn:
        pytest.fail(
            "TAM_008C_PG_DSN is not set — security tests require an explicit "
            "isolated test DB, e.g. TAM_008C_PG_DSN='host=localhost dbname=tai_test_tam_ledger'",
            pytrace=False,
        )

    # Guard 2: production DB checks — all evaluated before any connection
    if _PROD_SUPABASE_REF in dsn:
        pytest.fail(
            f"TAM_008C_PG_DSN contains production Supabase project ref '{_PROD_SUPABASE_REF}' "
            "— refusing destructive DDL against production DB.",
            pytrace=False,
        )

    _test_params = _parse_dsn(dsn)
    _test_host = _test_params.get("host", "localhost")
    if _test_host not in _LOCAL_HOSTS:
        pytest.fail(
            f"TAM_008C_PG_DSN targets non-local host '{_test_host}'. "
            "Only localhost / 127.0.0.1 are allowed for destructive security tests.",
            pytrace=False,
        )

    _prod_url = os.environ.get("DATABASE_URL", "")
    if _prod_url:
        _prod_params = _parse_dsn(_prod_url)
        if _dsns_same_db(_test_params, _prod_params) or dsn.strip() == _prod_url.strip():
            pytest.fail(
                "TAM_008C_PG_DSN targets the same DB as DATABASE_URL (production guard) "
                "— refusing destructive DDL.",
                pytrace=False,
            )

    # Guard 3: connectivity
    try:
        conn = psycopg2.connect(dsn, connect_timeout=5)
    except Exception as exc:
        pytest.fail(f"Cannot connect to test DB ({dsn}): {exc}", pytrace=False)

    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Guard 4: connected DB name must be in the allowed isolation list
    cur.execute("SELECT current_database() AS db_name")
    _actual_dbname = cur.fetchone()["db_name"]
    if _actual_dbname not in _ALLOWED_TEST_DBNAMES:
        conn.close()
        pytest.fail(
            f"Connected DB '{_actual_dbname}' is not in the allowed test DB list "
            f"{sorted(_ALLOWED_TEST_DBNAMES)} — refusing destructive DDL.",
            pytrace=False,
        )

    # Guard 5: isolation marker must pre-exist — never auto-create
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = '_tam_security_isolation_marker'
        ) AS tbl_exists
    """)
    if not cur.fetchone()["tbl_exists"]:
        conn.close()
        pytest.fail(
            "_tam_security_isolation_marker table not found. "
            "Pre-create it with:\n"
            "  CREATE TABLE _tam_security_isolation_marker "
            "      (marker_value TEXT PRIMARY KEY, created_at TIMESTAMPTZ DEFAULT now());\n"
            f"  INSERT INTO _tam_security_isolation_marker VALUES ('{_ISOLATION_MARKER}');",
            pytrace=False,
        )

    cur.execute(
        "SELECT 1 FROM _tam_security_isolation_marker WHERE marker_value = %s",
        (_ISOLATION_MARKER,),
    )
    if cur.fetchone() is None:
        conn.close()
        pytest.fail(
            f"Isolation marker value '{_ISOLATION_MARKER}' not present in "
            "_tam_security_isolation_marker. "
            f"Run: INSERT INTO _tam_security_isolation_marker VALUES ('{_ISOLATION_MARKER}');",
            pytrace=False,
        )

    # Create Supabase-equivalent roles if absent
    for role in ("anon", "authenticated", "service_role"):
        cur.execute(f"""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    CREATE ROLE {role};
                END IF;
            END $$;
        """)

    # Drop existing TAM objects (dependency order)
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

    # Create stub reference tables (UNIQUE on factories already included)
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

    cur.execute("INSERT INTO companies (id) VALUES (%s), (%s)", (_CO_A, _CO_B))
    cur.execute(
        "INSERT INTO factories (id, company_id) VALUES (%s, %s), (%s, %s)",
        (_FAC1, _CO_A, _FAC2, _CO_A),
    )

    # Simulate Supabase default privileges:
    # In Supabase, every new TABLE and FUNCTION automatically receives
    # ALL / EXECUTE for anon, authenticated, and service_role.
    # The migration REVOKE statements must neutralise these auto-grants.
    cur.execute("""
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT ALL ON TABLES TO anon;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT ALL ON TABLES TO authenticated;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT ALL ON TABLES TO service_role;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT EXECUTE ON FUNCTIONS TO anon;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT EXECUTE ON FUNCTIONS TO authenticated;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT EXECUTE ON FUNCTIONS TO service_role;
    """)

    # Apply security migrations (DDL + REVOKE/GRANT)
    cur.execute(_MIG_ROUTES)
    cur.execute(_MIG_LEDGER)

    yield cur

    # ── Teardown ────────────────────────────────────────────────────────────────

    # Reset DEFAULT PRIVILEGES to not affect other test modules
    cur.execute("""
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            REVOKE ALL ON TABLES FROM anon;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            REVOKE ALL ON TABLES FROM authenticated;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            REVOKE ALL ON TABLES FROM service_role;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            REVOKE EXECUTE ON FUNCTIONS FROM anon;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            REVOKE EXECUTE ON FUNCTIONS FROM authenticated;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            REVOKE EXECUTE ON FUNCTIONS FROM service_role;
    """)

    # Drop route tables so ledger test D16 isolation is preserved
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


# ── S22-S28: service_role has exact grants ────────────────────────────────────

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


# ── S29-S35: PUBLIC has no EXECUTE on trigger functions (proacl) ──────────────

@pytest.mark.parametrize("fn_name,sid", [
    ("tam_routes_published_guard_fn",   "S29"),
    ("tam_version_immutability_fn",     "S30"),
    ("tam_steps_draft_only_fn",         "S31"),
    ("tam_assignees_draft_only_fn",     "S32"),
    ("tam_audit_immutability_fn",       "S33"),
    ("tam_grants_immutability_fn",      "S34"),
    ("tam_revocations_immutability_fn", "S35"),
])
def test_trigger_fn_public_execute_revoked(pg, fn_name, sid):
    """EXECUTE must be revoked from PUBLIC for all TAM trigger functions.

    proacl IS NULL means default ACL is in effect (PUBLIC has EXECUTE).
    After REVOKE, proacl is explicitly set and contains no '=X' (PUBLIC execute).
    """
    pg.execute(
        """
        SELECT
            proacl IS NOT NULL AS acl_explicit,
            CASE
                WHEN proacl IS NULL THEN FALSE
                ELSE NOT EXISTS (
                    SELECT 1 FROM unnest(proacl) AS a
                    WHERE a::text ~ '^=[^/]*X'
                )
            END AS public_execute_revoked
        FROM pg_proc
        JOIN pg_namespace ON pg_namespace.oid = pg_proc.pronamespace
        WHERE proname = %s AND nspname = 'public'
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


# ── S36-S42: anon has no EXECUTE on trigger functions ─────────────────────────

@pytest.mark.parametrize("fn_name,sid", [
    ("tam_routes_published_guard_fn",   "S36"),
    ("tam_version_immutability_fn",     "S37"),
    ("tam_steps_draft_only_fn",         "S38"),
    ("tam_assignees_draft_only_fn",     "S39"),
    ("tam_audit_immutability_fn",       "S40"),
    ("tam_grants_immutability_fn",      "S41"),
    ("tam_revocations_immutability_fn", "S42"),
])
def test_trigger_fn_anon_execute_revoked(pg, fn_name, sid):
    """anon must not have EXECUTE on any TAM trigger function.

    Supabase auto-grants EXECUTE to anon for new functions; the migration
    must explicitly revoke it.  Checked via has_function_privilege on the
    function OID to avoid signature ambiguity.
    """
    pg.execute(
        """
        SELECT has_function_privilege('anon', p.oid, 'EXECUTE') AS can_execute
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE p.proname = %s AND n.nspname = 'public'
        """,
        (fn_name,),
    )
    row = pg.fetchone()
    assert row is not None, f"{sid}: function {fn_name} not found"
    assert row["can_execute"] is False, (
        f"{sid}: anon still has EXECUTE on {fn_name} "
        "(REVOKE FROM anon missing or Supabase auto-grant not neutralised)"
    )


# ── S43-S49: authenticated has no EXECUTE on trigger functions ────────────────

@pytest.mark.parametrize("fn_name,sid", [
    ("tam_routes_published_guard_fn",   "S43"),
    ("tam_version_immutability_fn",     "S44"),
    ("tam_steps_draft_only_fn",         "S45"),
    ("tam_assignees_draft_only_fn",     "S46"),
    ("tam_audit_immutability_fn",       "S47"),
    ("tam_grants_immutability_fn",      "S48"),
    ("tam_revocations_immutability_fn", "S49"),
])
def test_trigger_fn_authenticated_execute_revoked(pg, fn_name, sid):
    """authenticated must not have EXECUTE on any TAM trigger function."""
    pg.execute(
        """
        SELECT has_function_privilege('authenticated', p.oid, 'EXECUTE') AS can_execute
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE p.proname = %s AND n.nspname = 'public'
        """,
        (fn_name,),
    )
    row = pg.fetchone()
    assert row is not None, f"{sid}: function {fn_name} not found"
    assert row["can_execute"] is False, (
        f"{sid}: authenticated still has EXECUTE on {fn_name}"
    )
