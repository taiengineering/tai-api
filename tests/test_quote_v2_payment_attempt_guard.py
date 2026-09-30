"""WO-FE-WWW-04-PRE-001: Frozen Quote V2 Duplicate Payment Guard.

DP01-DP24: guard helper unit tests + integration through prepare_saas_v2_payment_from_quote.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

from services.saas_payment_v2_adapter import (
    SaasPaymentV2AdapterError,
    _find_existing_v2_payment,
    _handle_race_recovery,
    _is_quote_v2_unique_violation,
    _validate_pending_reuse,
    prepare_saas_v2_payment_from_quote,
)

_QUOTE_ID = str(uuid.uuid4())
_USER_ID = "U-DP-TEST"
_OTHER_USER_ID = "U-DP-OTHER"
_COMPANY_ID = "C-DP-TEST"
_PAYMENT_ID = str(uuid.uuid4())
_ORDER_ID = "ORD-DP-001"
_SIGN_KEY = "TEST_SIGN_KEY_DP"
_GOODNAME = "TAI Safe 관리자형"
_SITE_ID = str(uuid.uuid4())


# ── Helpers ────────────────────────────────────────────────────────────────────

def _pending_row(user_id=_USER_ID, payment_id=_PAYMENT_ID, order_id=_ORDER_ID, total=110_000):
    return {
        "id": payment_id,
        "user_id": user_id,
        "status_code": "PENDING",
        "inicis_order_id": order_id,
        "total_amount": total,
        "product_type": "SAAS",
        "goodname": _GOODNAME,
        "buyername": None,
        "buyertel": None,
        "buyeremail": None,
    }


def _paid_row(user_id=_USER_ID, status="PAID"):
    return {**_pending_row(user_id=user_id), "status_code": status}


def _fake_sb_with_existing(row: Optional[dict]):
    """SELECT query returns existing row or nothing."""
    sb = MagicMock()
    (sb.table.return_value
       .select.return_value
       .eq.return_value
       .eq.return_value
       .eq.return_value
       .in_.return_value
       .order.return_value
       .limit.return_value
       .execute.return_value) = MagicMock(data=[row] if row else [])
    return sb


def _fake_sb_insert_ok(payment_id=_PAYMENT_ID, order_id=_ORDER_ID):
    sb = MagicMock()
    insert_mock = MagicMock()
    insert_mock.execute.return_value = MagicMock(data=[{"id": payment_id, "inicis_order_id": order_id}])
    sb.table.return_value.insert.return_value = insert_mock
    return sb


def _minimal_snap_dict(supply=100_000, vat=10_000, total=110_000, term=1):
    return {
        "schema_version": "SAAS_PRICING_V2",
        "policy_version": "TEST",
        "product_tier": "MANAGER",
        "pricing_mode": "STANDARD",
        "sites": [{
            "entity_type": "factory",
            "entity_id": _SITE_ID,
            "sector": "INDUSTRY",
            "base_band_code": "STANDARD",
            "base_amount": supply,
            "is_primary": True,
            "applied_rate_bps": 10_000,
            "final_site_amount": supply,
        }],
        "worker": {"capacity": 0, "amount": 0, "brackets": []},
        "payment_months": term,
        "term_discount_rate_bps": 0,
        "monthly_supply_amount": supply,
        "prepaid_supply_amount": supply,
        "vat_rate_bps": 1_000,
        "vat_amount": vat,
        "total_amount": total,
    }


def _minimal_item_dict(supply=100_000, vat=10_000, total=110_000, term=1):
    return {
        "quote_schema_version": "SAAS_QUOTE_V2",
        "display_name": _GOODNAME,
        "billing_unit": "MONTHLY",
        "unit_amount": supply,
        "quantity": term,
        "supply_amount": supply,
        "vat_amount": vat,
        "total_amount": total,
        "service_type": "SAAS",
        "price_id": None,
        "tier_code": None,
        "sector": "INDUSTRY",
        "sectors": ["INDUSTRY"],
        "product_tier": "MANAGER",
        "pricing_mode": "STANDARD",
        "policy_version": "TEST",
        "worker_capacity": 0,
        "payment_months": term,
        "vat_rate": 0.1,
        "vat_rate_bps": 1_000,
        "pricing_input": {
            "product_tier": "MANAGER",
            "worker_capacity": 0,
            "payment_months": term,
            "sites": [{"entity_id": _SITE_ID, "sector": "INDUSTRY", "criteria_value": 10}],
        },
        "pricing_snapshot": _minimal_snap_dict(supply, vat, total, term),
    }


def _valid_v2_quote(supply=100_000, vat=10_000, total=110_000, term=1):
    return {
        "id": _QUOTE_ID,
        "company_id": _COMPANY_ID,
        "status_code": "ISSUED",
        "service_type": "SAAS",
        "supply_amount": supply,
        "vat_amount": vat,
        "total_amount": total,
        "items": [_minimal_item_dict(supply, vat, total, term)],
    }


# ── DP01-DP05: _find_existing_v2_payment ──────────────────────────────────────

def test_DP01_find_returns_none_when_no_row():
    """PENDING/PAID/SUCCESS 없음 → None."""
    sb = _fake_sb_with_existing(None)
    result = _find_existing_v2_payment(sb, _QUOTE_ID)
    assert result is None


def test_DP02_find_returns_pending_row():
    """PENDING 행 존재 → 해당 row 반환."""
    row = _pending_row()
    sb = _fake_sb_with_existing(row)
    result = _find_existing_v2_payment(sb, _QUOTE_ID)
    assert result is not None
    assert result["status_code"] == "PENDING"


def test_DP03_find_returns_paid_row():
    """PAID 행 존재 → 해당 row 반환."""
    row = _paid_row(status="PAID")
    sb = _fake_sb_with_existing(row)
    result = _find_existing_v2_payment(sb, _QUOTE_ID)
    assert result is not None
    assert result["status_code"] == "PAID"


def test_DP04_find_returns_success_row():
    """SUCCESS 행 존재 → 해당 row 반환."""
    row = _paid_row(status="SUCCESS")
    sb = _fake_sb_with_existing(row)
    result = _find_existing_v2_payment(sb, _QUOTE_ID)
    assert result is not None
    assert result["status_code"] == "SUCCESS"


def test_DP05_find_query_uses_active_statuses():
    """_find_existing_v2_payment 소스에 PENDING/PAID/SUCCESS 포함 확인."""
    src = (Path(__file__).parent.parent / "services" / "saas_payment_v2_adapter.py").read_text()
    # The helper uses _ACTIVE_STATUSES which maps to these codes
    assert "PENDING" in src
    assert "PAID" in src
    assert "SUCCESS" in src
    assert "_ACTIVE_STATUSES" in src


# ── DP06-DP10: _validate_pending_reuse ────────────────────────────────────────

def test_DP06_same_user_pending_returns_success_response():
    """PENDING + 같은 user_id → {"status": "success", ...} 반환."""
    row = _pending_row(user_id=_USER_ID)
    result = _validate_pending_reuse(row, _USER_ID, _SIGN_KEY, _GOODNAME)
    assert result["status"] == "success"
    assert result["data"]["payment_id"] == _PAYMENT_ID


def test_DP07_same_user_pending_reuses_order_id():
    """PENDING reuse → 기존 inicis_order_id 재사용."""
    row = _pending_row(user_id=_USER_ID, order_id=_ORDER_ID)
    result = _validate_pending_reuse(row, _USER_ID, _SIGN_KEY, _GOODNAME)
    assert result["data"]["oid"] == _ORDER_ID


def test_DP08_same_user_pending_fresh_timestamp():
    """PENDING reuse → timestamp 필드 존재 (INICIS form 필요)."""
    row = _pending_row(user_id=_USER_ID)
    result = _validate_pending_reuse(row, _USER_ID, _SIGN_KEY, _GOODNAME)
    assert "timestamp" in result["data"]
    assert result["data"]["timestamp"]


def test_DP09_other_user_pending_raises_quote_payment_pending():
    """PENDING + 다른 user_id → QUOTE_PAYMENT_PENDING."""
    row = _pending_row(user_id=_OTHER_USER_ID)
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        _validate_pending_reuse(row, _USER_ID, _SIGN_KEY, _GOODNAME)
    assert exc.value.code == "QUOTE_PAYMENT_PENDING"


def test_DP10_paid_row_raises_quote_already_paid():
    """PAID 행 → QUOTE_ALREADY_PAID."""
    row = _paid_row(status="PAID", user_id=_USER_ID)
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        _validate_pending_reuse(row, _USER_ID, _SIGN_KEY, _GOODNAME)
    assert exc.value.code == "QUOTE_ALREADY_PAID"


def test_DP10b_success_row_raises_quote_already_paid():
    """SUCCESS 행 → QUOTE_ALREADY_PAID."""
    row = _paid_row(status="SUCCESS", user_id=_USER_ID)
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        _validate_pending_reuse(row, _USER_ID, _SIGN_KEY, _GOODNAME)
    assert exc.value.code == "QUOTE_ALREADY_PAID"


# ── DP11-DP13: _is_quote_v2_unique_violation ──────────────────────────────────

def test_DP11_correct_violation_detected():
    """23505 + index name → True."""
    class _FakeExc(Exception):
        pass
    exc = _FakeExc("ERROR: duplicate key value violates unique constraint "
                   '"uix_payments_quote_v2_initial_active" DETAIL: ... (23505)')
    assert _is_quote_v2_unique_violation(exc) is True


def test_DP12_other_unique_violation_not_detected():
    """23505 but different index → False."""
    class _FakeExc(Exception):
        pass
    exc = _FakeExc("ERROR: duplicate key 23505 constraint uix_payments_other")
    assert _is_quote_v2_unique_violation(exc) is False


def test_DP13_non_unique_error_not_detected():
    """23514 (check violation) → False."""
    class _FakeExc(Exception):
        pass
    exc = _FakeExc("ERROR: 23514 new row violates check constraint")
    assert _is_quote_v2_unique_violation(exc) is False


# ── DP14-DP17: _handle_race_recovery ──────────────────────────────────────────

def test_DP14_race_recovery_same_user_pending_returns_reuse(monkeypatch):
    """경쟁 삽입 후 재조회 PENDING 같은 user → reuse 응답."""
    row = _pending_row(user_id=_USER_ID)
    monkeypatch.setattr(
        "services.saas_payment_v2_adapter._find_existing_v2_payment",
        lambda sb, qid: row,
    )
    result = _handle_race_recovery(None, _QUOTE_ID, _USER_ID, _SIGN_KEY, _GOODNAME)
    assert result["status"] == "success"
    assert result["data"]["payment_id"] == _PAYMENT_ID


def test_DP15_race_recovery_no_row_raises_conflict(monkeypatch):
    """경쟁 삽입 후 재조회 빈 결과 → QUOTE_PAYMENT_STATE_CONFLICT."""
    monkeypatch.setattr(
        "services.saas_payment_v2_adapter._find_existing_v2_payment",
        lambda sb, qid: None,
    )
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        _handle_race_recovery(None, _QUOTE_ID, _USER_ID, _SIGN_KEY, _GOODNAME)
    assert exc.value.code == "QUOTE_PAYMENT_STATE_CONFLICT"


def test_DP16_race_recovery_other_user_raises_pending(monkeypatch):
    """경쟁 삽입 후 재조회 PENDING 다른 user → QUOTE_PAYMENT_PENDING."""
    row = _pending_row(user_id=_OTHER_USER_ID)
    monkeypatch.setattr(
        "services.saas_payment_v2_adapter._find_existing_v2_payment",
        lambda sb, qid: row,
    )
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        _handle_race_recovery(None, _QUOTE_ID, _USER_ID, _SIGN_KEY, _GOODNAME)
    assert exc.value.code == "QUOTE_PAYMENT_PENDING"


def test_DP17_race_recovery_paid_raises_already_paid(monkeypatch):
    """경쟁 삽입 후 재조회 PAID → QUOTE_ALREADY_PAID."""
    row = _paid_row(status="PAID", user_id=_OTHER_USER_ID)
    monkeypatch.setattr(
        "services.saas_payment_v2_adapter._find_existing_v2_payment",
        lambda sb, qid: row,
    )
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        _handle_race_recovery(None, _QUOTE_ID, _USER_ID, _SIGN_KEY, _GOODNAME)
    assert exc.value.code == "QUOTE_ALREADY_PAID"


# ── DP18-DP24: Integration — prepare_saas_v2_payment_from_quote ───────────────

def _setup_guard_test(monkeypatch, existing_row: Optional[dict] = None):
    """검증 통과 + guard 조건만 변수화하는 공통 픽스처."""
    quote = _valid_v2_quote()
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: quote)
    monkeypatch.setattr("services.saas_payment_v2_adapter.load_sign_key", lambda: _SIGN_KEY)
    monkeypatch.setattr(
        "services.saas_payment_v2_adapter._find_existing_v2_payment",
        lambda sb, qid: existing_row,
    )
    insert_calls = []

    def _fake_insert(sb, sk, **kw):
        insert_calls.append(kw)
        return {"status": "success", "data": {"payment_id": "pay-new"}}

    monkeypatch.setattr("services.saas_payment_v2_adapter._run_inicis_prepare_exact", _fake_insert)
    return insert_calls


def test_DP18_no_existing_payment_proceeds_to_insert(monkeypatch):
    """기존 결제 없음 → INSERT 경로 진입 (insert_calls=1)."""
    calls = _setup_guard_test(monkeypatch, existing_row=None)
    prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert len(calls) == 1


def test_DP19_existing_pending_same_user_no_insert(monkeypatch):
    """PENDING 같은 user → INSERT 0, reuse 응답 반환."""
    row = _pending_row(user_id=_USER_ID)
    calls = _setup_guard_test(monkeypatch, existing_row=row)
    result = prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert len(calls) == 0
    assert result["status"] == "success"
    assert result["data"]["payment_id"] == _PAYMENT_ID


def test_DP20_existing_pending_other_user_raises_409_code(monkeypatch):
    """PENDING 다른 user → QUOTE_PAYMENT_PENDING, INSERT 0."""
    row = _pending_row(user_id=_OTHER_USER_ID)
    calls = _setup_guard_test(monkeypatch, existing_row=row)
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_PAYMENT_PENDING"
    assert len(calls) == 0


def test_DP21_existing_paid_raises_quote_already_paid(monkeypatch):
    """PAID 기존 결제 → QUOTE_ALREADY_PAID, INSERT 0."""
    row = _paid_row(status="PAID")
    calls = _setup_guard_test(monkeypatch, existing_row=row)
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_ALREADY_PAID"
    assert len(calls) == 0


def test_DP22_existing_success_raises_quote_already_paid(monkeypatch):
    """SUCCESS 기존 결제 → QUOTE_ALREADY_PAID, INSERT 0."""
    row = _paid_row(status="SUCCESS")
    calls = _setup_guard_test(monkeypatch, existing_row=row)
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_ALREADY_PAID"
    assert len(calls) == 0


def test_DP23_race_insert_23505_triggers_recovery(monkeypatch):
    """INSERT에서 23505(index) → race recovery 경로 진입."""
    quote = _valid_v2_quote()
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: quote)
    monkeypatch.setattr("services.saas_payment_v2_adapter.load_sign_key", lambda: _SIGN_KEY)
    # First call: no existing; INSERT raises 23505
    monkeypatch.setattr(
        "services.saas_payment_v2_adapter._find_existing_v2_payment",
        lambda sb, qid: None,
    )

    class _UniqueViolation(Exception):
        pass

    def _raise_23505(sb, sk, **kw):
        raise _UniqueViolation(
            "23505 duplicate key violates unique constraint "
            "uix_payments_quote_v2_initial_active"
        )

    monkeypatch.setattr("services.saas_payment_v2_adapter._run_inicis_prepare_exact", _raise_23505)

    recovery_calls = []

    def _fake_recovery(sb, qid, uid, sk, gn, **kw):
        recovery_calls.append({"qid": qid, "uid": uid})
        return {"status": "success", "data": {"payment_id": "pay-recovered"}}

    monkeypatch.setattr("services.saas_payment_v2_adapter._handle_race_recovery", _fake_recovery)
    result = prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert len(recovery_calls) == 1
    assert result["data"]["payment_id"] == "pay-recovered"


def test_DP24_non_unique_insert_error_propagates(monkeypatch):
    """INSERT에서 23505 아닌 오류 → recovery 없이 그대로 raise."""
    quote = _valid_v2_quote()
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: quote)
    monkeypatch.setattr("services.saas_payment_v2_adapter.load_sign_key", lambda: _SIGN_KEY)
    monkeypatch.setattr(
        "services.saas_payment_v2_adapter._find_existing_v2_payment",
        lambda sb, qid: None,
    )

    class _OtherError(RuntimeError):
        pass

    def _raise_other(sb, sk, **kw):
        raise _OtherError("connection timeout")

    monkeypatch.setattr("services.saas_payment_v2_adapter._run_inicis_prepare_exact", _raise_other)
    with pytest.raises(_OtherError):
        prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
