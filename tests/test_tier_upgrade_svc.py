"""WO-COMMON-TIER-PAYMENT-GATE-MODULARIZE-001 / B3.

tier upgrade prepare + idempotent writer. 실 INICIS 0 · prod DB apply 0.
"""
from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest

from schemas.payment import UpgradePrepareBody
from services.payment_helpers import add_vat
from services.tier_upgrade_svc import (
    TierUpgradeError,
    apply_saas_tier_upgrade,
    prepare_saas_tier_upgrade,
)
import services.tier_upgrade_svc as upgrade_svc
import services.payment_post_process as pp

CO_OWN = "co-own"
FAC_IND = "fac-ind"
USER = "11111111-1111-1111-1111-111111111111"
CALLER = {
    "id": USER,
    "company_id": CO_OWN,
    "factory_id": FAC_IND,
    "role_code": "011",
}
SVC_PATH = Path(__file__).resolve().parents[1] / "services" / "tier_upgrade_svc.py"
CURRENT_SUPPLY = 149000
TARGET_SUPPLY = 299000
DELTA_SUPPLY = 150000
DELTA_VAT = 15000
DELTA_TOTAL = 165000
TARGET_VAT = 29900
TARGET_TOTAL = 328900


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
        self._payload = None

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
        return self

    def order(self, col, **_k):
        self._order_col = col
        return self

    def limit(self, n):
        self._limit = n
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def upsert(self, payload):
        self._op = "upsert"
        self._payload = payload
        return self

    def _match(self, row):
        for kind, col, val in self._filters:
            if kind == "eq" and row.get(col) != val:
                return False
            if kind == "in" and row.get(col) not in val:
                return False
        return True

    def execute(self):
        store = self._sb.store.setdefault(self._table, [])
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            out = []
            for it in items:
                row = dict(it)
                row.setdefault("id", str(uuid.uuid4()))
                store.append(row)
                self._sb.writes.append(("insert", self._table, dict(row)))
                out.append(dict(row))
            return _FakeResponse(out)
        if self._op == "update":
            matched = []
            for row in store:
                if self._match(row):
                    row.update(self._payload or {})
                    matched.append(dict(row))
            self._sb.writes.append(("update", self._table, dict(self._payload or {})))
            return _FakeResponse(matched)
        if self._op in ("delete", "upsert"):
            self._sb.writes.append((self._op, self._table, self._payload))
            return _FakeResponse([])
        rows = [dict(r) for r in store if self._match(r)]
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


def _pm(pid, sector, tier, sort_order, cmin, cmax, amount, **extra):
    row = {
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
    row.update(extra)
    return row


def _base_store(*, employees=80, plan="INDUSTRY_BUSINESS", with_sub=True):
    start, end = "2026-01-01", "2026-12-31"
    current_total = add_vat(CURRENT_SUPPLY)
    store = {
        "role_data_scope": [{"role_code": "011", "scope_type": "COMPANY"}],
        "factories": [
            {
                "id": FAC_IND,
                "company_id": CO_OWN,
                "employee_count": employees,
                "building_area": 500,
            }
        ],
        "construction_sites": [],
        "contracts": [
            {
                "id": "ct-ind",
                "company_id": CO_OWN,
                "plan_code": plan,
                "service_type": "SAAS",
                "status_code": "ACTIVE",
                "is_active": True,
                "start_date": start,
                "end_date": end,
                "contract_amount": CURRENT_SUPPLY,
                "vat_amount": add_vat(CURRENT_SUPPLY) - CURRENT_SUPPLY,
                "total_amount": current_total,
                "paid_amount": current_total,
            }
        ],
        "price_master": [
            _pm("ind-s", "INDUSTRY", "INDUSTRY_STARTER", 1, 0, 50, 99000),
            _pm("ind-m", "INDUSTRY", "INDUSTRY_BUSINESS", 2, 0, 50, CURRENT_SUPPLY),
            _pm("ind-l", "INDUSTRY", "INDUSTRY_PRO", 3, 50, 300, TARGET_SUPPLY),
            _pm("ind-c", "INDUSTRY", "INDUSTRY_CUSTOM", 4, 300, 1000000, 0),
        ],
        "price_service_feature": [],
        "payments": [],
        "saas_tier_upgrade_transitions": [],
        "subscriptions": [],
        "users": [{"id": USER, "company_id": CO_OWN, "name": "테스터", "phone": None, "email": None}],
        "companies": [{"id": CO_OWN, "name": "Own Co"}],
    }
    if with_sub:
        store["subscriptions"].append(
            {
                "id": "sub-1",
                "company_id": CO_OWN,
                "plan_code": "INDUSTRY_BUSINESS",
                "plan_name": "INDUSTRY_BUSINESS",
                "amount": current_total,
                "supply_amount": CURRENT_SUPPLY,
                "vat_amount": current_total - CURRENT_SUPPLY,
                "billing_cycle": "monthly",
                "status": "ACTIVE",
            }
        )
    return store


@pytest.fixture
def store():
    return _base_store()


@pytest.fixture
def sb(store):
    return _FakeSB(store)


@pytest.fixture
def patch_prepare_sb(sb, monkeypatch):
    monkeypatch.setattr("services.payment_svc.get_supabase", lambda: sb)
    return sb


def _prepare(sb, **kw):
    kw.setdefault("factory_id", FAC_IND)
    return prepare_saas_tier_upgrade(sb, CALLER, **kw)


def test_b3_2_normal_delta(patch_prepare_sb, store):
    sb = patch_prepare_sb
    out = _prepare(sb)
    assert out["status"] == "success"
    pay = sb.store["payments"][0]
    assert pay["supply_amount"] == DELTA_SUPPLY
    assert pay["vat_amount"] == DELTA_VAT
    assert pay["total_amount"] == DELTA_TOTAL
    assert pay["payment_type"] == "UPGRADE"
    assert pay["plan_code"] == "INDUSTRY_PRO"
    tr = sb.store["saas_tier_upgrade_transitions"][0]
    assert tr["target_supply_amount"] == TARGET_SUPPLY
    assert tr["target_total_amount"] == TARGET_TOTAL
    assert tr["delta_supply_amount"] == DELTA_SUPPLY
    assert tr["delta_vat_amount"] == DELTA_VAT
    assert tr["delta_total_amount"] == DELTA_TOTAL
    assert tr["status"] == "PREPARED"
    assert out["upgrade"]["target_total_amount"] == TARGET_TOTAL


def test_b3_1_client_amount_ignored(patch_prepare_sb):
    body = UpgradePrepareBody.model_validate(
        {
            "factory_id": FAC_IND,
            "amount": 1,
            "delta_amount": 2,
            "plan_code": "HACK",
            "current_plan": "HACK",
            "target_plan": "HACK",
            "sector": "CONSTRUCTION",
            "contract_id": "nope",
            "company_id": "nope",
            "subscription_id": "nope",
        }
    )
    dumped = body.model_dump()
    for k in (
        "amount",
        "delta_amount",
        "plan_code",
        "current_plan",
        "target_plan",
        "sector",
        "contract_id",
        "company_id",
        "subscription_id",
    ):
        assert k not in dumped
    out = _prepare(patch_prepare_sb, factory_id=body.factory_id)
    pay = patch_prepare_sb.store["payments"][0]
    assert pay["supply_amount"] == DELTA_SUPPLY
    assert pay["plan_code"] == "INDUSTRY_PRO"


def test_b3_3_custom_manual_quote_no_payment(patch_prepare_sb, store):
    store["factories"][0]["employee_count"] = 400
    with pytest.raises(TierUpgradeError) as ei:
        _prepare(patch_prepare_sb)
    assert ei.value.code == "MANUAL_QUOTE_REQUIRED"
    assert store["payments"] == []
    assert store["saas_tier_upgrade_transitions"] == []


def test_b3_4_fit_already_no_payment(patch_prepare_sb, store):
    store["factories"][0]["employee_count"] = 10
    store["contracts"][0]["plan_code"] = "INDUSTRY_PRO"
    with pytest.raises(TierUpgradeError) as ei:
        _prepare(patch_prepare_sb)
    assert ei.value.code == "ALREADY_FIT"
    assert store["payments"] == []
    assert store["saas_tier_upgrade_transitions"] == []


def test_b3_10_downgrade_or_non_increase_no_mutation(patch_prepare_sb, store):
    store["factories"][0]["employee_count"] = 10
    store["contracts"][0]["plan_code"] = "INDUSTRY_PRO"
    with pytest.raises(TierUpgradeError) as ei:
        _prepare(patch_prepare_sb)
    assert ei.value.code == "ALREADY_FIT"
    assert not any(w[0] == "insert" and w[1] == "payments" for w in patch_prepare_sb.writes)


def test_b3_9_ambiguous_subscription_no_payment(patch_prepare_sb, store):
    store["subscriptions"].append(
        {
            "id": "sub-2",
            "company_id": CO_OWN,
            "plan_code": "INDUSTRY_BUSINESS",
            "plan_name": "x",
            "amount": 1,
            "supply_amount": 1,
            "vat_amount": 0,
            "billing_cycle": "monthly",
            "status": "ACTIVE",
        }
    )
    with pytest.raises(TierUpgradeError) as ei:
        _prepare(patch_prepare_sb)
    assert ei.value.code == "AMBIGUOUS_ACTIVE_SUBSCRIPTION"
    assert store["payments"] == []


def _paid_upgrade(sb):
    out = _prepare(sb)
    pay = sb.store["payments"][0]
    pay["status_code"] = "PAID"
    pay["paid_at"] = "2026-09-10T00:00:00+09:00"
    return pay


def test_b3_5_idempotent_writer(patch_prepare_sb, store):
    sb = patch_prepare_sb
    pay = _paid_upgrade(sb)
    r1 = apply_saas_tier_upgrade(pay["id"], sb)
    r2 = apply_saas_tier_upgrade(pay["id"], sb)
    assert r1["status"] == "APPLIED" and r1["noop"] is False
    assert r2["status"] == "APPLIED" and r2["noop"] is True
    ct = store["contracts"][0]
    assert ct["plan_code"] == "INDUSTRY_PRO"
    assert ct["contract_amount"] == TARGET_SUPPLY
    assert ct["total_amount"] == TARGET_TOTAL
    assert ct["paid_amount"] == DELTA_TOTAL
    assert len(store["contracts"]) == 1
    trs = [t for t in store["saas_tier_upgrade_transitions"] if t["status"] == "APPLIED"]
    assert len(trs) == 1
    sub_updates = [w for w in sb.writes if w[0] == "update" and w[1] == "subscriptions"]
    assert len(sub_updates) == 1


def test_b3_6_dates_preserved(patch_prepare_sb, store):
    pay = _paid_upgrade(patch_prepare_sb)
    apply_saas_tier_upgrade(pay["id"], patch_prepare_sb)
    ct = store["contracts"][0]
    assert ct["start_date"] == "2026-01-01"
    assert ct["end_date"] == "2026-12-31"


def test_b3_7_subscription_full_not_delta(patch_prepare_sb, store):
    pay = _paid_upgrade(patch_prepare_sb)
    apply_saas_tier_upgrade(pay["id"], patch_prepare_sb)
    sub = store["subscriptions"][0]
    assert sub["amount"] == TARGET_TOTAL
    assert sub["amount"] != DELTA_TOTAL
    assert sub["supply_amount"] == TARGET_SUPPLY
    assert sub["vat_amount"] == TARGET_VAT
    assert sub["plan_code"] == "INDUSTRY_PRO"
    assert sub["billing_cycle"] == "monthly"


def test_b3_8_no_subscription_no_insert(monkeypatch):
    store = _base_store(with_sub=False)
    sb = _FakeSB(store)
    monkeypatch.setattr("services.payment_svc.get_supabase", lambda: sb)
    pay = _paid_upgrade(sb)
    apply_saas_tier_upgrade(pay["id"], sb)
    assert store["subscriptions"] == []
    assert not any(w[0] == "insert" and w[1] == "subscriptions" for w in sb.writes)
    assert store["contracts"][0]["plan_code"] == "INDUSTRY_PRO"


def test_b3_12_partial_failure_retry(patch_prepare_sb, store):
    sb = patch_prepare_sb
    pay = _paid_upgrade(sb)
    pay["status_code"] = "PAID"
    boom = {"n": 0}
    real = upgrade_svc._apply_contract

    def once(sb_, tr, pay_):
        boom["n"] += 1
        if boom["n"] == 1:
            raise RuntimeError("injected-fail")
        return real(sb_, tr, pay_)

    upgrade_svc._apply_contract = once
    try:
        r1 = apply_saas_tier_upgrade(pay["id"], sb)
        assert r1["status"] == "APPLY_FAILED"
        assert pay["status_code"] == "PAID"
        tr = store["saas_tier_upgrade_transitions"][0]
        assert tr["status"] == "APPLY_FAILED"
        assert tr["last_error"]
        r2 = apply_saas_tier_upgrade(pay["id"], sb)
        assert r2["status"] == "APPLIED"
        ct = store["contracts"][0]
        assert ct["plan_code"] == "INDUSTRY_PRO"
        assert ct["total_amount"] == TARGET_TOTAL
        assert ct["paid_amount"] == DELTA_TOTAL
        assert ct["start_date"] == "2026-01-01"
        assert pay["status_code"] == "PAID"
    finally:
        upgrade_svc._apply_contract = real


def test_b3_11_postprocess_upgrade_bypasses_contract_writers(patch_prepare_sb, store, monkeypatch):
    sb = patch_prepare_sb
    pay = _paid_upgrade(sb)
    calls = {"apply": 0, "act": 0, "ren": 0, "new": 0}

    def apply_spy(payment_id, supabase=None):
        calls["apply"] += 1
        return {"status": "APPLIED"}

    monkeypatch.setattr(pp, "get_supabase", lambda: sb)
    monkeypatch.setattr(pp, "_bootstrap_buyer_company_admin", lambda *a, **k: None)
    monkeypatch.setattr(pp, "_fire_automation", lambda *a, **k: None)
    monkeypatch.setattr(pp, "send_payment_notification", lambda *a, **k: None)
    monkeypatch.setattr(pp, "_activate_existing_contract", lambda *a, **k: calls.__setitem__("act", calls["act"] + 1))
    monkeypatch.setattr(pp, "_extend_contract_for_renewal", lambda *a, **k: calls.__setitem__("ren", calls["ren"] + 1))
    monkeypatch.setattr(pp, "_create_contract_from_payment", lambda *a, **k: calls.__setitem__("new", calls["new"] + 1) or "x")
    monkeypatch.setattr("services.tier_upgrade_svc.apply_saas_tier_upgrade", apply_spy)
    monkeypatch.setattr(upgrade_svc, "apply_saas_tier_upgrade", apply_spy)
    pp.on_payment_success_sync(pay["id"])
    assert calls["apply"] == 1
    assert calls["act"] == 0
    assert calls["ren"] == 0
    assert calls["new"] == 0


def test_c1_1_migration_enables_rls_without_policies():
    src = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "2026-09-10_saas_tier_upgrade_transitions.sql"
    ).read_text()
    assert "ENABLE ROW LEVEL SECURITY" in src
    assert "CREATE POLICY" not in src.upper()


def test_c1_2_transition_persist_fail_marks_payment_failed(patch_prepare_sb):
    sb = patch_prepare_sb
    real_table = sb.table

    def table(name):
        q = real_table(name)
        if name == "saas_tier_upgrade_transitions":
            q.insert = lambda payload: (_ for _ in ()).throw(RuntimeError("insert-fail"))
        return q

    sb.table = table
    with pytest.raises(TierUpgradeError) as ei:
        _prepare(sb)
    assert ei.value.code == "TRANSITION_PERSIST_FAILED"
    pays = [w for w in sb.writes if w[0] == "insert" and w[1] == "payments"]
    assert len(pays) == 1
    pay_id = pays[0][2]["id"]
    row = next(p for p in sb.store["payments"] if p["id"] == pay_id)
    assert row["status_code"] == "FAILED"
    assert row["fail_reason"] == "TIER_UPGRADE_TRANSITION_PERSIST_FAILED"
    failed_updates = [
        w for w in sb.writes
        if w[0] == "update" and w[1] == "payments" and w[2].get("status_code") == "FAILED"
    ]
    assert len(failed_updates) == 1
    assert sb.store["saas_tier_upgrade_transitions"] == []


def test_c1_3_cleanup_failure_preserves_transition_persist_error(patch_prepare_sb):
    sb = patch_prepare_sb
    real_table = sb.table

    def table(name):
        q = real_table(name)
        if name == "saas_tier_upgrade_transitions":
            q.insert = lambda payload: (_ for _ in ()).throw(RuntimeError("insert-fail"))
        if name == "payments":
            orig_update = q.update

            def boom_update(payload):
                if payload.get("status_code") == "FAILED":
                    raise RuntimeError("cleanup-fail")
                return orig_update(payload)

            q.update = boom_update
        return q

    sb.table = table
    with pytest.raises(TierUpgradeError) as ei:
        _prepare(sb)
    assert ei.value.code == "TRANSITION_PERSIST_FAILED"
    assert "cleanup-fail" not in ei.value.message
    assert "cleanup-fail" not in str(ei.value)


def _postprocess_upgrade_notif(monkeypatch, sb, apply_status):
    pay = _paid_upgrade(sb)
    notif = {"n": 0}

    def apply_spy(payment_id, supabase=None):
        return {"status": apply_status}

    monkeypatch.setattr(pp, "get_supabase", lambda: sb)
    monkeypatch.setattr(pp, "_bootstrap_buyer_company_admin", lambda *a, **k: None)
    monkeypatch.setattr(pp, "_fire_automation", lambda *a, **k: None)
    monkeypatch.setattr(pp, "send_payment_notification", lambda *a, **k: notif.__setitem__("n", notif["n"] + 1))
    monkeypatch.setattr("services.tier_upgrade_svc.apply_saas_tier_upgrade", apply_spy)
    pp.on_payment_success_sync(pay["id"])
    return notif["n"], pay


def test_c1_4_applied_sends_notification(patch_prepare_sb, monkeypatch):
    n, pay = _postprocess_upgrade_notif(monkeypatch, patch_prepare_sb, "APPLIED")
    assert n == 1
    assert pay["status_code"] == "PAID"


def test_c1_5_apply_failed_skips_notification(patch_prepare_sb, monkeypatch):
    n, pay = _postprocess_upgrade_notif(monkeypatch, patch_prepare_sb, "APPLY_FAILED")
    assert n == 0
    assert pay["status_code"] == "PAID"


def test_c1_6_skip_skips_notification(patch_prepare_sb, monkeypatch):
    n, pay = _postprocess_upgrade_notif(monkeypatch, patch_prepare_sb, "SKIP")
    assert n == 0
    assert pay["status_code"] == "PAID"


def test_static_schema_and_source_guards():
    fields = set(UpgradePrepareBody.model_fields)
    forbidden = {
        "amount",
        "delta_amount",
        "plan_code",
        "current_plan",
        "target_plan",
        "sector",
        "sort_order",
        "contract_id",
        "company_id",
        "subscription_id",
    }
    assert forbidden.isdisjoint(fields)
    src = SVC_PATH.read_text()
    tree = ast.parse(src)
    imported = []
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        if isinstance(node, ast.Name):
            names.append(node.id)
        if isinstance(node, ast.Attribute):
            names.append(node.attr)
    assert "PLAN_MAP" not in names
    assert "help_plan_level" not in imported
    assert "payment_post_process" not in imported
    assert "run_billing_prepare" not in names
    assert "run_billing_charge" not in names
    assert "paid_amount +" not in src
    assert r"_V\d+" not in src
    assert "PLAN_LEVELS" not in names
    assert "resolve_saas_tier_gate_context" in names
    assert "add_vat" in names


def test_static_no_fastapi_in_upgrade_svc():
    src = SVC_PATH.read_text()
    assert "from fastapi" not in src
    assert "HTTPException" not in src


try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import httpx  # noqa: F401

    _HAS_CLIENT = True
except Exception:  # noqa: BLE001
    _HAS_CLIENT = False

requires_client = pytest.mark.skipif(not _HAS_CLIENT, reason="httpx/TestClient 미설치")


@requires_client
def test_router_b3_1_injected_body_ignored(patch_prepare_sb, monkeypatch):
    import routers.payment as pay_mod

    monkeypatch.setattr(pay_mod, "get_supabase", lambda: patch_prepare_sb)
    monkeypatch.setattr(pay_mod, "get_current_user", lambda authorization=None: CALLER)
    app = FastAPI()
    app.include_router(pay_mod.router)
    with TestClient(app) as c:
        r = c.post(
            "/payments/tier-upgrade/prepare",
            json={
                "factory_id": FAC_IND,
                "amount": 1,
                "plan_code": "HACK",
                "sector": "CONSTRUCTION",
                "contract_id": "nope",
            },
        )
    assert r.status_code == 200
    pay = patch_prepare_sb.store["payments"][0]
    assert pay["supply_amount"] == DELTA_SUPPLY
    assert pay["plan_code"] == "INDUSTRY_PRO"


@requires_client
def test_router_b3_4_already_fit_409(monkeypatch):
    store = _base_store(employees=10, plan="INDUSTRY_PRO")
    sb = _FakeSB(store)
    monkeypatch.setattr("services.payment_svc.get_supabase", lambda: sb)
    import routers.payment as pay_mod

    monkeypatch.setattr(pay_mod, "get_supabase", lambda: sb)
    monkeypatch.setattr(pay_mod, "get_current_user", lambda authorization=None: CALLER)
    app = FastAPI()
    app.include_router(pay_mod.router)
    with TestClient(app) as c:
        r = c.post("/payments/tier-upgrade/prepare", json={"factory_id": FAC_IND})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ALREADY_FIT"
    assert store["payments"] == []
