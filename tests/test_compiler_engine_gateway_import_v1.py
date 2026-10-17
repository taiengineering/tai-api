"""
WO-E2E2000-BE-COMPILER-GATEWAY-IMPORT-PATCH-001
T01–T07: compiler_engine_gateway import + key-resolution contracts.

All tests are fully mocked — no Supabase network calls, no DB writes.
"""
import importlib
import sys
import types
import pytest


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _reload_gateway(monkeypatch, env: dict):
    """Reload compiler_engine_gateway with a patched environment."""
    # Patch os.environ via supabase_client symbols
    import db.supabase_client as dbc
    fake_url = "https://fake.supabase.co"
    monkeypatch.setattr(dbc, "SUPABASE_URL", fake_url)
    # _resolve_service_role_key reads os.environ directly; patch os.environ
    import os
    for key in ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY"):
        monkeypatch.delenv(key, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    # Remove cached module so importlib.reload picks up patched env
    mod_name = "services.compiler_engine_gateway"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    # Also reset the module-level singleton
    import services.compiler_engine_gateway as gw
    monkeypatch.setattr(gw, "_engine_client", None)
    return gw


def _make_fake_client(schema_name):
    """Return a fake Supabase client stub whose .table() chain is inspectable."""
    class _FakeExec:
        def __init__(self):
            self.data = []

        def execute(self):
            return self

    class _FakeTable:
        def select(self, *_): return self
        def not_(self): return self
        def in_(self, *_): return self
        def order(self, *_): return self
        def range(self, *_): return self
        def execute(self): return _FakeExec()

    class _FakeClient:
        bound_schema = schema_name

        def table(self, name):
            return _FakeTable()

    return _FakeClient()


# ---------------------------------------------------------------------------
# T01 — import succeeds without SUPABASE_KEY export
# ---------------------------------------------------------------------------

def test_T01_import_no_supabase_key_export(monkeypatch):
    """Module loads cleanly; SUPABASE_KEY is NOT referenced at import time."""
    import db.supabase_client as dbc
    # Verify SUPABASE_KEY does not exist in supabase_client
    assert not hasattr(dbc, "SUPABASE_KEY"), (
        "SUPABASE_KEY must not be exported from db.supabase_client"
    )
    # Import gateway — must not raise
    if "services.compiler_engine_gateway" in sys.modules:
        del sys.modules["services.compiler_engine_gateway"]
    import services.compiler_engine_gateway  # noqa: F401 — import-only test


# ---------------------------------------------------------------------------
# T02 — key absent → RuntimeError (fail-closed)
# ---------------------------------------------------------------------------

def test_T02_no_key_raises(monkeypatch):
    """_make_engine_client() raises RuntimeError when both key env-vars are absent."""
    import db.supabase_client as dbc
    monkeypatch.setattr(dbc, "SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)

    if "services.compiler_engine_gateway" in sys.modules:
        del sys.modules["services.compiler_engine_gateway"]
    import services.compiler_engine_gateway as gw
    monkeypatch.setattr(gw, "_engine_client", None)

    with pytest.raises(RuntimeError, match="service_role"):
        gw._make_engine_client()


# ---------------------------------------------------------------------------
# T03 — canonical key SUPABASE_SERVICE_ROLE_KEY accepted
# ---------------------------------------------------------------------------

def test_T03_canonical_key_accepted(monkeypatch):
    """SUPABASE_SERVICE_ROLE_KEY is resolved and passed to create_client."""
    import db.supabase_client as dbc
    monkeypatch.setattr(dbc, "SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "svc-role-canonical")
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)

    captured = {}

    def _fake_create(url, key, **kwargs):
        captured["url"] = url
        captured["key"] = key
        return _make_fake_client("engine_isolated")

    if "services.compiler_engine_gateway" in sys.modules:
        del sys.modules["services.compiler_engine_gateway"]
    import services.compiler_engine_gateway as gw
    monkeypatch.setattr(gw, "_engine_client", None)
    monkeypatch.setattr("services.compiler_engine_gateway.create_client", _fake_create)

    gw._make_engine_client()
    assert captured["key"] == "svc-role-canonical"


# ---------------------------------------------------------------------------
# T04 — legacy alias SUPABASE_SERVICE_KEY accepted
# ---------------------------------------------------------------------------

def test_T04_legacy_alias_accepted(monkeypatch):
    """SUPABASE_SERVICE_KEY (legacy alias) is resolved when canonical key absent."""
    import db.supabase_client as dbc
    monkeypatch.setattr(dbc, "SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc-role-legacy")

    captured = {}

    def _fake_create(url, key, **kwargs):
        captured["key"] = key
        return _make_fake_client("engine_isolated")

    if "services.compiler_engine_gateway" in sys.modules:
        del sys.modules["services.compiler_engine_gateway"]
    import services.compiler_engine_gateway as gw
    monkeypatch.setattr(gw, "_engine_client", None)
    monkeypatch.setattr("services.compiler_engine_gateway.create_client", _fake_create)

    gw._make_engine_client()
    assert captured["key"] == "svc-role-legacy"


# ---------------------------------------------------------------------------
# T05 — anon-only environment → rejected (RuntimeError)
# ---------------------------------------------------------------------------

def test_T05_anon_only_rejected(monkeypatch):
    """Setting only SUPABASE_ANON_KEY must NOT satisfy the service-role check."""
    import db.supabase_client as dbc
    monkeypatch.setattr(dbc, "SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key-value")

    if "services.compiler_engine_gateway" in sys.modules:
        del sys.modules["services.compiler_engine_gateway"]
    import services.compiler_engine_gateway as gw
    monkeypatch.setattr(gw, "_engine_client", None)

    with pytest.raises(RuntimeError, match="service_role"):
        gw._make_engine_client()


# ---------------------------------------------------------------------------
# T06 — engine_isolated schema binding preserved
# ---------------------------------------------------------------------------

def test_T06_engine_isolated_schema_binding(monkeypatch):
    """create_client is called with options targeting engine_isolated schema."""
    import db.supabase_client as dbc
    monkeypatch.setattr(dbc, "SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "svc-role-test")
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)

    schema_received = {}

    class _FakeClientOptions:
        def __init__(self, schema=None, **_):
            schema_received["schema"] = schema

    def _fake_create(url, key, options=None, **kwargs):
        return _make_fake_client("engine_isolated")

    if "services.compiler_engine_gateway" in sys.modules:
        del sys.modules["services.compiler_engine_gateway"]
    import services.compiler_engine_gateway as gw
    monkeypatch.setattr(gw, "_engine_client", None)
    monkeypatch.setattr("services.compiler_engine_gateway.create_client", _fake_create)

    # Patch ClientOptions inside the function's import path
    fake_opts_module = types.ModuleType("supabase.lib.client_options")
    fake_opts_module.ClientOptions = _FakeClientOptions
    monkeypatch.setitem(sys.modules, "supabase.lib.client_options", fake_opts_module)

    gw._make_engine_client()
    assert schema_received.get("schema") == "engine_isolated"


# ---------------------------------------------------------------------------
# T07 — module import triggers zero DB/network calls
# ---------------------------------------------------------------------------

def test_T07_import_no_network_call(monkeypatch):
    """Importing the module must not call create_client (lazy singleton)."""
    call_count = {"n": 0}

    def _spy_create(*_args, **_kwargs):
        call_count["n"] += 1
        return _make_fake_client("engine_isolated")

    if "services.compiler_engine_gateway" in sys.modules:
        del sys.modules["services.compiler_engine_gateway"]

    # Patch create_client before import
    import supabase as _supabase_pkg
    original_create = getattr(_supabase_pkg, "create_client", None)
    monkeypatch.setattr(_supabase_pkg, "create_client", _spy_create)

    import services.compiler_engine_gateway  # noqa: F401

    assert call_count["n"] == 0, (
        f"create_client was called {call_count['n']} times during module import"
    )
