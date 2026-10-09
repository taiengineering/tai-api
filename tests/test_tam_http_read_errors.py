"""TAI-WO-TAM-HTTP-READ-C2-001 — GET API Error Security Hardening tests.

Verifies that:
  - Invalid UUID → 422 INVALID_ROUTE_ID (no DB error text leaked)
  - DB connection failure → 503 SERVICE_UNAVAILABLE (static message)
  - SQL execution error → 503 SERVICE_UNAVAILABLE (static message)
  - DB not configured → 500 DB_NOT_CONFIGURED (existing static contract unchanged)
  - Cross-company, factory scope → existing contracts unchanged
  - Unauthenticated → 401
  - Inactive user → 403
  - All POST write endpoints → 403 ROUTE_MANAGER_PERMISSION_REQUIRED
  - write_enabled=False in route_authz_adapter
  - TAM router absent from main.app

All tests use an isolated FastAPI instance — TAM router is never registered in main.app.
No live DB required (DB scenarios use mocking or _DATABASE_URL None).
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import psycopg2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.auth import get_current_user
from routers.tam_routes import router as tam_router

# ── Stable test IDs ──────────────────────────────────────────────────────────

CO_A = "aaaaaaaa-0001-0001-0001-000000000001"
CO_B = "bbbbbbbb-0002-0002-0002-000000000002"
FAC1 = "ffffffff-0001-0001-0001-000000000001"
FAC2 = "ffffffff-0002-0002-0002-000000000002"
U1   = "11111111-1111-1111-1111-111111111111"

ACTIVE_USER = {
    "id": U1, "company_id": CO_A, "factory_id": None,
    "status_code": "ACTIVE", "is_active": True, "role_code": "001",
}
FAC_USER = {
    "id": U1, "company_id": CO_A, "factory_id": FAC1,
    "status_code": "ACTIVE", "is_active": True, "role_code": "001",
}


def _isolated_client(mock_user=None) -> TestClient:
    app = FastAPI()
    app.include_router(tam_router)
    if mock_user is not None:
        app.dependency_overrides[get_current_user] = lambda: mock_user
    return TestClient(app, raise_server_exceptions=False)


def _no_dsn(svc_module):
    """Context manager: temporarily clears _DATABASE_URL to simulate missing config."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        orig = svc_module._DATABASE_URL
        svc_module._DATABASE_URL = None
        try:
            yield
        finally:
            svc_module._DATABASE_URL = orig
    return _ctx()


# ── E01: Invalid UUID → 422 INVALID_ROUTE_ID ─────────────────────────────────

class TestInvalidRouteId:
    """Invalid route_id UUID must return 422 without exposing DB error text."""

    def test_e01_non_uuid_string(self):
        client = _isolated_client(ACTIVE_USER)
        r = client.get("/v1/tam/routes/not-a-valid-uuid")
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert detail["code"] == "INVALID_ROUTE_ID"
        assert "postgresql" not in detail["message"].lower()
        assert "invalid input syntax" not in detail["message"].lower()

    def test_e02_empty_string_route_id(self):
        client = _isolated_client(ACTIVE_USER)
        r = client.get("/v1/tam/routes/ ")
        # FastAPI path normalisation: whitespace-only path segment
        # either 422 INVALID_ROUTE_ID or 404 (router doesn't match)
        assert r.status_code in (404, 422)

    def test_e03_sql_injection_attempt_route_id(self):
        """SQL injection string in route_id must be rejected before DB call."""
        client = _isolated_client(ACTIVE_USER)
        r = client.get("/v1/tam/routes/'; DROP TABLE tam_approval_routes; --")
        assert r.status_code in (404, 422)  # router may 404 on path special chars

    def test_e04_uuid_format_is_validated_before_db_call(self):
        """UUID validation fires before any DB connection attempt."""
        from services.tam import routes_svc
        with _no_dsn(routes_svc):
            # If UUID validation fires first, we get 422 NOT 500 DB_NOT_CONFIGURED
            client = _isolated_client(ACTIVE_USER)
            r = client.get("/v1/tam/routes/bad-uuid-no-db")
            assert r.status_code == 422
            assert r.json()["detail"]["code"] == "INVALID_ROUTE_ID"


# ── E05: DB connection failure → 503 SERVICE_UNAVAILABLE ─────────────────────

_FAKE_DSN = "postgresql://fakeuser:fakepass@localhost:9999/fakedb"


def _with_connect_raise(exc_class):
    """Set a fake DSN (so _connect() reaches psycopg2.connect) and raise exc_class."""
    import contextlib
    from services.tam import routes_svc

    @contextlib.contextmanager
    def _ctx():
        orig = routes_svc._DATABASE_URL
        routes_svc._DATABASE_URL = _FAKE_DSN
        with patch("psycopg2.connect", side_effect=exc_class("connection refused")):
            try:
                yield
            finally:
                routes_svc._DATABASE_URL = orig
    return _ctx()


def _with_sql_error(exc_class):
    """Set fake DSN; mock connect returns a conn whose cursor.execute raises exc_class."""
    import contextlib
    from services.tam import routes_svc

    @contextlib.contextmanager
    def _ctx():
        orig = routes_svc._DATABASE_URL
        routes_svc._DATABASE_URL = _FAKE_DSN

        mock_cur = MagicMock()
        mock_cur.execute.side_effect = exc_class("relation does not exist")
        mock_cur.fetchone.side_effect = exc_class("relation does not exist")
        mock_cur.fetchall.side_effect = exc_class("relation does not exist")
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch("psycopg2.connect", return_value=mock_conn):
            try:
                yield
            finally:
                routes_svc._DATABASE_URL = orig
    return _ctx()


class TestDbConnectionFailure:
    """DB connection failure must return 503 with a static message — no DSN/error text."""

    def test_e05_list_routes_operational_error(self):
        with _with_connect_raise(psycopg2.OperationalError):
            client = _isolated_client(ACTIVE_USER)
            r = client.get("/v1/tam/routes", params={"company_id": CO_A})
        assert r.status_code == 503
        detail = r.json()["detail"]
        assert detail["code"] == "SERVICE_UNAVAILABLE"
        _assert_no_leak(detail["message"])

    def test_e06_get_route_operational_error(self):
        valid_id = str(uuid.uuid4())
        with _with_connect_raise(psycopg2.OperationalError):
            client = _isolated_client(ACTIVE_USER)
            r = client.get(f"/v1/tam/routes/{valid_id}")
        assert r.status_code == 503
        detail = r.json()["detail"]
        assert detail["code"] == "SERVICE_UNAVAILABLE"
        _assert_no_leak(detail["message"])

    def test_e07_list_routes_interface_error(self):
        with _with_connect_raise(psycopg2.InterfaceError):
            client = _isolated_client(ACTIVE_USER)
            r = client.get("/v1/tam/routes", params={"company_id": CO_A})
        assert r.status_code == 503
        assert r.json()["detail"]["code"] == "SERVICE_UNAVAILABLE"


# ── E08: SQL execution error → 503 SERVICE_UNAVAILABLE ───────────────────────

class TestSqlExecutionError:
    """SQL errors during execute() must return 503 with a static message."""

    def test_e08_list_routes_programming_error(self):
        with _with_sql_error(psycopg2.ProgrammingError):
            client = _isolated_client(ACTIVE_USER)
            r = client.get("/v1/tam/routes", params={"company_id": CO_A})
        assert r.status_code == 503
        detail = r.json()["detail"]
        assert detail["code"] == "SERVICE_UNAVAILABLE"
        _assert_no_leak(detail["message"])

    def test_e09_get_route_programming_error(self):
        valid_id = str(uuid.uuid4())
        with _with_sql_error(psycopg2.ProgrammingError):
            client = _isolated_client(ACTIVE_USER)
            r = client.get(f"/v1/tam/routes/{valid_id}")
        assert r.status_code == 503
        detail = r.json()["detail"]
        assert detail["code"] == "SERVICE_UNAVAILABLE"
        _assert_no_leak(detail["message"])

    def test_e10_list_routes_data_error(self):
        with _with_sql_error(psycopg2.errors.NumericValueOutOfRange):
            client = _isolated_client(ACTIVE_USER)
            r = client.get("/v1/tam/routes", params={"company_id": CO_A})
        assert r.status_code == 503
        assert r.json()["detail"]["code"] == "SERVICE_UNAVAILABLE"


# ── E11: DB not configured → 500 DB_NOT_CONFIGURED (unchanged) ───────────────

class TestDbNotConfigured:
    """DB_NOT_CONFIGURED contract must remain unchanged from baseline."""

    def test_e11_list_routes_no_dsn(self):
        from services.tam import routes_svc
        with _no_dsn(routes_svc):
            client = _isolated_client(ACTIVE_USER)
            r = client.get("/v1/tam/routes", params={"company_id": CO_A})
        assert r.status_code == 500
        detail = r.json()["detail"]
        assert detail["code"] == "DB_NOT_CONFIGURED"
        assert "DATABASE_URL" in detail["message"]
        assert len(detail["message"]) < 100  # static message, no variable content

    def test_e12_get_route_no_dsn_valid_uuid(self):
        from services.tam import routes_svc
        valid_id = str(uuid.uuid4())
        with _no_dsn(routes_svc):
            client = _isolated_client(ACTIVE_USER)
            r = client.get(f"/v1/tam/routes/{valid_id}")
        assert r.status_code == 500
        assert r.json()["detail"]["code"] == "DB_NOT_CONFIGURED"


# ── A/B: Auth and tenant (regression) ────────────────────────────────────────

class TestAuthTenantRegression:
    """Auth and tenant isolation contracts must be unchanged after C2 patch."""

    def test_a01_no_auth_list(self):
        app = FastAPI(); app.include_router(tam_router)
        r = TestClient(app, raise_server_exceptions=False).get(
            "/v1/tam/routes", params={"company_id": CO_A}
        )
        assert r.status_code == 401

    def test_a02_no_auth_get(self):
        app = FastAPI(); app.include_router(tam_router)
        r = TestClient(app, raise_server_exceptions=False).get(
            f"/v1/tam/routes/{U1}"
        )
        assert r.status_code == 401

    def test_b01_cross_company_list(self):
        r = _isolated_client(ACTIVE_USER).get(
            "/v1/tam/routes", params={"company_id": CO_B}
        )
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "CROSS_COMPANY_FORBIDDEN"

    def test_b03_factory_scope_mismatch(self):
        r = _isolated_client(FAC_USER).get(
            "/v1/tam/routes", params={"company_id": CO_A, "factory_id": FAC2}
        )
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "FACTORY_SCOPE_NOT_FINALIZED"

    def test_b04_no_factory_user_with_factory_filter(self):
        r = _isolated_client(ACTIVE_USER).get(
            "/v1/tam/routes", params={"company_id": CO_A, "factory_id": FAC1}
        )
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "FACTORY_SCOPE_NOT_FINALIZED"


# ── P: POST write gate (regression) ──────────────────────────────────────────

class TestWriteGateRegression:
    """All POST endpoints must remain unconditionally 403."""

    _ENDPOINTS = [
        ("POST", "/v1/tam/routes",
         {"company_id": CO_A, "route_scope": "COMPANY_DEFAULT", "display_name": "R"}),
        ("POST", f"/v1/tam/routes/{U1}/versions", {"notes": None}),
        ("POST", f"/v1/tam/routes/{U1}/versions/{U1}/steps",
         {"step_order": 1, "step_name": "S", "step_type": "SEQUENTIAL"}),
        ("POST", f"/v1/tam/routes/{U1}/versions/{U1}/steps/{U1}/assignees",
         {"user_id": U1}),
        ("POST", f"/v1/tam/routes/{U1}/versions/{U1}/publish", {}),
    ]

    def test_p01_all_post_endpoints_return_403(self):
        client = _isolated_client(ACTIVE_USER)
        for method, url, body in self._ENDPOINTS:
            r = client.request(method, url, json=body)
            assert r.status_code == 403, (
                f"{method} {url} expected 403, got {r.status_code}: {r.text}"
            )
            assert r.json()["detail"]["code"] == "ROUTE_MANAGER_PERMISSION_REQUIRED"

    def test_p02_write_enabled_always_false(self):
        from services.tam.route_authz_adapter import assess_tam_route_authorization_candidate
        import os
        dsn = os.getenv("TAM_TEST_PG_DSN") or os.getenv("DATABASE_URL", "")
        if not dsn:
            pytest.skip("no DSN available for adapter test")
        # adapter never sets write_enabled=True regardless of auth result
        result = assess_tam_route_authorization_candidate(
            ACTIVE_USER, route_id=str(uuid.uuid4()), dsn=dsn
        )
        assert result["write_enabled"] is False


# ── M: main.py registration check ────────────────────────────────────────────

class TestMainAppRegistration:
    """TAM router must not be registered in main.app (PREMERGE-003)."""

    def test_m01_tam_not_in_main_app(self):
        import main as _main
        routes = getattr(getattr(_main.app, "router", _main.app), "routes", [])
        all_paths = []
        for r in routes:
            sub = getattr(r, "routes", None)
            if sub:
                for s in sub:
                    p = getattr(s, "path", None)
                    if p:
                        all_paths.append(p)
            else:
                p = getattr(r, "path", None)
                if p:
                    all_paths.append(p)
        tam_paths = [p for p in all_paths if "/tam" in p]
        assert tam_paths == [], f"TAM paths found in main.app: {tam_paths}"


# ── Leak guard helper ─────────────────────────────────────────────────────────

def _assert_no_leak(message: str) -> None:
    """Verify service-unavailable message contains no DB/SQL internals."""
    leak_patterns = [
        "connection refused", "password", "FATAL", "ERROR:", "syntax",
        "relation", "column", "constraint", "postgresql", "psycopg",
        "localhost", "5432", "fakeuser", "fakepass", "DATABASE_URL",
    ]
    lower = message.lower()
    leaks = [p for p in leak_patterns if p.lower() in lower]
    assert not leaks, f"potential info leak in message {message!r}: patterns {leaks}"
