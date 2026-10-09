"""tests/test_saas_diagnosis_snapshot_router.py

WO-DIAGNOSIS-RESULT-SNAPSHOT-INVENTORY-SEPARATION-PATCH1+PATCH2.

Router-level tests for GET /legal-engine/diagnose/snapshot/{diagnosis_id}.

R01 valid auth + own company → 200
R02 wrong company → 404
R03 snapshot missing → 404
R04 malformed snapshot (obligations_raw absent) → 500
R05 response public_token absent
R06 response input_data absent
R07 get_current_user called with 1 arg (signature regression guard)
R08 COMPANY-role user with matching company_id → 200
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.legal_engine as _le_mod
from routers.auth import get_current_user


# ── Minimal fake Supabase ─────────────────────────────────────────────────────

class _Resp:
    def __init__(self, data):
        self.data = data


class _Q:
    def __init__(self, sb, name):
        self._sb = sb
        self._name = name
        self._filters = []
        self._limit_n = None

    def select(self, *a, **k):
        return self

    def insert(self, row):
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def limit(self, n):
        self._limit_n = n
        return self

    def execute(self):
        rows = list(self._sb.tables.get(self._name, []))
        for col, val in self._filters:
            rows = [r for r in rows if r.get(col) == val]
        if self._limit_n is not None:
            rows = rows[:self._limit_n]
        return _Resp(rows)


class FakeSB:
    def __init__(self, tables):
        self.tables = {k: list(v) for k, v in tables.items()}

    def table(self, name):
        return _Q(self, name)


# ── Common fixtures ───────────────────────────────────────────────────────────

_VALID_FULL_RESULT = {
    "obligations_raw": [{"id": "O1", "law_name": "산업안전보건법", "law_article": "제38조"}],
    "applicable_count": 1,
    "sector": "MANUFACTURING",
    "engine_version": "5.8.0",
}

_OWN_COMPANY_ID = "co-owner"
_OTHER_COMPANY_ID = "co-other"
_FACTORY_ID = "fac-1"
_DIAG_ID = "diag-uuid-1"

_VALID_ROW = {
    "id": _DIAG_ID,
    "input_data": {"company_id": _OWN_COMPANY_ID, "factory_id": _FACTORY_ID, "sector": "MANUFACTURING"},
    "full_result": _VALID_FULL_RESULT,
    "engine_version": "5.8.0",
    "created_at": "2026-09-29T10:00:00+09:00",
    "source_type": "saas",
    "public_token": "should-not-leak",
}

_MALFORMED_ROW = {
    "id": "diag-bad-1",
    "input_data": {"company_id": _OWN_COMPANY_ID, "factory_id": _FACTORY_ID},
    "full_result": {"sector": "MANUFACTURING"},  # obligations_raw absent
    "engine_version": None,
    "created_at": None,
    "source_type": "saas",
}

# owner = ALL-tier → _ensure_own_company bypasses company check
_USER_OWN = {"id": "u-1", "company_id": _OWN_COMPANY_ID, "role_code": "001"}
_USER_OTHER = {"id": "u-2", "company_id": _OTHER_COMPANY_ID, "role_code": "010"}
# COMPANY-role user whose company_id matches the stored snapshot company_id
_USER_COMPANY = {"id": "u-3", "company_id": _OWN_COMPANY_ID, "role_code": "010"}

_SEED_VALID = {
    "anonymous_diagnosis_results": [_VALID_ROW],
    "role_data_scope": [
        {"role_code": "001", "scope_type": "ALL"},
        {"role_code": "010", "scope_type": "COMPANY"},
    ],
}

_SEED_MALFORMED = {
    "anonymous_diagnosis_results": [_MALFORMED_ROW],
    "role_data_scope": [{"role_code": "001", "scope_type": "ALL"}],
}


def _make_client(fake, monkeypatch, user):
    monkeypatch.setattr(_le_mod, "get_supabase", lambda: fake)
    # snapshot endpoint calls get_current_user(authorization) directly (not as Depends),
    # so monkeypatch the module-level reference to bypass JWT validation in tests.
    monkeypatch.setattr(_le_mod, "get_current_user", lambda _auth: user)
    app = FastAPI()
    app.include_router(_le_mod.router)
    return TestClient(app, raise_server_exceptions=False)


# ── R01 — valid auth + own company → 200 ─────────────────────────────────────

def test_r01_valid_own_company(monkeypatch):
    fake = FakeSB(_SEED_VALID)
    client = _make_client(fake, monkeypatch, _USER_OWN)
    resp = client.get(f"/legal-engine/diagnose/snapshot/{_DIAG_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["diagnosis_id"] == _DIAG_ID
    assert body["data"]["factory_id"] == _FACTORY_ID


# ── R02 — wrong company → 404 ─────────────────────────────────────────────────

def test_r02_wrong_company(monkeypatch):
    fake = FakeSB(_SEED_VALID)
    client = _make_client(fake, monkeypatch, _USER_OTHER)
    resp = client.get(f"/legal-engine/diagnose/snapshot/{_DIAG_ID}")
    assert resp.status_code == 404


# ── R03 — snapshot missing → 404 ─────────────────────────────────────────────

def test_r03_missing_snapshot(monkeypatch):
    fake = FakeSB({"anonymous_diagnosis_results": [], "role_data_scope": []})
    client = _make_client(fake, monkeypatch, _USER_OWN)
    resp = client.get("/legal-engine/diagnose/snapshot/no-such-id")
    assert resp.status_code == 404


# ── R04 — malformed snapshot (obligations_raw absent) → 500 ──────────────────

def test_r04_malformed_snapshot(monkeypatch):
    fake = FakeSB(_SEED_MALFORMED)
    client = _make_client(fake, monkeypatch, _USER_OWN)
    resp = client.get("/legal-engine/diagnose/snapshot/diag-bad-1")
    assert resp.status_code == 500


# ── R05 — response must not contain public_token ─────────────────────────────

def test_r05_public_token_not_exposed(monkeypatch):
    fake = FakeSB(_SEED_VALID)
    client = _make_client(fake, monkeypatch, _USER_OWN)
    resp = client.get(f"/legal-engine/diagnose/snapshot/{_DIAG_ID}")
    assert resp.status_code == 200
    body_str = resp.text
    assert "public_token" not in body_str
    assert "should-not-leak" not in body_str


# ── R06 — response must not contain input_data or company_id ─────────────────

def test_r06_input_data_not_exposed(monkeypatch):
    fake = FakeSB(_SEED_VALID)
    client = _make_client(fake, monkeypatch, _USER_OWN)
    resp = client.get(f"/legal-engine/diagnose/snapshot/{_DIAG_ID}")
    assert resp.status_code == 200
    body = resp.json()
    data = body["data"]
    assert "input_data" not in data
    assert "company_id" not in data
    assert "_stored_company_id" not in data


# ── R07 — get_current_user called with 1 arg (signature regression) ───────────

def test_r07_get_current_user_signature():
    """Calling get_current_user with 2 positional args must raise TypeError.
    This ensures the route does NOT pass supabase as second argument.
    """
    with pytest.raises(TypeError):
        get_current_user("Bearer fake-token", object())  # type: ignore[call-arg]


# ── R08 — COMPANY-role user with matching company_id → 200 ───────────────────

def test_r08_company_role_matching_company(monkeypatch):
    """A non-ALL role user whose company_id matches the snapshot's stored company_id
    must receive 200 with the full snapshot payload — not a 404 ownership rejection.
    """
    fake = FakeSB(_SEED_VALID)
    client = _make_client(fake, monkeypatch, _USER_COMPANY)
    resp = client.get(f"/legal-engine/diagnose/snapshot/{_DIAG_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["diagnosis_id"] == _DIAG_ID


# ── R09 — all unconfirmed fields stripped from customer-facing response ───────

def test_r09_unconfirmed_fields_not_in_response(monkeypatch):
    """All four internal unconfirmed fields must be absent from the HTTP response.
    Internal DB storage is unchanged; only the HTTP response is filtered.
    review_required / review_required_count / unconfirmed / unconfirmed_count
    """
    row_with_rr = dict(_VALID_ROW)
    row_with_rr["full_result"] = {
        **_VALID_FULL_RESULT,
        "review_required": [{"atom_id": "A1", "reason": "UNKNOWN"}],
        "review_required_count": 1,
        "unconfirmed": [{"atom_id": "A1"}],
        "unconfirmed_count": 1,
    }
    seed = {
        "anonymous_diagnosis_results": [row_with_rr],
        "role_data_scope": [{"role_code": "001", "scope_type": "ALL"}],
    }
    fake = FakeSB(seed)
    client = _make_client(fake, monkeypatch, _USER_OWN)
    resp = client.get(f"/legal-engine/diagnose/snapshot/{_DIAG_ID}")
    assert resp.status_code == 200
    body = resp.json()
    full = body["data"]["full_result"]
    for key in ("review_required", "review_required_count", "unconfirmed", "unconfirmed_count"):
        assert key not in full, f"{key!r} must be stripped from customer response"
    # Confirmed obligations still present
    assert "obligations_raw" in full
