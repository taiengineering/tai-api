"""§91 AUTH_SESSION_ISSUED — first production Common Event v1 adopter (A1–A18)."""

import ast
import pathlib

import pytest

import routers.auth as auth_mod
from routers.auth import login, LoginRequest

AUTH_SRC = pathlib.Path(auth_mod.__file__).read_text(encoding="utf-8")


class _Q:
    def __init__(self, rows): self._rows = rows
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def neq(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def update(self, *a, **k): return self
    def insert(self, *a, **k): return self
    def execute(self): return type("R", (), {"data": self._rows})()


class _Auth:
    def sign_in_with_password(self, *a, **k):
        session = type("Se", (), {"access_token": "at", "refresh_token": "rt",
                                  "expires_in": 3600})()
        return type("S", (), {"user": object(), "session": session})()


class _SB:
    def __init__(self): self.auth = _Auth()
    def table(self, name):
        if name == "users":
            return _Q([{
                "id": "u-123", "email": "a@b.com", "name": "N", "role_code": "002",
                "company_id": None, "factory_id": None, "status_code": "ACTIVE",
                "profile_image_url": None, "password_hash": None, "auth_id": "auth-1",
                "phone": "010",
            }])
        return _Q([])


def _login(monkeypatch, emit_return=True):
    calls = []
    monkeypatch.setattr(auth_mod, "emit_event",
                        lambda **kw: calls.append(kw) or emit_return)
    monkeypatch.setattr(auth_mod, "get_supabase", lambda: _SB())
    monkeypatch.setattr(auth_mod, "clear_trace", lambda: None)
    resp = login(LoginRequest(email="a@b.com", password="pw"))
    si = next((c for c in calls if c.get("step_key") == "session_issued"), None)
    return calls, si, resp


def test_a1_to_a10_session_issued_canonical(monkeypatch):
    _, si, _ = _login(monkeypatch)
    assert si is not None                                 # A1
    assert si["event_name"] == "AUTH_SESSION_ISSUED"      # A2
    assert si["actor_kind"] == "USER"                     # A3
    assert si["actor_ref"] == "user:u-123"                # A4, A16
    assert si["step_key"] == "session_issued"             # A5
    assert si["event_type"] == "read"                     # A6
    assert si["result"] == "success"                      # A7
    assert "trace" not in si and "trace_id" not in si     # A8
    assert "tenant_id" not in si and "service_key" not in si and "environment" not in si  # A8
    assert "occurred_at" not in si                        # A9
    assert "outcome" not in si                            # A10
    assert "event_version" not in si


def test_a11_emit_false_keeps_login_success(monkeypatch):
    _, _, resp = _login(monkeypatch, emit_return=False)
    assert resp["status"] == "success"                    # A11
    assert "data" in resp and "access_token" in resp["data"]  # A17


def _login_emit_calls(source):
    tree = ast.parse(source)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "login")
    return [n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "emit_event"]


def test_a12_to_a15_only_session_issued_is_canonical():
    emit_calls = _login_emit_calls(AUTH_SRC)
    canonical = [n for n in emit_calls
                 if {"event_name", "actor_kind", "actor_ref"} <= {k.arg for k in n.keywords}]
    assert len(canonical) == 1
    step = next((k.value for k in canonical[0].keywords if k.arg == "step_key"), None)
    assert isinstance(step, ast.Constant) and step.value == "session_issued"
