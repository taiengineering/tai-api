"""CT-BE01-CT-BE15  Admin Commercial Contract Chain tests — WO-ADM-CONTRACT-01.

FakeSupabase + real service functions. DB 없음.

케이스 매트릭스:
  AUTH     CT-BE01 non-admin payments → 403
           CT-BE02 non-admin contracts → 403
  PAYMENTS CT-BE03 company_id exact filter — other company excluded
           CT-BE04 quote_id field returned in payment row
           CT-BE05 contract_id field returned in payment row
           CT-BE06 company_id field returned in payment row
           CT-BE07 DB write = 0
           CT-BE08 created_at DESC ordering
  CONTRACTS CT-BE09 company_id exact filter — other company excluded
           CT-BE10 contract_no field returned in contract row
           CT-BE11 company_id field returned in contract row
           CT-BE12 DB write = 0
           CT-BE13 created_at DESC ordering
  STATIC   CT-BE14 no write routes in admin_commercial router
           CT-BE15 no v_payments_list usage in admin_commercial_svc
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

from services import admin_commercial_svc as svc


# ── FakeSupabase (reusable pattern from test_admin_commercial_read) ──────────

class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if data else 0)


class _Query:
    def __init__(self, store: dict, table: str, write_log: list):
        self._store = store
        self._table = table
        self._wl = write_log
        self._op = "select"
        self._filters: list = []
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

    def eq(self, c, v):    self._filters.append(("eq", c, v)); return self
    def range(self, s, e): self._range = (s, e); return self

    def order(self, col, *, desc=False, **kw):
        self._order_col = col; self._order_desc = desc; return self

    def _match(self, row: dict) -> bool:
        for op, c, v in self._filters:
            rv = str(row.get(c, ""))
            if op == "eq" and rv != str(v):
                return False
        return True

    def execute(self) -> _Result:
        if self._op in ("insert", "update", "delete"):
            self._wl.append(self._op)
            return _Result([], 0)
        rows = [r for r in (self._store.get(self._table) or []) if self._match(r)]
        if self._order_col:
            rows = sorted(rows, key=lambda r: r.get(self._order_col, ""),
                          reverse=self._order_desc)
        if self._range is not None:
            s, e = self._range
            rows = rows[s:e + 1]
        total = len(rows)
        return _Result(rows, total if self._count_exact else None)


class FakeSB:
    def __init__(self, store: dict):
        self._store = store
        self.write_log: list = []

    def table(self, name: str) -> _Query:
        return _Query(self._store, name, self.write_log)


def _admin_user():
    return {"user_id": "admin-001", "company_id": None, "role_code": "001"}


def _non_admin_user():
    return {"user_id": "user-999", "company_id": "co-999", "role_code": "010"}


def _now_iso(offset_days: int = 0) -> str:
    from datetime import timezone
    return (datetime.now(tz=timezone.utc) + timedelta(days=offset_days)).isoformat()


def _make_payment(company_id: str, quote_id: str | None = None,
                  contract_id: str | None = None) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "company_id": company_id,
        "quote_id": quote_id or str(uuid.uuid4()),
        "contract_id": contract_id or str(uuid.uuid4()),
        "plan_code": "SAAS_MANAGER_12M",
        "product_type": "SAAS",
        "payment_type": "INICIS_CARD",
        "total_amount": 1320000,
        "supply_amount": 1200000,
        "vat_amount": 120000,
        "status_code": "SUCCESS",
        "service_status": "ACTIVE",
        "pg_method": "Card",
        "period_months": 12,
        "paid_at": _now_iso(-5),
        "created_at": _now_iso(-5),
    }


def _make_contract(company_id: str) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "contract_no": f"CON-{uuid.uuid4().hex[:8].upper()}",
        "company_id": company_id,
        "service_type": "SAAS",
        "status_code": "ACTIVE",
        "start_date": _now_iso(-30),
        "end_date": _now_iso(335),
        "total_amount": 1320000,
        "created_at": _now_iso(-5),
    }


# ── AUTH ─────────────────────────────────────────────────────────────────────

def test_ct_be01_non_admin_payments_403():
    """CT-BE01: non-admin → _require_admin raises 403 (same gate as other /admin/commercial)."""
    from fastapi import HTTPException
    from services.company_scope import _require_admin
    with pytest.raises(HTTPException) as exc:
        _require_admin(_non_admin_user(), FakeSB({}))
    assert exc.value.status_code == 403


def test_ct_be02_non_admin_contracts_403():
    """CT-BE02: same gate for contracts."""
    from fastapi import HTTPException
    from services.company_scope import _require_admin
    with pytest.raises(HTTPException) as exc:
        _require_admin(_non_admin_user(), FakeSB({}))
    assert exc.value.status_code == 403


# ── PAYMENTS ─────────────────────────────────────────────────────────────────

def test_ct_be03_payments_company_id_exact():
    """CT-BE03: company_id exact filter — other company excluded."""
    co_a = str(uuid.uuid4())
    co_b = str(uuid.uuid4())
    pay_a = _make_payment(co_a)
    pay_b = _make_payment(co_b)
    sb = FakeSB({"payments": [pay_a, pay_b]})

    result = svc.list_payments_admin(sb, co_a)
    ids = [r["id"] for r in result["items"]]
    assert pay_a["id"] in ids
    assert pay_b["id"] not in ids
    assert result["total"] == 1


def test_ct_be04_payments_quote_id_present():
    """CT-BE04: quote_id FK field returned in payment row."""
    co = str(uuid.uuid4())
    q_id = str(uuid.uuid4())
    pay = _make_payment(co, quote_id=q_id)
    sb = FakeSB({"payments": [pay]})

    result = svc.list_payments_admin(sb, co)
    assert result["items"][0]["quote_id"] == q_id


def test_ct_be05_payments_contract_id_present():
    """CT-BE05: contract_id FK field returned in payment row."""
    co = str(uuid.uuid4())
    ct_id = str(uuid.uuid4())
    pay = _make_payment(co, contract_id=ct_id)
    sb = FakeSB({"payments": [pay]})

    result = svc.list_payments_admin(sb, co)
    assert result["items"][0]["contract_id"] == ct_id


def test_ct_be06_payments_company_id_in_row():
    """CT-BE06: company_id field returned in each payment row."""
    co = str(uuid.uuid4())
    pay = _make_payment(co)
    sb = FakeSB({"payments": [pay]})

    result = svc.list_payments_admin(sb, co)
    assert result["items"][0]["company_id"] == co


def test_ct_be07_payments_db_write_zero():
    """CT-BE07: list_payments_admin DB write = 0."""
    co = str(uuid.uuid4())
    sb = FakeSB({"payments": [_make_payment(co)]})
    svc.list_payments_admin(sb, co)
    assert sb.write_log == []


def test_ct_be08_payments_created_at_desc():
    """CT-BE08: payments ordered by created_at DESC (newest first)."""
    co = str(uuid.uuid4())
    old = _make_payment(co); old["created_at"] = _now_iso(-10)
    new = _make_payment(co); new["created_at"] = _now_iso(-1)
    sb = FakeSB({"payments": [old, new]})

    result = svc.list_payments_admin(sb, co)
    dates = [r["created_at"] for r in result["items"]]
    assert dates == sorted(dates, reverse=True), "payments must be DESC by created_at"


# ── CONTRACTS ─────────────────────────────────────────────────────────────────

def test_ct_be09_contracts_company_id_exact():
    """CT-BE09: company_id exact filter — other company excluded."""
    co_a = str(uuid.uuid4())
    co_b = str(uuid.uuid4())
    ct_a = _make_contract(co_a)
    ct_b = _make_contract(co_b)
    sb = FakeSB({"contracts": [ct_a, ct_b]})

    result = svc.list_contracts_admin(sb, co_a)
    ids = [r["id"] for r in result["items"]]
    assert ct_a["id"] in ids
    assert ct_b["id"] not in ids
    assert result["total"] == 1


def test_ct_be10_contracts_contract_no_present():
    """CT-BE10: contract_no FK field returned in contract row."""
    co = str(uuid.uuid4())
    ct = _make_contract(co)
    sb = FakeSB({"contracts": [ct]})

    result = svc.list_contracts_admin(sb, co)
    assert result["items"][0]["contract_no"] == ct["contract_no"]


def test_ct_be11_contracts_company_id_in_row():
    """CT-BE11: company_id field returned in each contract row."""
    co = str(uuid.uuid4())
    ct = _make_contract(co)
    sb = FakeSB({"contracts": [ct]})

    result = svc.list_contracts_admin(sb, co)
    assert result["items"][0]["company_id"] == co


def test_ct_be12_contracts_db_write_zero():
    """CT-BE12: list_contracts_admin DB write = 0."""
    co = str(uuid.uuid4())
    sb = FakeSB({"contracts": [_make_contract(co)]})
    svc.list_contracts_admin(sb, co)
    assert sb.write_log == []


def test_ct_be13_contracts_created_at_desc():
    """CT-BE13: contracts ordered by created_at DESC."""
    co = str(uuid.uuid4())
    old = _make_contract(co); old["created_at"] = _now_iso(-10)
    new = _make_contract(co); new["created_at"] = _now_iso(-1)
    sb = FakeSB({"contracts": [old, new]})

    result = svc.list_contracts_admin(sb, co)
    dates = [r["created_at"] for r in result["items"]]
    assert dates == sorted(dates, reverse=True), "contracts must be DESC by created_at"


# ── STATIC ────────────────────────────────────────────────────────────────────

def test_ct_be14_no_write_routes():
    """CT-BE14: admin_commercial router에 POST/PUT/PATCH/DELETE route = 0."""
    import inspect
    import routers.admin_commercial as mod
    src = inspect.getsource(mod)
    for method in ("router.post", "router.put", "router.patch", "router.delete"):
        assert method not in src, f"mutation route found: {method}"


def test_ct_be15_no_v_payments_list():
    """CT-BE15: admin_commercial_svc에 .table('v_payments_list') 호출 없음."""
    import inspect
    import re
    import services.admin_commercial_svc as mod
    src = inspect.getsource(mod)
    assert not re.search(r'\.table\(["\']v_payments_list["\']', src), \
        ".table('v_payments_list') must not appear in admin_commercial_svc"
