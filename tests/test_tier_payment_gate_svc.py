"""WO-COMMON-TIER-PAYMENT-GATE-MODULARIZE-001 / B2.

evaluate_saas_tier_gate 단위(G1~G15) + GET /payments/tier-gate.
실 DB/네트워크 0. mutation 0. 판정 = GPT.
"""
from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

import pytest

from services.tier_payment_gate_svc import TierGateError, evaluate_saas_tier_gate
import services.tier_payment_gate_svc as gate_svc

CO_OWN = "co-own"
CO_OTHER = "co-other"
FAC_IND = "fac-ind"
FAC_BLD = "fac-bld"
FAC_OTHER = "fac-other"
SITE_OWN = "site-own"
SITE_OTHER = "site-other"
CALLER = {
    "id": "user-own",
    "company_id": CO_OWN,
    "factory_id": FAC_IND,
    "role_code": "011",
}

SVC_PATH = Path(__file__).resolve().parents[1] / "services" / "tier_payment_gate_svc.py"


# ── Fake Supabase ──────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, table: str, sb: "_FakeSB"):
        self._table = table
        self._sb = sb
        self._filters = []
        self._order_col = None
        self._limit = None
        self._op = "select"

    def select(self, *_cols, **_kw):
        self._op = "select"
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
        return self

    def order(self, col, **_kw):
        self._order_col = col
        return self

    def limit(self, n):
        self._limit = n
        return self

    def insert(self, payload):
        self._op = "insert"
        self._sb.writes.append(("insert", self._table, payload))
        return self

    def update(self, payload):
        self._op = "update"
        self._sb.writes.append(("update", self._table, payload))
        return self

    def delete(self):
        self._op = "delete"
        self._sb.writes.append(("delete", self._table, None))
        return self

    def upsert(self, payload):
        self._op = "upsert"
        self._sb.writes.append(("upsert", self._table, payload))
        return self

    def execute(self):
        if self._op in ("insert", "update", "delete", "upsert"):
            return _FakeResponse([])
        rows = [dict(r) for r in self._sb.store.get(self._table, [])]
        for kind, col, val in self._filters:
            if kind == "eq":
                rows = [r for r in rows if r.get(col) == val]
            else:
                rows = [r for r in rows if r.get(col) in val]
        if self._order_col:
            rows.sort(
                key=lambda r: (r.get(self._order_col) is None, r.get(self._order_col))
            )
        if self._limit is not None:
            rows = rows[: self._limit]
        return _FakeResponse(rows)


class _FakeSB:
    def __init__(self, store: dict):
        self.store = store
        self.writes = []

    def table(self, name: str):
        return _FakeQuery(name, self)


def _pm(pid, sector, tier, sort_order, cmin, cmax, amount):
    return {
        "id": pid,
        "service_type": "SAAS",
        "sector": sector,
        "tier_code": tier,
        "criteria_type": "RANGE",
        "criteria_min": cmin,
        "criteria_max": cmax,
        "amount": amount,
        "vat_included": False,
        "vat_rate": 0.1,
        "billing_unit": "MONTHLY",
        "display_name": tier,
        "sub_label": None,
        "icon": None,
        "is_recommended": False,
        "is_active": True,
        "sort_order": sort_order,
    }


def _contract(cid, company_id, plan_code, *, service_type="SAAS", status="ACTIVE", active=True):
    return {
        "id": cid,
        "company_id": company_id,
        "plan_code": plan_code,
        "service_type": service_type,
        "status_code": status,
        "is_active": active,
    }


def _base_store():
    return {
        "role_data_scope": [{"role_code": "011", "scope_type": "COMPANY"}],
        "factories": [
            {
                "id": FAC_IND,
                "company_id": CO_OWN,
                "employee_count": 80,
                "building_area": 500,
            },
            {
                "id": FAC_BLD,
                "company_id": CO_OWN,
                "employee_count": 10,
                "building_area": 1500,
            },
            {
                "id": FAC_OTHER,
                "company_id": CO_OTHER,
                "employee_count": 9999,
                "building_area": 99999,
            },
        ],
        "construction_sites": [
            {"id": SITE_OWN, "company_id": CO_OWN, "contract_amount": 50},
            {"id": SITE_OTHER, "company_id": CO_OTHER, "contract_amount": 50},
        ],
        "contracts": [
            _contract("ct-ind", CO_OWN, "INDUSTRY_BUSINESS"),
            _contract("ct-noise-expired", CO_OWN, "INDUSTRY_PRO", status="EXPIRED"),
            _contract("ct-noise-diag", CO_OWN, "INDUSTRY_PRO", service_type="DIAGNOSIS"),
            _contract("ct-noise-off", CO_OWN, "INDUSTRY_PRO", active=False),
            _contract("ct-other", CO_OTHER, "INDUSTRY_PRO"),
        ],
        "price_master": [
            _pm("ind-s", "INDUSTRY", "INDUSTRY_STARTER", 1, 0, 50, 59000),
            _pm("ind-m", "INDUSTRY", "INDUSTRY_BUSINESS", 2, 50, 300, 79000),
            _pm("ind-l", "INDUSTRY", "INDUSTRY_PRO", 3, 300, 100000, 99000),
            _pm("bld-s", "BUILDING", "BUILDING_LITE", 1, 0, 1000, 49000),
            _pm("bld-m", "BUILDING", "BUILDING_BASIC", 2, 1000, 3000, 69000),
            _pm("bld-l", "BUILDING", "BUILDING_STANDARD", 3, 3000, 20000, 89000),
            _pm("cst-s", "CONSTRUCTION", "CONSTRUCTION_STANDARD", 1, 0, 1_000_000_000, 99000),
            _pm("cst-m", "CONSTRUCTION", "CONSTRUCTION_PREMIUM", 2, 1_000_000_000, 5_000_000_000, 149000),
            _pm("cst-l", "CONSTRUCTION", "CONSTRUCTION_CUSTOM", 3, 5_000_000_000, 100_000_000_000, 0),
        ],
        "price_service_feature": [],
    }


@pytest.fixture
def store():
    return _base_store()


@pytest.fixture
def sb(store):
    return _FakeSB(store)


def _eval(sb, **kw):
    return evaluate_saas_tier_gate(sb, CALLER, **kw)


def _err(sb, **kw):
    with pytest.raises(TierGateError) as ei:
        _eval(sb, **kw)
    return ei.value


def _set_plan(store, plan_code, company_id=CO_OWN):
    for c in store["contracts"]:
        if c["id"] == "ct-ind" and c["company_id"] == company_id:
            c["plan_code"] = plan_code
            return
    store["contracts"].append(_contract("ct-ind", company_id, plan_code))


# ── G1~G10 단위 ─────────────────────────────────────


def test_g1_equal_sort_fit(sb, store):
    out = _eval(sb, factory_id=FAC_IND)
    assert out["status"] == "FIT"
    assert out["sector"] == "INDUSTRY"
    assert out["current_plan"]["tier_code"] == "INDUSTRY_BUSINESS"
    assert out["required_plan"]["tier_code"] == "INDUSTRY_BUSINESS"
    assert out["current_plan"]["sort_order"] == out["required_plan"]["sort_order"]
    assert "upgrade_supply" not in out
    assert "payment_url" not in out
    assert sb.writes == []


def test_g2_higher_current_fit_no_downgrade(sb, store):
    _set_plan(store, "INDUSTRY_PRO")
    store["factories"][0]["employee_count"] = 10
    out = _eval(sb, factory_id=FAC_IND)
    assert out["status"] == "FIT"
    assert out["current_plan"]["sort_order"] > out["required_plan"]["sort_order"]
    assert out["required_plan"]["tier_code"] == "INDUSTRY_STARTER"
    assert sb.writes == []


def test_g3_insufficient_upgrade_required_no_mutation(sb, store):
    _set_plan(store, "INDUSTRY_STARTER")
    out = _eval(sb, factory_id=FAC_IND)
    assert out["status"] == "UPGRADE_REQUIRED"
    assert out["current_plan"]["tier_code"] == "INDUSTRY_STARTER"
    assert out["required_plan"]["tier_code"] == "INDUSTRY_BUSINESS"
    assert sb.writes == []


def test_g4_no_active_saas_contract(sb, store):
    store["contracts"] = [
        c for c in store["contracts"] if c["company_id"] != CO_OWN or c["id"] != "ct-ind"
    ]
    err = _err(sb, factory_id=FAC_IND)
    assert err.code == "NO_ACTIVE_SAAS_CONTRACT"


def test_g5_unknown_current_plan_no_fallback(sb, store):
    _set_plan(store, "NO_SUCH_PLAN")
    err = _err(sb, factory_id=FAC_IND)
    assert err.code == "UNKNOWN_CURRENT_PLAN"


def test_g6_entity_sector_mismatch_both_ways(sb, store):
    _set_plan(store, "CONSTRUCTION_STANDARD")
    err_f = _err(sb, factory_id=FAC_IND)
    assert err_f.code == "ENTITY_SECTOR_MISMATCH"

    _set_plan(store, "INDUSTRY_BUSINESS")
    err_s = _err(sb, site_id=SITE_OWN)
    assert err_s.code == "ENTITY_SECTOR_MISMATCH"


def test_g7_ambiguous_active_saas_no_pick(sb, store):
    store["contracts"].append(_contract("ct-ind-2", CO_OWN, "INDUSTRY_PRO"))
    err = _err(sb, factory_id=FAC_IND)
    assert err.code == "AMBIGUOUS_ACTIVE_SAAS_CONTRACT"


def test_g8_pricing_not_found_no_current_substitute(sb, monkeypatch):
    monkeypatch.setattr(
        gate_svc,
        "resolve_plan",
        lambda *_a, **_k: {"status": "not_found", "data": None},
    )
    err = _err(sb, factory_id=FAC_IND)
    assert err.code == "PRICING_NOT_FOUND"


def test_g10_metric_three_sources(sb, store):
    ind = _eval(sb, factory_id=FAC_IND)
    assert ind["metric"] == {"type": "employee_count", "value": 80, "unit": "명"}

    _set_plan(store, "BUILDING_BASIC")
    bld = _eval(sb, factory_id=FAC_BLD)
    assert bld["metric"] == {"type": "building_area", "value": 1500, "unit": "㎡"}
    assert bld["required_plan"]["tier_code"] == "BUILDING_BASIC"

    _set_plan(store, "CONSTRUCTION_STANDARD")
    cst = _eval(sb, site_id=SITE_OWN)
    assert cst["metric"]["type"] == "construction_amount"
    assert cst["metric"]["value"] == 5_000_000_000
    assert cst["metric"]["unit"] == "원"
    assert cst["metric"]["source_value"] == 50
    assert cst["metric"]["source_unit"] == "억원"


def test_scale_none_is_not_zero(sb, store):
    store["factories"][0]["employee_count"] = None
    err = _err(sb, factory_id=FAC_IND)
    assert err.code == "MISSING_SCALE_VALUE"

    store["factories"][0]["employee_count"] = 0
    out = _eval(sb, factory_id=FAC_IND)
    assert out["metric"]["value"] == 0
    assert out["required_plan"]["tier_code"] == "INDUSTRY_STARTER"


def test_g15_construction_eok_to_won_spy(sb, store, monkeypatch):
    _set_plan(store, "CONSTRUCTION_STANDARD")
    seen = {}
    real = gate_svc.resolve_plan

    def spy(supabase, service_type, sector, value=None):
        seen["value"] = value
        seen["sector"] = sector
        seen["service_type"] = service_type
        return real(supabase, service_type, sector, value)

    monkeypatch.setattr(gate_svc, "resolve_plan", spy)
    out = _eval(sb, site_id=SITE_OWN)
    assert seen["value"] == 5_000_000_000
    assert seen["value"] != 50
    assert seen["sector"] == "CONSTRUCTION"
    assert seen["service_type"] == "SAAS"
    assert out["metric"]["value"] == 5_000_000_000


# ── G11~G14 정적 ─────────────────────────────────────


def test_g11_client_injection_fields_absent():
    from routers.payment import get_tier_gate

    params = set(inspect.signature(get_tier_gate).parameters)
    forbidden = {
        "sector",
        "current_plan",
        "required_plan",
        "value",
        "employee_count",
        "building_area",
        "construction_amount",
        "sort_order",
        "amount",
    }
    assert forbidden.isdisjoint(params)
    assert "factory_id" in params
    assert "site_id" in params
    assert "authorization" in params


def test_g12_no_criteria_formula_uses_resolve_plan():
    src = SVC_PATH.read_text()
    tree = ast.parse(src)
    assert "criteria_min" not in src
    assert "criteria_max" not in src
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                calls.append(func.id)
            elif isinstance(func, ast.Attribute):
                calls.append(func.attr)
    assert "resolve_plan" in calls
    assert "load_prices" in calls


def test_g13_no_hardcoded_plan_map():
    src = SVC_PATH.read_text()
    assert "PLAN_MAP" not in src
    assert "PLAN_LEVELS" not in src
    assert "normalize_plan" not in src
    assert r"_V\d+" not in src
    assert "help_plan_level" not in src
    assert "payment_post_process" not in src


def test_g14_no_mutation_payment_or_leg():
    src = SVC_PATH.read_text()
    for token in (".insert(", ".update(", ".delete(", ".upsert("):
        assert token not in src
    assert "payment_svc" not in src
    assert "run_inicis" not in src
    assert "legal_engine" not in src
    assert "run_safe_" not in src
    from routers import payment as pay_mod

    fn_src = inspect.getsource(pay_mod.get_tier_gate)
    for token in (".insert(", ".update(", ".delete(", ".upsert("):
        assert token not in fn_src
    assert "payment_svc" not in fn_src
    assert "run_inicis" not in fn_src
    assert "legal_engine" not in fn_src
    assert "run_safe_" not in fn_src


def test_service_has_no_fastapi_import():
    tree = ast.parse(SVC_PATH.read_text())
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module.split(".")[0])
    assert "fastapi" not in imported
    src = SVC_PATH.read_text()
    assert "HTTPException" not in src
    assert "from fastapi" not in src


# ── Router ──────────────────────────────────────────

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
    import routers.payment as pay_mod

    monkeypatch.setattr(pay_mod, "get_supabase", lambda: sb)
    monkeypatch.setattr(pay_mod, "get_current_user", lambda authorization=None: CALLER)
    app = FastAPI()
    app.include_router(pay_mod.router)
    with TestClient(app) as c:
        yield c


@requires_client
def test_router_g1_fit(client):
    r = client.get("/payments/tier-gate", params={"factory_id": FAC_IND})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "FIT"
    assert body["required_plan"]["tier_code"] == "INDUSTRY_BUSINESS"


@requires_client
def test_router_g3_upgrade_required_is_200(client, store):
    _set_plan(store, "INDUSTRY_STARTER")
    r = client.get("/payments/tier-gate", params={"factory_id": FAC_IND})
    assert r.status_code == 200
    assert r.json()["status"] == "UPGRADE_REQUIRED"


@requires_client
def test_router_g4_conflict_409(client, store):
    store["contracts"] = [c for c in store["contracts"] if c["id"] != "ct-ind"]
    r = client.get("/payments/tier-gate", params={"factory_id": FAC_IND})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "NO_ACTIVE_SAAS_CONTRACT"


@requires_client
def test_router_g9_foreign_factory_and_site_404(client, sb):
    rf = client.get("/payments/tier-gate", params={"factory_id": FAC_OTHER})
    assert rf.status_code == 404
    dumped_f = json.dumps(rf.json(), ensure_ascii=False)
    assert "INDUSTRY_PRO" not in dumped_f
    assert "9999" not in dumped_f
    assert "upgrade" not in dumped_f.lower()

    rs = client.get("/payments/tier-gate", params={"site_id": SITE_OTHER})
    assert rs.status_code == 404
    dumped_s = json.dumps(rs.json(), ensure_ascii=False)
    assert "CONSTRUCTION" not in dumped_s
    assert dumped_s.count("50") == 0 or "현장을 찾을 수 없습니다" in dumped_s


@requires_client
def test_router_xor_422(client):
    both = client.get(
        "/payments/tier-gate",
        params={"factory_id": FAC_IND, "site_id": SITE_OWN},
    )
    assert both.status_code == 422
    none = client.get("/payments/tier-gate")
    assert none.status_code == 422


@requires_client
def test_router_g8_pricing_503(client, monkeypatch):
    monkeypatch.setattr(
        gate_svc,
        "resolve_plan",
        lambda *_a, **_k: {"status": "not_found", "data": None},
    )
    r = client.get("/payments/tier-gate", params={"factory_id": FAC_IND})
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "PRICING_NOT_FOUND"


@requires_client
def test_router_g11_injected_query_ignored(client):
    r = client.get(
        "/payments/tier-gate",
        params={
            "factory_id": FAC_IND,
            "sector": "CONSTRUCTION",
            "current_plan": "INDUSTRY_PRO",
            "required_plan": "INDUSTRY_STARTER",
            "value": 1,
            "employee_count": 1,
            "amount": 1,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["sector"] == "INDUSTRY"
    assert body["current_plan"]["tier_code"] == "INDUSTRY_BUSINESS"
    assert body["metric"]["value"] == 80


@requires_client
def test_router_auth_required(monkeypatch, sb):
    import routers.payment as pay_mod
    from routers.auth import get_current_user as real_get_user

    monkeypatch.setattr(pay_mod, "get_supabase", lambda: sb)
    monkeypatch.setattr(pay_mod, "get_current_user", real_get_user)
    app = FastAPI()
    app.include_router(pay_mod.router)
    with TestClient(app) as c:
        r = c.get("/payments/tier-gate", params={"factory_id": FAC_IND})
    assert r.status_code == 401


@requires_client
def test_router_g15_construction(client, store, monkeypatch):
    _set_plan(store, "CONSTRUCTION_STANDARD")
    seen = {}
    real = gate_svc.resolve_plan

    def spy(supabase, service_type, sector, value=None):
        seen["value"] = value
        return real(supabase, service_type, sector, value)

    monkeypatch.setattr(gate_svc, "resolve_plan", spy)
    r = client.get("/payments/tier-gate", params={"site_id": SITE_OWN})
    assert r.status_code == 200
    assert seen["value"] == 5_000_000_000
    body = r.json()
    assert body["metric"]["source_value"] == 50
    assert body["metric"]["value"] == 5_000_000_000
