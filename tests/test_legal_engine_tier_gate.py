"""WO-COMMON-TIER-PAYMENT-GATE-MODULARIZE-001 / B4.

SaaS LEG 3 endpoint commercial gate. LEG 엔진/assembler/finalizer 불변.
실 DB/네트워크 0. 판정 = GPT.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.tier_payment_gate_svc import TierGateError

CO_OWN = "co-own"
CO_OTHER = "co-other"
FAC_OWN = "fac-own"
FAC_OTHER = "fac-other"
SITE_OWN = "site-own"
SITE_OTHER = "site-other"
CALLER = {
    "id": "user-own",
    "company_id": CO_OWN,
    "factory_id": FAC_OWN,
    "role_code": "011",
}

ROUTER_PATH = Path(__file__).resolve().parents[1] / "routers" / "legal_engine.py"

IND_PATH = "/legal-engine/diagnose/industrial-leg"
BLD_PATH = "/legal-engine/diagnose/building-leg"
CST_PATH = "/legal-engine/diagnose/construction-leg"

IND_BODY = {"factory_id": FAC_OWN, "input": {}}
BLD_BODY = {"factory_id": FAC_OWN, "input": {}}
CST_BODY = {"site_id": SITE_OWN, "input": {}}

FIT = {
    "status": "FIT",
    "sector": "INDUSTRY",
    "current_plan": {"tier_code": "INDUSTRY_BUSINESS", "sort_order": 2, "amount": 79000},
    "required_plan": {"tier_code": "INDUSTRY_STARTER", "sort_order": 1, "amount": 59000},
    "metric": {"name": "employee_count", "value": 80, "unit": "명"},
}

UPGRADE = {
    "status": "UPGRADE_REQUIRED",
    "sector": "INDUSTRY",
    "current_plan": {"tier_code": "INDUSTRY_STARTER", "sort_order": 1, "amount": 59000},
    "required_plan": {"tier_code": "INDUSTRY_PRO", "sort_order": 3, "amount": 99000},
    "metric": {"name": "employee_count", "value": 400, "unit": "명"},
}

SECTORS = (
    pytest.param(
        IND_PATH, IND_BODY, "run_safe_industrial_leg", {"factory_id": FAC_OWN, "site_id": None},
        id="INDUSTRY",
    ),
    pytest.param(
        BLD_PATH, BLD_BODY, "run_safe_building_leg", {"factory_id": FAC_OWN, "site_id": None},
        id="BUILDING",
    ),
    pytest.param(
        CST_PATH, CST_BODY, "run_safe_construction_leg", {"factory_id": None, "site_id": SITE_OWN},
        id="CONSTRUCTION",
    ),
)


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, table: str, sb: "_FakeSB"):
        self._table = table
        self._sb = sb
        self._filters = []
        self._limit = None

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        rows = [dict(r) for r in self._sb.store.get(self._table, [])]
        for col, val in self._filters:
            rows = [r for r in rows if r.get(col) == val]
        if self._limit is not None:
            rows = rows[: self._limit]
        return _FakeResponse(rows)


class _FakeSB:
    def __init__(self, store: dict):
        self.store = store

    def table(self, name: str):
        return _FakeQuery(name, self)


def _store():
    return {
        "role_data_scope": [{"role_code": "011", "scope_type": "COMPANY"}],
        "factories": [
            {"id": FAC_OWN, "company_id": CO_OWN},
            {"id": FAC_OTHER, "company_id": CO_OTHER},
        ],
        "construction_sites": [
            {"id": SITE_OWN, "company_id": CO_OWN, "contract_amount": 50},
            {"id": SITE_OTHER, "company_id": CO_OTHER, "contract_amount": 50},
        ],
    }


def _ok_out(factory_id="fac-from-runtime"):
    return {
        "factory_id": factory_id,
        "full_result": {"sector": "X", "obligations_raw": []},
        "contract_version": "v-test",
        "unresolved_fields": [],
    }


def _fin_ok(*_a, **_k):
    return {
        "status": "success",
        "data": {"ok": True},
        "contract_version": "v-test",
        "unresolved_fields": [],
        "diagnosis_id": "diag-1",
        "inspection_materialization": {"status": "MATERIALIZED"},
    }


@pytest.fixture
def le_mod(monkeypatch):
    import routers.legal_engine as LE

    sb = _FakeSB(_store())
    monkeypatch.setattr(LE, "get_supabase", lambda: sb)
    monkeypatch.setattr(LE, "get_current_user", lambda authorization=None: dict(CALLER))
    app = FastAPI()
    app.include_router(LE.router)
    client = TestClient(app, raise_server_exceptions=False)
    return LE, client, sb


def _install_spies(monkeypatch, LE, *, gate_result=FIT, gate_error=None, enabled=True):
    log = []

    def eval_spy(supabase, current, *, factory_id=None, site_id=None):
        log.append(("gate", {"factory_id": factory_id, "site_id": site_id}))
        if gate_error is not None:
            raise gate_error
        return dict(gate_result)

    def enabled_spy():
        log.append(("enabled", None))
        return enabled

    def _runtime(name):
        def runtime_spy(*_a, **_k):
            log.append(("runtime", name))
            return _ok_out()
        return runtime_spy

    def fin_spy(*_a, **_k):
        log.append(("finalize", None))
        return _fin_ok()

    monkeypatch.setattr(LE, "evaluate_saas_tier_gate", eval_spy)
    monkeypatch.setattr(LE.leg_runtime_client, "is_enabled", enabled_spy)
    monkeypatch.setattr(LE, "run_safe_industrial_leg", _runtime("run_safe_industrial_leg"))
    monkeypatch.setattr(LE, "run_safe_building_leg", _runtime("run_safe_building_leg"))
    monkeypatch.setattr(LE, "run_safe_construction_leg", _runtime("run_safe_construction_leg"))
    monkeypatch.setattr(LE, "finalize_saas_leg_result", fin_spy)
    return log


def _count(log, name):
    return sum(1 for n, _ in log if n == name)


def _gate_kw(log):
    for n, kw in log:
        if n == "gate":
            return kw
    return None


# ── B4-1/3/5 FIT → runtime 1 + finalizer 1 ─────────────


@pytest.mark.parametrize("path,body,runtime_attr,gate_kw", SECTORS)
def test_B4_fit_runs_runtime_and_finalizer(le_mod, monkeypatch, path, body, runtime_attr, gate_kw):
    LE, client, _sb = le_mod
    log = _install_spies(monkeypatch, LE, gate_result=FIT, enabled=True)
    r = client.post(path, json=body)
    assert r.status_code == 200, r.text
    assert _count(log, "gate") == 1
    assert _gate_kw(log) == gate_kw
    assert _count(log, "enabled") == 1
    assert _count(log, "runtime") == 1
    assert _count(log, "finalize") == 1
    assert [n for n, _ in log] == ["gate", "enabled", "runtime", "finalize"]
    assert log[2] == ("runtime", runtime_attr)
    for other in (
        "run_safe_industrial_leg",
        "run_safe_building_leg",
        "run_safe_construction_leg",
    ):
        if other != runtime_attr:
            assert ("runtime", other) not in log


# ── B4-2/4/6 UPGRADE_REQUIRED → 402 · runtime 0 · finalize 0 ──


@pytest.mark.parametrize("path,body,runtime_attr,gate_kw", SECTORS)
def test_B4_upgrade_required_402_no_runtime(le_mod, monkeypatch, path, body, runtime_attr, gate_kw):
    LE, client, _sb = le_mod
    log = _install_spies(monkeypatch, LE, gate_result=UPGRADE, enabled=True)
    r = client.post(path, json=body)
    assert r.status_code == 402, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "SAAS_TIER_UPGRADE_REQUIRED"
    assert detail["current_plan"] == UPGRADE["current_plan"]
    assert detail["required_plan"] == UPGRADE["required_plan"]
    assert detail["metric"] == UPGRADE["metric"]
    assert detail["sector"] == UPGRADE["sector"]
    assert _count(log, "gate") == 1
    assert _gate_kw(log) == gate_kw
    assert _count(log, "enabled") == 0
    assert _count(log, "runtime") == 0
    assert _count(log, "finalize") == 0
    assert ("runtime", runtime_attr) not in log


# ── B4-7 factory ownership 실패 → 404 · gate 0 · runtime 0 ──


def test_B4_7_factory_ownership_404_skips_gate(le_mod, monkeypatch):
    LE, client, _sb = le_mod
    log = _install_spies(monkeypatch, LE, gate_result=FIT, enabled=True)
    r = client.post(IND_PATH, json={"factory_id": FAC_OTHER, "input": {}})
    assert r.status_code == 404, r.text
    assert _count(log, "gate") == 0
    assert _count(log, "enabled") == 0
    assert _count(log, "runtime") == 0
    assert _count(log, "finalize") == 0


# ── B4-8 site ownership 실패 → 404 · gate 0 · runtime 0 ──


def test_B4_8_site_ownership_404_skips_gate(le_mod, monkeypatch):
    LE, client, _sb = le_mod
    log = _install_spies(monkeypatch, LE, gate_result=FIT, enabled=True)
    r = client.post(CST_PATH, json={"site_id": SITE_OTHER, "input": {}})
    assert r.status_code == 404, r.text
    assert _count(log, "gate") == 0
    assert _count(log, "enabled") == 0
    assert _count(log, "runtime") == 0
    assert _count(log, "finalize") == 0


# ── B4-9 PRICING_NOT_FOUND → 503 · runtime 0 ──


def test_B4_9_pricing_not_found_503(le_mod, monkeypatch):
    LE, client, _sb = le_mod
    err = TierGateError("PRICING_NOT_FOUND", "필요 플랜을 산정할 수 없습니다.")
    log = _install_spies(monkeypatch, LE, gate_error=err, enabled=True)
    r = client.post(IND_PATH, json=IND_BODY)
    assert r.status_code == 503, r.text
    assert r.json()["detail"]["code"] == "PRICING_NOT_FOUND"
    assert _count(log, "runtime") == 0
    assert _count(log, "finalize") == 0
    assert _count(log, "enabled") == 0


# ── B4-10 NO_ACTIVE_SAAS_CONTRACT → 409 · runtime 0 (silent fallback 금지) ──


def test_B4_10_no_active_contract_409(le_mod, monkeypatch):
    LE, client, _sb = le_mod
    err = TierGateError("NO_ACTIVE_SAAS_CONTRACT", "활성 SaaS 계약이 없습니다.")
    log = _install_spies(monkeypatch, LE, gate_error=err, enabled=True)
    r = client.post(IND_PATH, json=IND_BODY)
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "NO_ACTIVE_SAAS_CONTRACT"
    assert _count(log, "runtime") == 0
    assert _count(log, "finalize") == 0
    assert _count(log, "enabled") == 0


# ── B4-11 FIT + is_enabled()==false → 기존 503 · runtime 0 ──


def test_B4_11_fit_but_leg_disabled_keeps_503(le_mod, monkeypatch):
    LE, client, _sb = le_mod
    log = _install_spies(monkeypatch, LE, gate_result=FIT, enabled=False)
    r = client.post(IND_PATH, json=IND_BODY)
    assert r.status_code == 503, r.text
    assert r.json()["detail"] == "LEG runtime 미설정"
    assert _count(log, "gate") == 1
    assert _count(log, "enabled") == 1
    assert _count(log, "runtime") == 0
    assert _count(log, "finalize") == 0


# ── B4-12 gate 가 is_enabled() 앞 ──
# ── B4-13 gate 가 sector runtime 앞 ──


def test_B4_12_13_source_order_gate_before_enabled_and_runtime():
    import routers.legal_engine as LE

    cases = (
        (LE.diagnose_industrial_leg, "_ensure_factory_own", "run_safe_industrial_leg"),
        (LE.diagnose_building_leg, "_ensure_factory_own", "run_safe_building_leg"),
        (LE.diagnose_construction_leg, "_ensure_own_company", "run_safe_construction_leg"),
    )
    for fn, ownership, runtime in cases:
        src = inspect.getsource(fn)
        own_i = src.index(ownership)
        gate_i = src.index("_assert_saas_tier_fit_http")
        en_i = src.index("is_enabled()")
        rt_i = src.index(runtime)
        assert own_i < gate_i < en_i < rt_i, fn.__name__


def test_B4_construction_gate_uses_site_id_only():
    import routers.legal_engine as LE

    src = inspect.getsource(LE.diagnose_construction_leg)
    assert "site_id=body.site_id" in src
    assert "factory_id=body.factory_id" not in src
    assert "construction_amount" not in src
    gate_line = [ln for ln in src.splitlines() if "_assert_saas_tier_fit_http" in ln][0]
    assert "site_id=body.site_id" in gate_line
    assert "factory_id" not in gate_line


# ── B4-14 finalizer 는 runtime 성공 후에만 ──


def test_B4_14_finalizer_only_after_runtime_success(le_mod, monkeypatch):
    LE, client, _sb = le_mod
    log = _install_spies(monkeypatch, LE, gate_result=FIT, enabled=True)

    def boom(*_a, **_k):
        log.append(("runtime", None))
        raise LE.LegRuntimeError("rtm down")

    monkeypatch.setattr(LE, "run_safe_industrial_leg", boom)
    r = client.post(IND_PATH, json=IND_BODY)
    assert r.status_code == 502, r.text
    assert _count(log, "runtime") == 1
    assert _count(log, "finalize") == 0


def test_B4_14_upgrade_skips_finalizer(le_mod, monkeypatch):
    LE, client, _sb = le_mod
    log = _install_spies(monkeypatch, LE, gate_result=UPGRADE, enabled=True)
    r = client.post(BLD_PATH, json=BLD_BODY)
    assert r.status_code == 402
    assert _count(log, "finalize") == 0
    assert _count(log, "runtime") == 0


# ── 정적: B2 재사용 · formula/PLAN_MAP/rank dup 0 · step1 ungated ──


def test_static_reuses_evaluate_no_pricing_dup():
    src = ROUTER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    imports = [
        n for n in tree.body
        if isinstance(n, ast.ImportFrom) and n.module == "services.tier_payment_gate_svc"
    ]
    names = {a.name for n in imports for a in n.names}
    assert "evaluate_saas_tier_gate" in names
    assert "TierGateError" in names
    assert src.count("def _assert_saas_tier_fit_http") == 1
    for banned in (
        "criteria_min",
        "criteria_max",
        "PLAN_MAP",
        "price_master",
        "sort_order",
        "resolve_plan",
        "load_prices",
    ):
        assert banned not in src, banned


def test_static_step1_and_apply_ungated():
    import routers.legal_engine as LE

    for fn in (
        LE.diagnose_step1,
        LE.apply_legal_engine,
        LE.apply_legal_engine_from_quote,
    ):
        src = inspect.getsource(fn)
        assert "_assert_saas_tier_fit_http" not in src
        assert "evaluate_saas_tier_gate" not in src
