"""Router-level contract tests for WO-EQUIPMENT-CODE-CANONICAL-ADAPTER-PATCH-001.

These tests call create_asset() and update_asset() through FastAPI TestClient
with a minimal fake Supabase so the actual DB insert/update payload can be
inspected. This proves the normalization wire reaches the DB write boundary.

Covers:
  POST_ALIAS_NUMERIC  — PRESS/CONVEYOR/CRANE/PRESSURE_VESSEL stored as 023/024/021/038
  POST_INVALID_422    — lowercase / unknown / out-of-range → 422 before any DB write
  PATCH_ALIAS_NUMERIC — alias in PATCH stored as numeric
  PATCH_INVALID_422   — invalid code → 422, DB update = 0
  MISSING_COMPAT      — absent/None code succeeds; equipment_type_code absent from payload
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.equipment_assets as _ea_mod
from routers.auth import get_current_user


# ── Minimal fake Supabase ─────────────────────────────────────────────────────

class _Resp:
    def __init__(self, data):
        self.data = data
        self.count = len(data)


class _Q:
    def __init__(self, sb, name):
        self._sb = sb
        self._name = name
        self._op = "select"
        self._payload = None
        self._filters = []
        self._limit_n = None

    def select(self, *a, **k):
        self._op = "select"
        return self

    def insert(self, row):
        self._op = "insert"
        self._payload = dict(row)
        return self

    def update(self, row):
        self._op = "update"
        self._payload = dict(row)
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def in_(self, col, vals):
        return self

    def order(self, *a, **k):
        return self

    def range(self, *a):
        return self

    def limit(self, n):
        self._limit_n = n
        return self

    def execute(self):
        if self._op == "insert":
            row = {**self._payload, "id": self._payload.get("id", "new-id")}
            self._sb.inserts.append({"table": self._name, "row": dict(row)})
            return _Resp([row])
        if self._op == "update":
            row = dict(self._payload)
            self._sb.updates.append({
                "table": self._name,
                "row": dict(row),
                "filters": list(self._filters),
            })
            row["id"] = next((v for c, v in self._filters if c == "id"), "asset-1")
            return _Resp([row])
        # select — return matching rows from seed tables
        rows = list(self._sb.tables.get(self._name, []))
        for col, val in self._filters:
            rows = [r for r in rows if r.get(col) == val]
        if self._limit_n is not None:
            rows = rows[:self._limit_n]
        return _Resp(rows)


class FakeSB:
    def __init__(self, tables):
        self.tables = {k: [dict(r) for r in v] for k, v in tables.items()}
        self.inserts: list = []
        self.updates: list = []

    def table(self, name):
        return _Q(self, name)


# ── Test helpers ──────────────────────────────────────────────────────────────

_ADMIN = {"id": "u-1", "role_code": "001", "company_id": "co-1"}

_SEED = {
    # role_data_scope: role_code 001 → ALL (admin bypass in _ensure_factory_own / _ensure_asset_own)
    "role_data_scope": [{"role_code": "001", "scope_type": "ALL"}],
    "factories":        [{"id": "factory-1", "company_id": "co-1"}],
    "equipment_assets": [{"id": "asset-1",   "factory_id": "factory-1"}],
}


def _make_client(fake, monkeypatch):
    monkeypatch.setattr(_ea_mod, "get_supabase", lambda: fake)
    app = FastAPI()
    app.include_router(_ea_mod.router)
    app.dependency_overrides[get_current_user] = lambda: _ADMIN
    return TestClient(app, raise_server_exceptions=False)


# ── POST alias → numeric DB payload ──────────────────────────────────────────

@pytest.mark.parametrize("alias,expected_code", [
    ("PRESS",            "023"),
    ("CONVEYOR",         "024"),
    ("CRANE",            "021"),
    ("PRESSURE_VESSEL",  "038"),
])
def test_post_alias_persisted_as_numeric(alias, expected_code, monkeypatch):
    fake = FakeSB(_SEED)
    client = _make_client(fake, monkeypatch)
    r = client.post("/equipment-assets", json={
        "factory_id": "factory-1",
        "asset_name": "테스트설비",
        "equipment_type_code": alias,
    })
    assert r.status_code == 200, r.text
    assert len(fake.inserts) == 1
    persisted = fake.inserts[0]["row"].get("equipment_type_code")
    assert persisted == expected_code, (
        f"alias={alias!r}: expected DB code {expected_code!r}, got {persisted!r}"
    )


def test_post_raw_press_not_persisted(monkeypatch):
    fake = FakeSB(_SEED)
    client = _make_client(fake, monkeypatch)
    r = client.post("/equipment-assets", json={
        "factory_id": "factory-1",
        "asset_name": "프레스",
        "equipment_type_code": "PRESS",
    })
    assert r.status_code == 200, r.text
    persisted = fake.inserts[0]["row"].get("equipment_type_code")
    assert persisted == "023"
    assert "PRESS" not in str(persisted)


# ── POST invalid → HTTP 422, DB insert = 0 ────────────────────────────────────

@pytest.mark.parametrize("bad_code", ["press", "UNKNOWN", "999"])
def test_post_invalid_code_returns_422(bad_code, monkeypatch):
    fake = FakeSB(_SEED)
    client = _make_client(fake, monkeypatch)
    r = client.post("/equipment-assets", json={
        "factory_id": "factory-1",
        "asset_name": "테스트",
        "equipment_type_code": bad_code,
    })
    assert r.status_code == 422, f"expected 422 for {bad_code!r}, got {r.status_code}"
    assert len(fake.inserts) == 0, (
        f"DB insert must not occur before validation passes; got {fake.inserts}"
    )


# ── PATCH alias → numeric DB payload ─────────────────────────────────────────

def test_patch_alias_persisted_as_numeric(monkeypatch):
    fake = FakeSB(_SEED)
    client = _make_client(fake, monkeypatch)
    r = client.patch("/equipment-assets/asset-1", json={
        "equipment_type_code": "PRESSURE_VESSEL",
    })
    assert r.status_code == 200, r.text
    assert len(fake.updates) == 1
    persisted = fake.updates[0]["row"].get("equipment_type_code")
    assert persisted == "038", f"expected '038', got {persisted!r}"


@pytest.mark.parametrize("alias,expected_code", [
    ("PRESS", "023"),
    ("CRANE", "021"),
])
def test_patch_alias_variants(alias, expected_code, monkeypatch):
    fake = FakeSB(_SEED)
    client = _make_client(fake, monkeypatch)
    r = client.patch("/equipment-assets/asset-1", json={
        "equipment_type_code": alias,
    })
    assert r.status_code == 200, r.text
    persisted = fake.updates[0]["row"].get("equipment_type_code")
    assert persisted == expected_code


# ── PATCH invalid → HTTP 422, DB update = 0 ──────────────────────────────────

@pytest.mark.parametrize("bad_code", ["press", "UNKNOWN"])
def test_patch_invalid_code_returns_422(bad_code, monkeypatch):
    fake = FakeSB(_SEED)
    client = _make_client(fake, monkeypatch)
    r = client.patch("/equipment-assets/asset-1", json={
        "equipment_type_code": bad_code,
    })
    assert r.status_code == 422, f"expected 422 for {bad_code!r}, got {r.status_code}"
    assert len(fake.updates) == 0


# ── POST missing/None code → backward compat ─────────────────────────────────

def test_post_no_code_succeeds_and_key_absent(monkeypatch):
    fake = FakeSB(_SEED)
    client = _make_client(fake, monkeypatch)
    r = client.post("/equipment-assets", json={
        "factory_id": "factory-1",
        "asset_name": "코드없는설비",
    })
    assert r.status_code == 200, r.text
    assert len(fake.inserts) == 1
    inserted = fake.inserts[0]["row"]
    assert "equipment_type_code" not in inserted, (
        f"equipment_type_code must be absent when None; got {inserted.get('equipment_type_code')!r}"
    )


def test_post_explicit_none_code_key_absent(monkeypatch):
    fake = FakeSB(_SEED)
    client = _make_client(fake, monkeypatch)
    r = client.post("/equipment-assets", json={
        "factory_id": "factory-1",
        "asset_name": "명시적None",
        "equipment_type_code": None,
    })
    assert r.status_code == 200, r.text
    inserted = fake.inserts[0]["row"]
    assert "equipment_type_code" not in inserted
