"""SC01~SC15 — WO-COMM-V3-07C Member Subscription Control.

FakeSupabase + real service. DB=0 (cancel 시 write만).

SC01  current contract → exact subscription resolution (payments linkage)
SC02  다른 company subscription 접근 불가
SC03  subscription_id client input = 0 (function signature)
SC04  payment_months=1 → ACTIVE subscription projection
SC05  payment_months=3/6/9/12 → NOT_RECURRING
SC06  ambiguous ACTIVE subscription → fail-closed (SUBSCRIPTION_AMBIGUOUS)
SC07  cancel → subscription status=CANCELLED
SC08  cancel → next_billing_at=NULL
SC09  cancel → billing_key status=REVOKED
SC10  cancel → contract write = 0
SC11  cancel → contract end_date 변경 없음 (write 0)
SC12  cancel → payment INSERT = 0
SC13  cancelled subscription 재취소 → 409 SUBSCRIPTION_ALREADY_CANCELLED
SC14  member service가 /payments/subscriptions/{id}/cancel 미사용
SC15  scheduler/payment engine source change = 0
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

from services import member_subscription_svc as svc
from services.member_subscription_svc import MemberSubscriptionError


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
        self._not_filters: list = []
        self._limit_n: Optional[int] = None
        self._payload: Any = None

    def select(self, cols="*", *a, **kw):
        return self

    def insert(self, row):
        self._op = "insert"; self._payload = row; return self

    def update(self, patch):
        self._op = "update"; self._payload = patch; return self

    def delete(self):
        self._op = "delete"; return self

    def eq(self, c, v):
        self._filters.append(("eq", c, str(v))); return self

    def in_(self, c, vs):
        self._in_filters.append((c, [str(x) for x in vs])); return self

    def not_(self):
        return _NotProxy(self)

    def limit(self, n):
        self._limit_n = n; return self

    def order(self, *a, **kw): return self

    def _match(self, row: dict) -> bool:
        for op, c, v in self._filters:
            if op == "eq" and str(row.get(c, "")) != v:
                return False
        for c, vs in self._in_filters:
            if str(row.get(c, "")) not in vs:
                return False
        for c in self._not_filters:
            if row.get(c) is None:
                return False
        return True

    def execute(self) -> _Result:
        if self._op in ("update",):
            self._wl.append({"op": "update", "table": self._table, "payload": self._payload})
            return _Result([], 0)
        if self._op in ("insert",):
            self._wl.append({"op": "insert", "table": self._table, "payload": self._payload})
            return _Result([], 0)
        if self._op == "delete":
            self._wl.append({"op": "delete", "table": self._table})
            return _Result([], 0)
        self._ql.append(self._table)
        rows = [r for r in (self._store.get(self._table) or []) if self._match(r)]
        if self._limit_n is not None:
            rows = rows[: self._limit_n]
        return _Result(rows)


class _NotProxy:
    """Handles .not_.is_(col, 'null') — filters out rows where col IS NULL."""
    def __init__(self, query: _Query):
        self._q = query

    def is_(self, c, v):
        if str(v).lower() == "null":
            self._q._not_filters.append(c)
        return self._q


class FakeSB:
    def __init__(self, store: dict):
        self._store = store
        self.write_log: list = []
        self.query_log: list = []

    def table(self, name: str) -> _Query:
        return _Query(self._store, name, self.write_log, self.query_log)


def _uid() -> str:
    return str(uuid.uuid4())


def _now(offset_days: int = 0) -> str:
    return (datetime.now(tz=timezone.utc) + timedelta(days=offset_days)).isoformat()


# ── 픽스처 팩토리 ──────────────────────────────────────────────────────────────

def _make_subscription(
    sub_id: str,
    company_id: str,
    status: str = "ACTIVE",
    billing_key_id: Optional[str] = None,
    next_billing_at: Optional[str] = None,
) -> dict:
    return {
        "id": sub_id,
        "company_id": company_id,
        "user_id": _uid(),
        "product_type": "SAAS",
        "status": status,
        "billing_key_id": billing_key_id,
        "next_billing_at": next_billing_at or _now(30),
        "last_billed_at": _now(-1),
        "created_at": _now(-31),
        "updated_at": _now(),
    }


def _make_payment(
    contract_id: str,
    sub_id: str,
    status: str = "PAID",
) -> dict:
    return {
        "id": _uid(),
        "subscription_id": sub_id,
        "contract_id": contract_id,
        "product_type": "SAAS",
        "status_code": status,
        "charge_cycle": 1,
    }


def _make_billing_key(bk_id: str, sub_id: Optional[str] = None) -> dict:
    return {
        "id": bk_id,
        "subscription_id": sub_id,
        "status": "ACTIVE",
    }


def _make_store(
    company_id: str,
    contract_id: str,
    sub_id: str,
    sub_status: str = "ACTIVE",
    billing_key_id: Optional[str] = None,
    next_billing_at: Optional[str] = None,
) -> dict:
    bk_id = billing_key_id or _uid()
    return {
        "payments": [_make_payment(contract_id, sub_id)],
        "subscriptions": [
            _make_subscription(sub_id, company_id, sub_status, bk_id, next_billing_at)
        ],
        "billing_keys": [_make_billing_key(bk_id, sub_id)],
    }


# ── SC01: exact subscription resolution ───────────────────────────────────────

def test_SC01_subscription_resolved_via_payment_linkage():
    company_id = _uid()
    contract_id = _uid()
    sub_id = _uid()
    store = _make_store(company_id, contract_id, sub_id)
    sb = FakeSB(store)

    result = svc.get_member_subscription(sb, company_id, contract_id, 1)

    assert result["state"] == "ACTIVE"
    assert result["subscription"]["id"] == sub_id


# ── SC02: cross-company 접근 불가 ─────────────────────────────────────────────

def test_SC02_cross_company_subscription_blocked():
    company_id = _uid()
    other_company = _uid()
    contract_id = _uid()
    sub_id = _uid()
    bk_id = _uid()

    store = {
        "payments": [_make_payment(contract_id, sub_id)],
        "subscriptions": [
            _make_subscription(sub_id, other_company)  # 다른 회사
        ],
        "billing_keys": [_make_billing_key(bk_id)],
    }
    sb = FakeSB(store)
    result = svc.get_member_subscription(sb, company_id, contract_id, 1)
    assert result["state"] == "ERROR"
    assert result.get("error_code") == "SUBSCRIPTION_COMPANY_MISMATCH"


# ── SC03: subscription_id client input = 0 ────────────────────────────────────

def test_SC03_no_subscription_id_in_function_signature():
    import inspect
    sig = inspect.signature(svc.get_member_subscription)
    params = list(sig.parameters.keys())
    assert "subscription_id" not in params, "subscription_id must not be in get_member_subscription params"

    sig2 = inspect.signature(svc.cancel_member_subscription)
    params2 = list(sig2.parameters.keys())
    assert "subscription_id" not in params2, "subscription_id must not be in cancel_member_subscription params"


# ── SC04: payment_months=1 → ACTIVE projection ───────────────────────────────

def test_SC04_payment_months_1_returns_active_projection():
    company_id = _uid()
    contract_id = _uid()
    sub_id = _uid()
    next_bill = _now(30)
    store = _make_store(company_id, contract_id, sub_id, next_billing_at=next_bill)
    sb = FakeSB(store)

    result = svc.get_member_subscription(sb, company_id, contract_id, 1)

    assert result["state"] == "ACTIVE"
    assert result["subscription"]["next_billing_at"] == next_bill
    assert result["subscription"]["has_active_billing_key"] is True


# ── SC05: payment_months 3/6/9/12 → NOT_RECURRING ───────────────────────────

@pytest.mark.parametrize("months", [3, 6, 9, 12])
def test_SC05_non_recurring_months_return_NOT_RECURRING(months):
    company_id = _uid()
    contract_id = _uid()
    sb = FakeSB({})  # DB 조회 없음 — early return
    result = svc.get_member_subscription(sb, company_id, contract_id, months)
    assert result["state"] == "NOT_RECURRING"
    assert result["subscription"] is None


# ── SC06: ambiguous subscription → fail-closed ────────────────────────────────

def test_SC06_ambiguous_subscription_fail_closed():
    company_id = _uid()
    contract_id = _uid()
    sub_id_a = _uid()
    sub_id_b = _uid()

    # 같은 contract_id에 두 개의 subscription_id
    store = {
        "payments": [
            _make_payment(contract_id, sub_id_a),
            _make_payment(contract_id, sub_id_b),
        ],
        "subscriptions": [
            _make_subscription(sub_id_a, company_id),
            _make_subscription(sub_id_b, company_id),
        ],
        "billing_keys": [],
    }
    sb = FakeSB(store)
    result = svc.get_member_subscription(sb, company_id, contract_id, 1)
    assert result["state"] == "ERROR"
    assert result.get("error_code") == "SUBSCRIPTION_AMBIGUOUS"


# ── SC07: cancel → subscription CANCELLED ────────────────────────────────────

def test_SC07_cancel_sets_subscription_cancelled():
    company_id = _uid()
    contract_id = _uid()
    sub_id = _uid()
    store = _make_store(company_id, contract_id, sub_id)
    sb = FakeSB(store)

    result = svc.cancel_member_subscription(sb, company_id, contract_id, 1)

    assert result["cancelled"] is True
    assert result["status"] == "CANCELLED"
    sub_writes = [w for w in sb.write_log if w["table"] == "subscriptions"]
    assert len(sub_writes) >= 1
    assert sub_writes[0]["payload"]["status"] == "CANCELLED"


# ── SC08: cancel → next_billing_at = NULL ────────────────────────────────────

def test_SC08_cancel_clears_next_billing_at():
    company_id = _uid()
    contract_id = _uid()
    sub_id = _uid()
    store = _make_store(company_id, contract_id, sub_id)
    sb = FakeSB(store)

    svc.cancel_member_subscription(sb, company_id, contract_id, 1)

    sub_writes = [w for w in sb.write_log if w["table"] == "subscriptions"]
    assert sub_writes[0]["payload"]["next_billing_at"] is None


# ── SC09: cancel → billing_key REVOKED ───────────────────────────────────────

def test_SC09_cancel_revokes_billing_key():
    company_id = _uid()
    contract_id = _uid()
    sub_id = _uid()
    bk_id = _uid()
    store = _make_store(company_id, contract_id, sub_id, billing_key_id=bk_id)
    sb = FakeSB(store)

    svc.cancel_member_subscription(sb, company_id, contract_id, 1)

    bk_writes = [w for w in sb.write_log if w["table"] == "billing_keys"]
    assert len(bk_writes) >= 1
    assert bk_writes[0]["payload"]["status"] == "REVOKED"


# ── SC10+SC11: cancel → contract write = 0 ───────────────────────────────────

def test_SC10_SC11_cancel_does_not_touch_contracts():
    company_id = _uid()
    contract_id = _uid()
    sub_id = _uid()
    store = _make_store(company_id, contract_id, sub_id)
    sb = FakeSB(store)

    svc.cancel_member_subscription(sb, company_id, contract_id, 1)

    contract_writes = [w for w in sb.write_log if w["table"] == "contracts"]
    assert len(contract_writes) == 0, "contracts must not be written on cancel"


# ── SC12: cancel → payment INSERT = 0 ────────────────────────────────────────

def test_SC12_cancel_does_not_insert_payment():
    company_id = _uid()
    contract_id = _uid()
    sub_id = _uid()
    store = _make_store(company_id, contract_id, sub_id)
    sb = FakeSB(store)

    svc.cancel_member_subscription(sb, company_id, contract_id, 1)

    payment_inserts = [w for w in sb.write_log if w["table"] == "payments" and w["op"] == "insert"]
    assert len(payment_inserts) == 0, "payments INSERT must be 0 on cancel"


# ── SC13: re-cancel → 409 ────────────────────────────────────────────────────

def test_SC13_recancel_already_cancelled_raises_409():
    company_id = _uid()
    contract_id = _uid()
    sub_id = _uid()
    store = _make_store(company_id, contract_id, sub_id, sub_status="CANCELLED")
    sb = FakeSB(store)

    with pytest.raises(MemberSubscriptionError) as exc_info:
        svc.cancel_member_subscription(sb, company_id, contract_id, 1)

    assert exc_info.value.code == "SUBSCRIPTION_ALREADY_CANCELLED"
    assert exc_info.value.http_status == 409


# ── SC14: member service가 legacy endpoint 미사용 ────────────────────────────

def test_SC14_member_service_does_not_use_legacy_cancel_endpoint():
    import inspect
    src = inspect.getsource(svc)
    assert "/payments/subscriptions" not in src, \
        "member_subscription_svc must not reference legacy /payments/subscriptions cancel endpoint"


# ── SC15: scheduler/payment engine source 변경 없음 ──────────────────────────

def test_SC15_scheduler_and_billing_engine_not_imported():
    import inspect
    src = inspect.getsource(svc)
    assert "saas_recurring_billing_scheduler" not in src, \
        "member_subscription_svc must not import scheduler"
    assert "payment_billing" not in src, \
        "member_subscription_svc must not import payment_billing"
    assert "run_billing_cancel" not in src, \
        "member_subscription_svc must not use run_billing_cancel (remote INIAPI)"
