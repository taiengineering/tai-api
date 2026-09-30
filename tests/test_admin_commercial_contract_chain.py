"""AC-B01-AC-B24  Admin Commercial Contract Chain — WO-ADM-CONTRACT-01-FINAL.

FakeSupabase + real service functions. DB 없음. pricing engine 호출 없음.

케이스 매트릭스:
  AUTH     AC-B01 non-admin payments → 403
           AC-B02 non-admin contracts → 403
  GUARD    AC-B03 company_id exact filter payments
           AC-B04 company_id exact filter contracts
  FILTER   AC-B05 payments status_code filter
           AC-B06 contracts status_code filter
           AC-B07 payments quote_id filter
           AC-B08 payments contract_id filter
  BATCH    AC-B09 payment rows created_at DESC
           AC-B10 quote batch N+1=0 (payments)
           AC-B11 contract batch N+1=0 (payments)
  PROJ     AC-B12 cross-company quote → quote_ref_ok=False
           AC-B13 cross-company contract → contract_ref_ok=False
           AC-B14 missing quote_id → quote_ref_ok=False
           AC-B15 missing contract_id → contract_ref_ok=False
           AC-B16 null quote_id → quote_ref_ok=None
  CONTRACT AC-B17 contracts _CONTRACT_ADM_COLS includes quote_id
           AC-B18 contracts contract_id exact filter
           AC-B19 contracts quote_id filter
           AC-B20 contract quote batch N+1=0
           AC-B21 contract missing quote → quote_ref_ok=False
           AC-B22 contract null quote_id → quote_ref_ok=None
  STATIC   AC-B23 no write routes in admin_commercial router
           AC-B24 no v_payments_list in admin_commercial_svc
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

from services import admin_commercial_svc as svc


# ── FakeSupabase ──────────────────────────────────────────────────────────────

class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if data else 0)


class _Query:
    def __init__(self, store: dict, table: str, write_log: list, query_log: list):
        self._store = store
        self._table = table
        self._wl = write_log
        self._ql = query_log
        self._op = "select"
        self._filters: list = []
        self._in_filters: list = []
        self._count_exact = False
        self._order_col: str | None = None
        self._order_desc = False
        self._range: tuple | None = None

    def select(self, cols="*", *a, **kw):
        if kw.get("count") == "exact":
            self._count_exact = True
        return self

    def insert(self, row):
        self._op = "insert"; self._payload = row; return self

    def update(self, patch):
        self._op = "update"; self._payload = patch; return self

    def delete(self):
        self._op = "delete"; return self

    def eq(self, c, v):     self._filters.append(("eq", c, v)); return self
    def in_(self, c, vs):   self._in_filters.append((c, list(vs))); return self
    def range(self, s, e):  self._range = (s, e); return self

    def order(self, col, *, desc=False, **kw):
        self._order_col = col; self._order_desc = desc; return self

    def _match(self, row: dict) -> bool:
        for op, c, v in self._filters:
            rv = str(row.get(c, ""))
            if op == "eq" and rv != str(v):
                return False
        for c, vs in self._in_filters:
            rv = str(row.get(c, ""))
            if rv not in [str(x) for x in vs]:
                return False
        return True

    def execute(self) -> _Result:
        if self._op in ("insert", "update", "delete"):
            self._wl.append(self._op)
            return _Result([], 0)
        self._ql.append(self._table)
        rows = [r for r in (self._store.get(self._table) or []) if self._match(r)]
        if self._order_col:
            rows = sorted(rows, key=lambda r: r.get(self._order_col, ""),
                          reverse=self._order_desc)
        if self._range is not None:
            s, e = self._range
            rows = rows[s:e + 1]
        return _Result(rows, len(rows) if self._count_exact else None)


class FakeSB:
    def __init__(self, store: dict):
        self._store = store
        self.write_log: list = []
        self.query_log: list = []

    def table(self, name: str) -> _Query:
        return _Query(self._store, name, self.write_log, self.query_log)


def _now_iso(offset_days: int = 0) -> str:
    return (datetime.now(tz=timezone.utc) + timedelta(days=offset_days)).isoformat()


def _make_payment(company_id: str, quote_id=None, contract_id=None,
                  status_code: str = "SUCCESS") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "company_id": company_id,
        "quote_id": quote_id,
        "contract_id": contract_id,
        "plan_code": "SAAS_MANAGER_12M",
        "product_type": "SAAS",
        "payment_type": "INICIS_CARD",
        "total_amount": 1320000,
        "supply_amount": 1200000,
        "vat_amount": 120000,
        "status_code": status_code,
        "service_status": "ACTIVE",
        "pg_method": "Card",
        "period_months": 12,
        "paid_at": _now_iso(-5),
        "created_at": _now_iso(-5),
    }


def _make_quote(company_id: str, quote_no: str = "QUO-TEST") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "quote_no": quote_no,
        "company_id": company_id,
        "status_code": "ISSUED",
        "created_at": _now_iso(-10),
    }


def _make_contract(company_id: str, quote_id=None,
                   status_code: str = "ACTIVE") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "contract_no": f"CON-{uuid.uuid4().hex[:6].upper()}",
        "company_id": company_id,
        "quote_id": quote_id,
        "service_type": "SAAS",
        "status_code": status_code,
        "start_date": _now_iso(-30),
        "end_date": _now_iso(335),
        "contract_amount": 1200000,
        "vat_amount": 120000,
        "total_amount": 1320000,
        "paid_amount": 1320000,
        "paid_at": _now_iso(-5),
        "is_active": True,
        "created_at": _now_iso(-5),
    }


# ── AUTH ─────────────────────────────────────────────────────────────────────

def test_ac_b01_non_admin_payments_403():
    """AC-B01: non-admin → _require_admin 403."""
    from fastapi import HTTPException
    from services.company_scope import _require_admin
    non_admin = {"user_id": "u-99", "company_id": "co-99", "role_code": "010"}
    with pytest.raises(HTTPException) as exc:
        _require_admin(non_admin, FakeSB({}))
    assert exc.value.status_code == 403


def test_ac_b02_non_admin_contracts_403():
    """AC-B02: same gate for contracts."""
    from fastapi import HTTPException
    from services.company_scope import _require_admin
    non_admin = {"user_id": "u-99", "company_id": "co-99", "role_code": "010"}
    with pytest.raises(HTTPException) as exc:
        _require_admin(non_admin, FakeSB({}))
    assert exc.value.status_code == 403


# ── GUARD ─────────────────────────────────────────────────────────────────────

def test_ac_b03_payments_company_id_exact():
    """AC-B03: company_id exact filter — other company excluded."""
    co_a = str(uuid.uuid4())
    co_b = str(uuid.uuid4())
    pay_a = _make_payment(co_a)
    pay_b = _make_payment(co_b)
    sb = FakeSB({"payments": [pay_a, pay_b]})
    result = svc.list_payments_admin(sb, co_a)
    ids = [r["id"] for r in result["items"]]
    assert pay_a["id"] in ids and pay_b["id"] not in ids


def test_ac_b04_contracts_company_id_exact():
    """AC-B04: contracts company_id exact filter."""
    co_a = str(uuid.uuid4())
    co_b = str(uuid.uuid4())
    ct_a = _make_contract(co_a)
    ct_b = _make_contract(co_b)
    sb = FakeSB({"contracts": [ct_a, ct_b]})
    result = svc.list_contracts_admin(sb, co_a)
    ids = [r["id"] for r in result["items"]]
    assert ct_a["id"] in ids and ct_b["id"] not in ids


# ── FILTER ────────────────────────────────────────────────────────────────────

def test_ac_b05_payments_status_code_filter():
    """AC-B05: status_code filter — non-matching excluded."""
    co = str(uuid.uuid4())
    p_ok = _make_payment(co, status_code="SUCCESS")
    p_fail = _make_payment(co, status_code="FAILED")
    sb = FakeSB({"payments": [p_ok, p_fail]})
    result = svc.list_payments_admin(sb, co, status_code="SUCCESS")
    ids = [r["id"] for r in result["items"]]
    assert p_ok["id"] in ids and p_fail["id"] not in ids


def test_ac_b06_contracts_status_code_filter():
    """AC-B06: contracts status_code filter."""
    co = str(uuid.uuid4())
    ct_active = _make_contract(co, status_code="ACTIVE")
    ct_cancelled = _make_contract(co, status_code="CANCELLED")
    sb = FakeSB({"contracts": [ct_active, ct_cancelled]})
    result = svc.list_contracts_admin(sb, co, status_code="ACTIVE")
    ids = [r["id"] for r in result["items"]]
    assert ct_active["id"] in ids and ct_cancelled["id"] not in ids


def test_ac_b07_payments_quote_id_filter():
    """AC-B07: payments quote_id exact filter."""
    co = str(uuid.uuid4())
    q = _make_quote(co)
    pay_with = _make_payment(co, quote_id=q["id"])
    pay_without = _make_payment(co, quote_id=None)
    sb = FakeSB({"payments": [pay_with, pay_without], "quotes": [q]})
    result = svc.list_payments_admin(sb, co, quote_id=q["id"])
    ids = [r["id"] for r in result["items"]]
    assert pay_with["id"] in ids and pay_without["id"] not in ids


def test_ac_b08_payments_contract_id_filter():
    """AC-B08: payments contract_id exact filter."""
    co = str(uuid.uuid4())
    ct = _make_contract(co)
    pay_with = _make_payment(co, contract_id=ct["id"])
    pay_without = _make_payment(co, contract_id=None)
    sb = FakeSB({"payments": [pay_with, pay_without], "contracts": [ct]})
    result = svc.list_payments_admin(sb, co, contract_id=ct["id"])
    ids = [r["id"] for r in result["items"]]
    assert pay_with["id"] in ids and pay_without["id"] not in ids


# ── BATCH / N+1 ───────────────────────────────────────────────────────────────

def test_ac_b09_payments_created_at_desc():
    """AC-B09: payments ordered DESC by created_at."""
    co = str(uuid.uuid4())
    old = _make_payment(co); old["created_at"] = _now_iso(-10)
    new = _make_payment(co); new["created_at"] = _now_iso(-1)
    sb = FakeSB({"payments": [old, new]})
    result = svc.list_payments_admin(sb, co)
    dates = [r["created_at"] for r in result["items"]]
    assert dates == sorted(dates, reverse=True)


def test_ac_b10_quote_batch_n1_zero():
    """AC-B10: quote batch lookup = exactly 1 query for N payments with distinct quote_ids."""
    co = str(uuid.uuid4())
    q1 = _make_quote(co, "QUO-001")
    q2 = _make_quote(co, "QUO-002")
    pay1 = _make_payment(co, quote_id=q1["id"])
    pay2 = _make_payment(co, quote_id=q2["id"])
    sb = FakeSB({"payments": [pay1, pay2], "quotes": [q1, q2]})
    svc.list_payments_admin(sb, co)
    # payments(1) + quotes(1) = 2 total, NOT payments(1) + quotes(2) = 3
    quote_queries = [t for t in sb.query_log if t == "quotes"]
    assert len(quote_queries) <= 1, f"N+1 violation: {len(quote_queries)} quote queries for 2 payments"


def test_ac_b11_contract_batch_n1_zero():
    """AC-B11: contract batch lookup = exactly 1 query for N payments."""
    co = str(uuid.uuid4())
    ct1 = _make_contract(co); ct2 = _make_contract(co)
    pay1 = _make_payment(co, contract_id=ct1["id"])
    pay2 = _make_payment(co, contract_id=ct2["id"])
    sb = FakeSB({"payments": [pay1, pay2], "contracts": [ct1, ct2]})
    svc.list_payments_admin(sb, co)
    contract_queries = [t for t in sb.query_log if t == "contracts"]
    assert len(contract_queries) <= 1, f"N+1 violation: {len(contract_queries)} contract queries"


# ── PROJECTION ────────────────────────────────────────────────────────────────

def test_ac_b12_cross_company_quote_ref_false():
    """AC-B12: cross-company quote FK → quote_ref_ok=False, no quote_no exposure."""
    co_a = str(uuid.uuid4())
    co_b = str(uuid.uuid4())
    q = _make_quote(co_b, "QUO-OTHER")  # belongs to co_b
    pay = _make_payment(co_a, quote_id=q["id"])  # payment belongs to co_a
    sb = FakeSB({"payments": [pay], "quotes": [q]})
    result = svc.list_payments_admin(sb, co_a)
    row = result["items"][0]
    assert row["quote_ref_ok"] is False, "cross-company quote must be ref_ok=False"
    assert row["quote_no"] is None, "cross-company quote_no must not be exposed"


def test_ac_b13_cross_company_contract_ref_false():
    """AC-B13: cross-company contract FK → contract_ref_ok=False."""
    co_a = str(uuid.uuid4())
    co_b = str(uuid.uuid4())
    ct = _make_contract(co_b)  # belongs to co_b
    pay = _make_payment(co_a, contract_id=ct["id"])
    sb = FakeSB({"payments": [pay], "contracts": [ct]})
    result = svc.list_payments_admin(sb, co_a)
    row = result["items"][0]
    assert row["contract_ref_ok"] is False
    assert row["contract_no"] is None


def test_ac_b14_missing_quote_ref_false():
    """AC-B14: payment quote_id set but quote not found → quote_ref_ok=False."""
    co = str(uuid.uuid4())
    pay = _make_payment(co, quote_id=str(uuid.uuid4()))  # non-existent quote
    sb = FakeSB({"payments": [pay], "quotes": []})
    result = svc.list_payments_admin(sb, co)
    assert result["items"][0]["quote_ref_ok"] is False


def test_ac_b15_missing_contract_ref_false():
    """AC-B15: payment contract_id set but contract not found → contract_ref_ok=False."""
    co = str(uuid.uuid4())
    pay = _make_payment(co, contract_id=str(uuid.uuid4()))
    sb = FakeSB({"payments": [pay], "contracts": []})
    result = svc.list_payments_admin(sb, co)
    assert result["items"][0]["contract_ref_ok"] is False


def test_ac_b16_null_quote_id_ref_none():
    """AC-B16: null quote_id → quote_ref_ok=None (not False)."""
    co = str(uuid.uuid4())
    pay = _make_payment(co, quote_id=None)
    sb = FakeSB({"payments": [pay]})
    result = svc.list_payments_admin(sb, co)
    assert result["items"][0]["quote_ref_ok"] is None
    assert result["items"][0]["quote_no"] is None


# ── CONTRACTS ─────────────────────────────────────────────────────────────────

def test_ac_b17_contract_cols_include_quote_id():
    """AC-B17: _CONTRACT_ADM_COLS includes quote_id."""
    assert "quote_id" in svc._CONTRACT_ADM_COLS, \
        "_CONTRACT_ADM_COLS must include quote_id for Contract→Quote chain"


def test_ac_b18_contracts_contract_id_exact_filter():
    """AC-B18: contracts contract_id exact filter."""
    co = str(uuid.uuid4())
    ct_a = _make_contract(co)
    ct_b = _make_contract(co)
    sb = FakeSB({"contracts": [ct_a, ct_b]})
    result = svc.list_contracts_admin(sb, co, contract_id=ct_a["id"])
    ids = [r["id"] for r in result["items"]]
    assert ct_a["id"] in ids and ct_b["id"] not in ids


def test_ac_b19_contracts_quote_id_filter():
    """AC-B19: contracts quote_id filter — contracts without matching quote_id excluded."""
    co = str(uuid.uuid4())
    q = _make_quote(co)
    ct_with = _make_contract(co, quote_id=q["id"])
    ct_without = _make_contract(co, quote_id=None)
    sb = FakeSB({"contracts": [ct_with, ct_without], "quotes": [q]})
    result = svc.list_contracts_admin(sb, co, quote_id=q["id"])
    ids = [r["id"] for r in result["items"]]
    assert ct_with["id"] in ids and ct_without["id"] not in ids


def test_ac_b20_contract_quote_batch_n1_zero():
    """AC-B20: contract quote batch = 1 query for N contracts."""
    co = str(uuid.uuid4())
    q1 = _make_quote(co, "QUO-A")
    q2 = _make_quote(co, "QUO-B")
    ct1 = _make_contract(co, quote_id=q1["id"])
    ct2 = _make_contract(co, quote_id=q2["id"])
    sb = FakeSB({"contracts": [ct1, ct2], "quotes": [q1, q2]})
    svc.list_contracts_admin(sb, co)
    quote_queries = [t for t in sb.query_log if t == "quotes"]
    assert len(quote_queries) <= 1, f"N+1 violation: {len(quote_queries)} quote queries"


def test_ac_b21_contract_missing_quote_ref_false():
    """AC-B21: contract quote_id set but quote not found → quote_ref_ok=False."""
    co = str(uuid.uuid4())
    ct = _make_contract(co, quote_id=str(uuid.uuid4()))
    sb = FakeSB({"contracts": [ct], "quotes": []})
    result = svc.list_contracts_admin(sb, co)
    assert result["items"][0]["quote_ref_ok"] is False


def test_ac_b22_contract_null_quote_id_ref_none():
    """AC-B22: contract null quote_id → quote_ref_ok=None."""
    co = str(uuid.uuid4())
    ct = _make_contract(co, quote_id=None)
    sb = FakeSB({"contracts": [ct]})
    result = svc.list_contracts_admin(sb, co)
    assert result["items"][0]["quote_ref_ok"] is None


# ── STATIC ────────────────────────────────────────────────────────────────────

def test_ac_b23_no_write_routes():
    """AC-B23: admin_commercial router POST/PUT/PATCH/DELETE = 0."""
    import inspect
    import routers.admin_commercial as mod
    src = inspect.getsource(mod)
    for method in ("router.post", "router.put", "router.patch", "router.delete"):
        assert method not in src, f"mutation route found: {method}"


def test_ac_b24_no_v_payments_list():
    """AC-B24: admin_commercial_svc .table('v_payments_list') = 0."""
    import inspect
    import re
    import services.admin_commercial_svc as mod
    src = inspect.getsource(mod)
    assert not re.search(r'\.table\(["\']v_payments_list["\']', src)
