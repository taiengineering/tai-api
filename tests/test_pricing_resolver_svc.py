"""WO-COMMON-TIER-PAYMENT-GATE-MODULARIZE-001 / B1.

resolve_plan 단위(R1~R6) + /public/pricing/* router parity.
실 DB/네트워크 0 — FakeSupabase fixture.
BEFORE 오라클 = main 의 public_pricing._load / resolve_price 본문 동결.
"""
from __future__ import annotations

import inspect

import pytest

from services.pricing_resolver_svc import (
    PRICE_MASTER_FIELDS,
    load_prices,
    resolve_plan,
)


# ── Frozen BEFORE (routers/public_pricing.py @ origin/main d3777b6) ──

_BEFORE_MASTER_FIELDS = (
    "id, service_type, sector, tier_code, criteria_type, criteria_min, criteria_max,"
    "amount, vat_included, vat_rate, billing_unit, display_name, sub_label, icon,"
    "is_recommended, is_active, sort_order"
)


def _before_load(supabase, service_type, sector=None):
    """동결: 추출 전 _load 본문. get_supabase → supabase 인자만 다름."""
    q = (
        supabase.table("price_master")
        .select(_BEFORE_MASTER_FIELDS)
        .eq("service_type", service_type)
        .eq("is_active", True)
    )
    if sector:
        q = q.eq("sector", sector.upper())
    rows = q.order("sort_order").execute().data or []

    ids = [r["id"] for r in rows]
    feat_map: dict = {}
    if ids:
        feats = (
            supabase.table("price_service_feature")
            .select("price_id, feature_text, feature_type, icon, sort_order, is_active")
            .in_("price_id", ids)
            .eq("is_active", True)
            .order("sort_order")
            .execute()
            .data or []
        )
        for f in feats:
            feat_map.setdefault(f["price_id"], []).append(f["feature_text"])

    for r in rows:
        r["features"] = feat_map.get(r["id"], [])
    return rows


def _before_resolve(supabase, service_type, sector, value=None):
    """동결: 추출 전 resolve_price 본문."""
    rows = _before_load(supabase, service_type.upper(), sector.upper())
    if not rows:
        return {"status": "not_found", "data": None}

    if value is None:
        chosen = next((r for r in rows if r.get("is_recommended")), rows[0])
        return {"status": "success", "data": chosen, "matched_by": "default"}

    match = None
    for r in rows:
        cmin = r.get("criteria_min")
        cmax = r.get("criteria_max")
        lo_ok = cmin is None or value >= float(cmin)
        hi_ok = cmax is None or value < float(cmax)
        if r.get("criteria_type") == "FLAT":
            continue
        if lo_ok and hi_ok:
            match = r
            break
    if match is None:
        match = next((r for r in rows if r.get("criteria_type") == "FLAT"), rows[-1])
    return {"status": "success", "data": match, "matched_by": "criteria"}


# ── Fake Supabase ──────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, table: str, store: dict):
        self._table = table
        self._store = store
        self._filters = []
        self._order_col = None

    def select(self, *_cols, **_kw):
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
        return self

    def order(self, col):
        self._order_col = col
        return self

    def execute(self):
        rows = [dict(r) for r in self._store.get(self._table, [])]
        for kind, col, val in self._filters:
            if kind == "eq":
                rows = [r for r in rows if r.get(col) == val]
            else:
                rows = [r for r in rows if r.get(col) in val]
        if self._order_col:
            rows.sort(key=lambda r: (r.get(self._order_col) is None, r.get(self._order_col)))
        return _FakeResponse(rows)


class _FakeSB:
    def __init__(self, store: dict):
        self._store = store

    def table(self, name: str):
        return _FakeQuery(name, self._store)


def _row(
    pid,
    service_type,
    sector,
    tier_code,
    *,
    criteria_type="RANGE",
    criteria_min=None,
    criteria_max=None,
    amount=10000,
    billing_unit="ONCE",
    is_recommended=False,
    is_active=True,
    sort_order=1,
):
    return {
        "id": pid,
        "service_type": service_type,
        "sector": sector,
        "tier_code": tier_code,
        "criteria_type": criteria_type,
        "criteria_min": criteria_min,
        "criteria_max": criteria_max,
        "amount": amount,
        "vat_included": False,
        "vat_rate": 0.1,
        "billing_unit": billing_unit,
        "display_name": tier_code,
        "sub_label": None,
        "icon": None,
        "is_recommended": is_recommended,
        "is_active": is_active,
        "sort_order": sort_order,
    }


def _store():
    return {
        "price_master": [
            # DIAGNOSIS BUILDING — STANDARD 경계 1000/3000
            _row("bld-s", "DIAGNOSIS", "BUILDING", "BLD_S", criteria_min=0, criteria_max=1000, sort_order=1, amount=50000),
            _row("bld-m", "DIAGNOSIS", "BUILDING", "BLD_M", criteria_min=1000, criteria_max=3000, sort_order=2, amount=80000, is_recommended=True),
            _row("bld-l", "DIAGNOSIS", "BUILDING", "BLD_L", criteria_min=3000, criteria_max=10000, sort_order=3, amount=120000),
            _row("bld-f", "DIAGNOSIS", "BUILDING", "BLD_FLAT", criteria_type="FLAT", sort_order=4, amount=0),
            _row("bld-dead", "DIAGNOSIS", "BUILDING", "BLD_DEAD", criteria_min=0, criteria_max=1, sort_order=0, is_active=False),
            # DIAGNOSIS INDUSTRY — STANDARD 경계 50/300
            _row("ind-s", "DIAGNOSIS", "INDUSTRY", "IND_S", criteria_min=1, criteria_max=50, sort_order=1, amount=40000),
            _row("ind-m", "DIAGNOSIS", "INDUSTRY", "IND_M", criteria_min=50, criteria_max=300, sort_order=2, amount=70000, is_recommended=True),
            _row("ind-l", "DIAGNOSIS", "INDUSTRY", "IND_L", criteria_min=300, criteria_max=1000, sort_order=3, amount=110000),
            _row("ind-f", "DIAGNOSIS", "INDUSTRY", "IND_FLAT", criteria_type="FLAT", sort_order=4, amount=0),
            # DIAGNOSIS CONSTRUCTION — STANDARD 경계 1e8 / 1e9
            _row("cst-s", "DIAGNOSIS", "CONSTRUCTION", "CST_S", criteria_min=0, criteria_max=100_000_000, sort_order=1, amount=60000),
            _row("cst-m", "DIAGNOSIS", "CONSTRUCTION", "CST_M", criteria_min=100_000_000, criteria_max=1_000_000_000, sort_order=2, amount=90000, is_recommended=True),
            _row("cst-l", "DIAGNOSIS", "CONSTRUCTION", "CST_L", criteria_min=1_000_000_000, criteria_max=10_000_000_000, sort_order=3, amount=150000),
            _row("cst-f", "DIAGNOSIS", "CONSTRUCTION", "CST_FLAT", criteria_type="FLAT", sort_order=4, amount=0),
            # SAAS BUILDING — FLAT 없음(last-row fallback) · 추천 없음(R6 first-row)
            _row("saas-bld-1", "SAAS", "BUILDING", "SAAS_S", criteria_min=0, criteria_max=500, sort_order=1, amount=59000, billing_unit="MONTHLY"),
            _row("saas-bld-2", "SAAS", "BUILDING", "SAAS_M", criteria_min=500, criteria_max=2000, sort_order=2, amount=99000, billing_unit="MONTHLY"),
            # SAAS INDUSTRY — 목록 parity용
            _row("saas-ind-1", "SAAS", "INDUSTRY", "SAAS_IND", criteria_min=1, criteria_max=100, sort_order=1, amount=79000, billing_unit="MONTHLY", is_recommended=True),
        ],
        "price_service_feature": [
            {"price_id": "bld-m", "feature_text": "feat-b", "feature_type": "PLUS", "icon": None, "sort_order": 2, "is_active": True},
            {"price_id": "bld-m", "feature_text": "feat-a", "feature_type": "PLUS", "icon": None, "sort_order": 1, "is_active": True},
            {"price_id": "bld-m", "feature_text": "feat-off", "feature_type": "PLUS", "icon": None, "sort_order": 0, "is_active": False},
            {"price_id": "saas-bld-1", "feature_text": "saas-feat", "feature_type": "PLUS", "icon": None, "sort_order": 1, "is_active": True},
        ],
    }


@pytest.fixture
def sb():
    return _FakeSB(_store())


# ── R1~R6 + frozen BEFORE ─────────────────────────────────────

def _assert_same(after, before, expected_id=None, matched_by=None):
    assert after == before
    if expected_id is not None:
        assert after["status"] == "success"
        assert after["data"]["id"] == expected_id
    if matched_by is not None:
        assert after.get("matched_by") == matched_by
    return after


def test_price_master_fields_unchanged():
    assert PRICE_MASTER_FIELDS == _BEFORE_MASTER_FIELDS


def test_load_prices_matches_frozen_before(sb):
    for service_type, sector in (
        ("DIAGNOSIS", "BUILDING"),
        ("DIAGNOSIS", "INDUSTRY"),
        ("DIAGNOSIS", "CONSTRUCTION"),
        ("SAAS", "BUILDING"),
        ("SAAS", None),
        ("DIAGNOSIS", "building"),
    ):
        assert load_prices(sb, service_type, sector) == _before_load(sb, service_type, sector)


def test_load_prices_joins_features_skips_inactive(sb):
    rows = load_prices(sb, "DIAGNOSIS", "BUILDING")
    ids = [r["id"] for r in rows]
    assert "bld-dead" not in ids
    assert ids == ["bld-s", "bld-m", "bld-l", "bld-f"]
    mid = next(r for r in rows if r["id"] == "bld-m")
    assert mid["features"] == ["feat-a", "feat-b"]


def test_r1_building_boundaries(sb):
    cases = (
        (999, "bld-s"),
        (1000, "bld-m"),
        (2999, "bld-m"),
        (3000, "bld-l"),
    )
    for value, expected_id in cases:
        after = resolve_plan(sb, "DIAGNOSIS", "BUILDING", value)
        before = _before_resolve(sb, "DIAGNOSIS", "BUILDING", value)
        _assert_same(after, before, expected_id=expected_id, matched_by="criteria")


def test_r2_industry_boundaries(sb):
    cases = (
        (49, "ind-s"),
        (50, "ind-m"),
        (299, "ind-m"),
        (300, "ind-l"),
    )
    for value, expected_id in cases:
        after = resolve_plan(sb, "DIAGNOSIS", "INDUSTRY", value)
        before = _before_resolve(sb, "DIAGNOSIS", "INDUSTRY", value)
        _assert_same(after, before, expected_id=expected_id, matched_by="criteria")


def test_r3_construction_boundaries(sb):
    cases = (
        (99_999_999, "cst-s"),
        (100_000_000, "cst-m"),
        (999_999_999, "cst-m"),
        (1_000_000_000, "cst-l"),
    )
    for value, expected_id in cases:
        after = resolve_plan(sb, "DIAGNOSIS", "CONSTRUCTION", value)
        before = _before_resolve(sb, "DIAGNOSIS", "CONSTRUCTION", value)
        _assert_same(after, before, expected_id=expected_id, matched_by="criteria")


def test_r4_flat_or_last_fallback(sb):
    after_flat = resolve_plan(sb, "DIAGNOSIS", "BUILDING", 20_000)
    before_flat = _before_resolve(sb, "DIAGNOSIS", "BUILDING", 20_000)
    _assert_same(after_flat, before_flat, expected_id="bld-f", matched_by="criteria")

    after_last = resolve_plan(sb, "SAAS", "BUILDING", 99_999)
    before_last = _before_resolve(sb, "SAAS", "BUILDING", 99_999)
    _assert_same(after_last, before_last, expected_id="saas-bld-2", matched_by="criteria")


def test_r5_not_found(sb):
    after = resolve_plan(sb, "NOPE", "BUILDING", 100)
    before = _before_resolve(sb, "NOPE", "BUILDING", 100)
    _assert_same(after, before)
    assert after == {"status": "not_found", "data": None}


def test_r6_default_recommended_or_first(sb):
    after_rec = resolve_plan(sb, "DIAGNOSIS", "BUILDING", None)
    before_rec = _before_resolve(sb, "DIAGNOSIS", "BUILDING", None)
    _assert_same(after_rec, before_rec, expected_id="bld-m", matched_by="default")

    after_first = resolve_plan(sb, "SAAS", "BUILDING", None)
    before_first = _before_resolve(sb, "SAAS", "BUILDING", None)
    _assert_same(after_first, before_first, expected_id="saas-bld-1", matched_by="default")


def test_service_has_no_fastapi_import():
    import ast
    from pathlib import Path

    tree = ast.parse(Path(inspect.getfile(resolve_plan)).read_text())
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module.split(".")[0])
    assert "fastapi" not in imported
    src = Path(inspect.getfile(resolve_plan)).read_text()
    assert "HTTPException" not in src
    assert "from fastapi" not in src
    assert "import fastapi" not in src


def test_router_has_no_direct_price_master_query():
    import routers.public_pricing as pp
    src = inspect.getsource(pp)
    assert 'table("price_master")' not in src
    assert "table('price_master')" not in src


# ── Router parity (동일 fixture) ────────────────────────────────

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import httpx  # noqa: F401
    _HAS_CLIENT = True
except Exception:  # noqa: BLE001
    _HAS_CLIENT = False

requires_client = pytest.mark.skipif(not _HAS_CLIENT, reason="httpx/TestClient 미설치")


@pytest.fixture
def client(sb, monkeypatch):
    import routers.public_pricing as pp

    pp._cache.clear()
    monkeypatch.setattr(pp, "get_supabase", lambda: sb)
    app = FastAPI()
    app.include_router(pp.router)
    with TestClient(app) as c:
        yield c
    pp._cache.clear()


@requires_client
@pytest.mark.parametrize(
    "service_type,sector,value,expected_id,matched_by",
    [
        ("DIAGNOSIS", "BUILDING", 999, "bld-s", "criteria"),
        ("DIAGNOSIS", "BUILDING", 1000, "bld-m", "criteria"),
        ("DIAGNOSIS", "BUILDING", 2999, "bld-m", "criteria"),
        ("DIAGNOSIS", "BUILDING", 3000, "bld-l", "criteria"),
        ("DIAGNOSIS", "INDUSTRY", 49, "ind-s", "criteria"),
        ("DIAGNOSIS", "INDUSTRY", 50, "ind-m", "criteria"),
        ("DIAGNOSIS", "INDUSTRY", 299, "ind-m", "criteria"),
        ("DIAGNOSIS", "INDUSTRY", 300, "ind-l", "criteria"),
        ("DIAGNOSIS", "CONSTRUCTION", 99_999_999, "cst-s", "criteria"),
        ("DIAGNOSIS", "CONSTRUCTION", 100_000_000, "cst-m", "criteria"),
        ("DIAGNOSIS", "CONSTRUCTION", 999_999_999, "cst-m", "criteria"),
        ("DIAGNOSIS", "CONSTRUCTION", 1_000_000_000, "cst-l", "criteria"),
        ("DIAGNOSIS", "BUILDING", 20_000, "bld-f", "criteria"),
        ("NOPE", "BUILDING", 100, None, None),
        ("DIAGNOSIS", "BUILDING", None, "bld-m", "default"),
    ],
)
def test_router_resolve_parity(client, sb, service_type, sector, value, expected_id, matched_by):
    params = {"service_type": service_type, "sector": sector}
    if value is not None:
        params["value"] = value
    http = client.get("/public/pricing/resolve", params=params).json()
    svc = resolve_plan(sb, service_type, sector, value)
    before = _before_resolve(sb, service_type, sector, value)
    assert http == svc == before
    if expected_id is None:
        assert http == {"status": "not_found", "data": None}
    else:
        assert http["data"]["id"] == expected_id
        assert http["matched_by"] == matched_by


@requires_client
def test_list_endpoints_parity_and_cache(client, sb):
    saas_rows = load_prices(sb, "SAAS", "BUILDING")
    diag_rows = load_prices(sb, "DIAGNOSIS", "BUILDING")
    before_saas = _before_load(sb, "SAAS", "BUILDING")
    before_diag = _before_load(sb, "DIAGNOSIS", "BUILDING")
    assert saas_rows == before_saas
    assert diag_rows == before_diag

    r1 = client.get("/public/pricing/saas-plans", params={"sector": "BUILDING"}).json()
    assert r1 == {"data": saas_rows}

    r2 = client.get("/public/pricing/diagnosis-reports", params={"sector": "BUILDING"}).json()
    assert r2 == {"data": diag_rows}

    all1 = client.get("/public/pricing/all", params={"sector": "BUILDING"}).json()
    assert all1 == {
        "status": "success",
        "cached": False,
        "saas_plans": saas_rows,
        "diagnosis_plans": diag_rows,
    }
    all2 = client.get("/public/pricing/all", params={"sector": "BUILDING"}).json()
    assert all2["cached"] is True
    assert all2["saas_plans"] == saas_rows
    assert all2["diagnosis_plans"] == diag_rows

    alias_saas = client.get("/public/pricing/saas", params={"sector": "BUILDING"}).json()
    alias_diag = client.get("/public/pricing/diagnosis", params={"sector": "BUILDING"}).json()
    assert alias_saas == r1
    assert alias_diag == r2


@requires_client
def test_resolve_is_uncached_lists_are_cached(client, sb):
    first = client.get(
        "/public/pricing/resolve",
        params={"service_type": "DIAGNOSIS", "sector": "BUILDING", "value": 1500},
    ).json()
    assert first["data"]["id"] == "bld-m"
    assert first["data"]["display_name"] == "BLD_M"

    for r in sb._store["price_master"]:
        if r["id"] == "bld-m":
            r["display_name"] = "MUTATED"
    second = client.get(
        "/public/pricing/resolve",
        params={"service_type": "DIAGNOSIS", "sector": "BUILDING", "value": 1500},
    ).json()
    assert second["data"]["id"] == "bld-m"
    assert second["data"]["display_name"] == "MUTATED"

    listed = client.get("/public/pricing/saas-plans", params={"sector": "BUILDING"}).json()
    sb._store["price_master"] = [r for r in sb._store["price_master"] if r["id"] != "saas-bld-1"]
    listed2 = client.get("/public/pricing/saas-plans", params={"sector": "BUILDING"}).json()
    assert listed2 == listed

    cleared = client.delete("/public/pricing/cache").json()
    assert cleared["status"] == "success"
    listed3 = client.get("/public/pricing/saas-plans", params={"sector": "BUILDING"}).json()
    ids = [r["id"] for r in listed3["data"]]
    assert "saas-bld-1" not in ids
