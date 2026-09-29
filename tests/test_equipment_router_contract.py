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
        self._sort_col = None
        self._sort_desc = False

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

    def order(self, col, *a, desc=False, **k):
        self._sort_col = col
        self._sort_desc = desc
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
        if self._sort_col:
            rows = sorted(rows, key=lambda r: r.get(self._sort_col, ""), reverse=self._sort_desc)
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


# ── T1-T4: GET /type-codes catalog endpoint ───────────────────────────────────

# Catalog fixture: projector-mapped (010,023,038) + non-mapped (001,021,040) + inactive excluded.
_CATALOG_ROWS = [
    {"type_code": "001", "type_name_ko": "리프트", "is_active": True},
    {"type_code": "010", "type_name_ko": "비상발전기", "is_active": True},
    {"type_code": "021", "type_name_ko": "크레인", "is_active": True},
    {"type_code": "023", "type_name_ko": "프레스", "is_active": True},
    {"type_code": "038", "type_name_ko": "압력용기", "is_active": True},
    {"type_code": "040", "type_name_ko": "기타", "is_active": True},
    {"type_code": "014", "type_name_ko": "보일러", "is_active": True},
    {"type_code": "024", "type_name_ko": "컨베이어", "is_active": True},
    {"type_code": "999", "type_name_ko": "비활성테스트", "is_active": False},  # must be excluded
]

_SEED_WITH_CATALOG = {
    **_SEED,
    "equipment_type_inspection_map": _CATALOG_ROWS,
}

_FIVE_PROJECTOR_CODES = {"010", "014", "023", "024", "038"}


def test_T1_type_codes_active_catalog_sorted(monkeypatch):
    """T1: GET /type-codes returns active rows only, sorted by type_code ASC."""
    fake = FakeSB(_SEED_WITH_CATALOG)
    client = _make_client(fake, monkeypatch)
    r = client.get("/equipment-assets/type-codes")
    assert r.status_code == 200, r.text
    data = r.json()
    items = data["data"]["items"]
    codes = [i["equipment_type_code"] for i in items]
    # inactive 999 must be excluded
    assert "999" not in codes, f"inactive code 999 must not appear; got {codes}"
    # sorted ASC
    assert codes == sorted(codes), f"codes must be sorted ASC; got {codes}"
    assert data["data"]["total"] == len(items)


def test_T2_type_codes_exposes_required_fields(monkeypatch):
    """T2: each item has equipment_type_code and label."""
    fake = FakeSB(_SEED_WITH_CATALOG)
    client = _make_client(fake, monkeypatch)
    r = client.get("/equipment-assets/type-codes")
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    assert len(items) > 0
    for item in items:
        assert "equipment_type_code" in item, f"missing equipment_type_code in {item}"
        assert "label" in item, f"missing label in {item}"
        assert item["label"], f"label must be non-empty in {item}"


def test_T3_type_codes_not_filtered_to_five_projector_codes(monkeypatch):
    """T3: catalog contains codes beyond the 5 projector-mapped codes (001, 021, 040 also present)."""
    fake = FakeSB(_SEED_WITH_CATALOG)
    client = _make_client(fake, monkeypatch)
    r = client.get("/equipment-assets/type-codes")
    assert r.status_code == 200, r.text
    codes = {i["equipment_type_code"] for i in r.json()["data"]["items"]}
    non_projector = codes - _FIVE_PROJECTOR_CODES
    assert len(non_projector) >= 2, (
        f"T3: catalog must include non-projector codes; "
        f"got codes={codes}, non_projector={non_projector}"
    )
    # Also confirm projector codes are present (not over-filtered either direction)
    assert _FIVE_PROJECTOR_CODES.issubset(codes), (
        f"T3: all 5 projector codes must be present; missing={_FIVE_PROJECTOR_CODES - codes}"
    )


class _RaisingQ:
    """Fake query chain that raises on execute() — simulates DB failure."""
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def order(self, *a, **k): return self
    def execute(self):
        raise RuntimeError("simulated catalog DB failure")


class _CatalogFailSB:
    def table(self, name):
        if name == "equipment_type_inspection_map":
            return _RaisingQ()
        # other tables fall through to empty
        class _EmptyQ:
            def select(self, *a, **k): return self
            def eq(self, *a, **k): return self
            def in_(self, *a, **k): return self
            def order(self, *a, **k): return self
            def range(self, *a): return self
            def limit(self, *a): return self
            def execute(self):
                class _R:
                    data = []
                    count = 0
                return _R()
        return _EmptyQ()


def test_T4_type_codes_catalog_db_failure_returns_503(monkeypatch):
    """T4: equipment_type_inspection_map DB failure → HTTP 503 / EQUIPMENT_TYPE_CATALOG_UNAVAILABLE."""
    monkeypatch.setattr(_ea_mod, "get_supabase", lambda: _CatalogFailSB())
    app = FastAPI()
    app.include_router(_ea_mod.router)
    app.dependency_overrides[get_current_user] = lambda: _ADMIN
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/equipment-assets/type-codes")
    assert r.status_code == 503, f"expected 503 on catalog DB failure; got {r.status_code}: {r.text}"
    assert r.json()["detail"]["code"] == "EQUIPMENT_TYPE_CATALOG_UNAVAILABLE"


# ── T4A: data=None malformed response → 503 ──────────────────────────────────

class _NoneDataQ:
    """Returns a response with data=None — simulates malformed DB response."""
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def order(self, *a, **k): return self
    def execute(self):
        class _R:
            data = None
            count = 0
        return _R()


class _NoneDataSB:
    def table(self, name):
        if name == "equipment_type_inspection_map":
            return _NoneDataQ()
        return _CatalogFailSB().table(name)


def test_T4A_type_codes_data_none_returns_503(monkeypatch):
    """T4A: res.data=None → HTTP 503 / EQUIPMENT_TYPE_CATALOG_UNAVAILABLE (not empty 200)."""
    monkeypatch.setattr(_ea_mod, "get_supabase", lambda: _NoneDataSB())
    app = FastAPI()
    app.include_router(_ea_mod.router)
    app.dependency_overrides[get_current_user] = lambda: _ADMIN
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/equipment-assets/type-codes")
    assert r.status_code == 503, f"expected 503 for data=None; got {r.status_code}: {r.text}"
    assert r.json()["detail"]["code"] == "EQUIPMENT_TYPE_CATALOG_UNAVAILABLE"


# ── T4B: malformed row (missing type_code) → 503 ─────────────────────────────

_MALFORMED_CATALOG_ROWS = [
    {"type_code": "001", "type_name_ko": "리프트", "is_active": True},
    {"type_name_ko": "missing_type_code_row", "is_active": True},  # no type_code key
]

_SEED_WITH_MALFORMED_CATALOG = {
    **_SEED,
    "equipment_type_inspection_map": _MALFORMED_CATALOG_ROWS,
}


def test_T4B_type_codes_malformed_row_returns_503(monkeypatch):
    """T4B: catalog row missing type_code → HTTP 503 / EQUIPMENT_TYPE_CATALOG_UNAVAILABLE."""
    fake = FakeSB(_SEED_WITH_MALFORMED_CATALOG)
    client = _make_client(fake, monkeypatch)
    r = client.get("/equipment-assets/type-codes")
    assert r.status_code == 503, f"expected 503 for malformed row; got {r.status_code}: {r.text}"
    assert r.json()["detail"]["code"] == "EQUIPMENT_TYPE_CATALOG_UNAVAILABLE"
