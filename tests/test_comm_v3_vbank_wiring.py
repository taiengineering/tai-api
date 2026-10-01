"""WO-COMM-V3-04-VBANK-V3-WIRING-001 — V3 SAAS VBANK wiring tests.

VB01-VB06  : prepare happy-path (payment row fields, response shape)
VB07-VB09  : duplicate / state guard
VB10       : monthly (payment_months=1) blocked
VB11-VB13  : quote validation errors (same as CARD path)
VB14       : legacy VBANK VbankPrepareBody still blocks SAAS
VB15-VB16  : process_vbank_deposit → on_payment_success_sync reuse
VB17       : V3 _is_commercial_v3_saas_payment trusts VBANK quote
VB18       : regression — existing CARD adapter unaffected
"""
from __future__ import annotations

import os
import uuid
from typing import Any, Optional
from unittest.mock import MagicMock, call, patch

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

_QUOTE_ID = str(uuid.uuid4())
_COMPANY_ID = str(uuid.uuid4())
_USER_ID = str(uuid.uuid4())
_OTHER_USER_ID = str(uuid.uuid4())
_PAY_ID = str(uuid.uuid4())
_ORDER_ID = "VBWT-ORD-001"
_SITE_ID = str(uuid.uuid4())

_SUPPLY = 200_000
_VAT = 20_000
_TOTAL = 220_000
_TERM = 3  # single-pay (3 months)


# ── Quote Factories ────────────────────────────────────────────────────────────

def _snap_dict(payment_months=_TERM, supply=_SUPPLY, vat=_VAT, total=_TOTAL):
    return {
        "schema_version": "SAAS_PRICING_V2",
        "policy_version": "V3-VBTEST",
        "product_tier": "MANAGER",
        "pricing_mode": "STANDARD",
        "sites": [{"entity_type": "factory", "entity_id": _SITE_ID, "sector": "INDUSTRY",
                   "base_band_code": "STANDARD", "base_amount": supply, "is_primary": True,
                   "applied_rate_bps": 10000, "final_site_amount": supply}],
        "worker": {"capacity": 0, "amount": 0, "brackets": []},
        "payment_months": payment_months,
        "term_discount_rate_bps": 0,
        "monthly_supply_amount": supply,
        "prepaid_supply_amount": supply,
        "vat_rate_bps": 1000,
        "vat_amount": vat,
        "total_amount": total,
    }


def _item_dict(payment_months=_TERM, supply=_SUPPLY, vat=_VAT, total=_TOTAL):
    return {
        "quote_schema_version": "SAAS_QUOTE_V2",
        "display_name": "TAI Safe MANAGER 3개월",
        "billing_unit": "MONTHLY",
        "unit_amount": supply,
        "quantity": payment_months,
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
        "policy_version": "V3-VBTEST",
        "worker_capacity": 0,
        "payment_months": payment_months,
        "vat_rate": 0.1,
        "vat_rate_bps": 1000,
        "pricing_input": {
            "product_tier": "MANAGER",
            "worker_capacity": 0,
            "payment_months": payment_months,
            "sites": [{"entity_id": _SITE_ID, "sector": "INDUSTRY", "criteria_value": 10}],
        },
        "pricing_snapshot": _snap_dict(payment_months, supply, vat, total),
    }


def _make_quote(payment_months=_TERM, supply=_SUPPLY, vat=_VAT, total=_TOTAL,
                company_id=_COMPANY_ID, status="ISSUED", service_type="SAAS"):
    return {
        "id": _QUOTE_ID,
        "company_id": company_id,
        "status_code": status,
        "service_type": service_type,
        "source": "member_auto",
        "supply_amount": supply,
        "vat_amount": vat,
        "total_amount": total,
        "items": [_item_dict(payment_months, supply, vat, total)],
    }


def _vbank_pending_row(user_id=_USER_ID, status="PENDING"):
    return {
        "id": _PAY_ID,
        "user_id": user_id,
        "company_id": _COMPANY_ID,
        "quote_id": _QUOTE_ID,
        "status_code": status,
        "inicis_order_id": _ORDER_ID,
        "product_type": "SAAS",
        "payment_type": "VBANK",
        "plan_code": None,
        "period_months": _TERM,
        "supply_amount": _SUPPLY,
        "vat_amount": _VAT,
        "total_amount": _TOTAL,
    }


def _make_sb(quote=None, existing_vbank=None, pay_insert_id=_PAY_ID):
    """FakeSupabase mock for V3 VBANK prepare tests."""
    sb = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "payments":
            # duplicate guard SELECT: eq(quote_id).eq(SAAS).eq(VBANK).in_(...).order.limit
            t.select.return_value.eq.return_value.eq.return_value.eq.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[existing_vbank] if existing_vbank else []
            )
            t.insert.return_value.execute.return_value = MagicMock(
                data=[{"id": pay_insert_id, "inicis_order_id": _ORDER_ID}]
            )
            t.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        return t

    sb.table.side_effect = _table
    return sb


# ── VB01-VB06: Happy-path prepare ─────────────────────────────────────────────

def test_VB01_response_has_vbank_gopaymethod():
    """VB01: prepare response gopaymethod=Vbank."""
    from services.saas_payment_v2_adapter import prepare_saas_v2_vbank_from_quote
    sb = _make_sb()
    with (
        patch("services.member_quote_svc.get_member_quote", return_value=_make_quote()),
        patch("services.saas_payment_v2_adapter.load_sign_key", return_value="SIGN"),
        patch("services.saas_payment_v2_adapter._run_inicis_prepare_exact", return_value={
            "status": "success",
            "data": {"payment_id": _PAY_ID, "oid": _ORDER_ID, "price": str(_TOTAL), "gopaymethod": ""},
        }),
    ):
        result = prepare_saas_v2_vbank_from_quote(sb, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert result["data"]["gopaymethod"] == "Vbank"


def test_VB02_response_has_vbankexpire():
    """VB02: prepare response vbankexpire present."""
    from services.saas_payment_v2_adapter import prepare_saas_v2_vbank_from_quote, _VBANK_EXPIRE_MIN_DEFAULT
    sb = _make_sb()
    with (
        patch("services.member_quote_svc.get_member_quote", return_value=_make_quote()),
        patch("services.saas_payment_v2_adapter.load_sign_key", return_value="SIGN"),
        patch("services.saas_payment_v2_adapter._run_inicis_prepare_exact", return_value={
            "status": "success",
            "data": {"payment_id": _PAY_ID, "oid": _ORDER_ID, "price": str(_TOTAL), "gopaymethod": ""},
        }),
    ):
        result = prepare_saas_v2_vbank_from_quote(sb, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert result["data"]["vbankexpire"] == _VBANK_EXPIRE_MIN_DEFAULT


def test_VB03_run_inicis_called_with_vbank_payment_type():
    """VB03: _run_inicis_prepare_exact called with payment_type=VBANK."""
    from services.saas_payment_v2_adapter import prepare_saas_v2_vbank_from_quote
    sb = _make_sb()
    captured = {}
    def _fake_run(supabase, sign_key, *, payment_type, product_type, quote_id, **kw):
        captured["payment_type"] = payment_type
        captured["product_type"] = product_type
        captured["quote_id"] = quote_id
        return {"status": "success", "data": {"payment_id": _PAY_ID, "oid": _ORDER_ID, "price": str(_TOTAL), "gopaymethod": ""}}
    with (
        patch("services.member_quote_svc.get_member_quote", return_value=_make_quote()),
        patch("services.saas_payment_v2_adapter.load_sign_key", return_value="SIGN"),
        patch("services.saas_payment_v2_adapter._run_inicis_prepare_exact", side_effect=_fake_run),
    ):
        prepare_saas_v2_vbank_from_quote(sb, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert captured["payment_type"] == "VBANK"
    assert captured["product_type"] == "SAAS"
    assert captured["quote_id"] == _QUOTE_ID


def test_VB04_pg_method_vbank_stored_via_update():
    """VB04: payments.update called with pg_method=VBANK after INSERT."""
    from services.saas_payment_v2_adapter import prepare_saas_v2_vbank_from_quote
    update_calls = []
    sb = _make_sb()

    original_table = sb.table.side_effect
    def _tracking_table(name):
        t = original_table(name)
        if name == "payments":
            original_update = t.update
            def _track_update(patch_dict):
                update_calls.append(patch_dict)
                return original_update(patch_dict)
            t.update = _track_update
        return t
    sb.table.side_effect = _tracking_table

    with (
        patch("services.member_quote_svc.get_member_quote", return_value=_make_quote()),
        patch("services.saas_payment_v2_adapter.load_sign_key", return_value="SIGN"),
        patch("services.saas_payment_v2_adapter._run_inicis_prepare_exact", return_value={
            "status": "success",
            "data": {"payment_id": _PAY_ID, "oid": _ORDER_ID, "price": str(_TOTAL), "gopaymethod": ""},
        }),
    ):
        prepare_saas_v2_vbank_from_quote(sb, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert any(c.get("pg_method") == "VBANK" for c in update_calls)


def test_VB05_vbank_expires_at_stored():
    """VB05: vbank_expires_at field set in pg_method update payload."""
    from services.saas_payment_v2_adapter import prepare_saas_v2_vbank_from_quote
    update_calls = []
    sb = _make_sb()

    original_table = sb.table.side_effect
    def _tracking_table(name):
        t = original_table(name)
        if name == "payments":
            original_update = t.update
            def _track(d):
                update_calls.append(d)
                return original_update(d)
            t.update = _track
        return t
    sb.table.side_effect = _tracking_table

    with (
        patch("services.member_quote_svc.get_member_quote", return_value=_make_quote()),
        patch("services.saas_payment_v2_adapter.load_sign_key", return_value="SIGN"),
        patch("services.saas_payment_v2_adapter._run_inicis_prepare_exact", return_value={
            "status": "success",
            "data": {"payment_id": _PAY_ID, "oid": _ORDER_ID, "price": str(_TOTAL), "gopaymethod": ""},
        }),
    ):
        prepare_saas_v2_vbank_from_quote(sb, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert any("vbank_expires_at" in c for c in update_calls)


def test_VB06_plan_code_none_in_run_inicis():
    """VB06: plan_code=None passed to _run_inicis_prepare_exact (V3 invariant)."""
    from services.saas_payment_v2_adapter import prepare_saas_v2_vbank_from_quote
    captured = {}
    def _fake_run(supabase, sign_key, *, plan_code, **kw):
        captured["plan_code"] = plan_code
        return {"status": "success", "data": {"payment_id": _PAY_ID, "oid": _ORDER_ID, "price": str(_TOTAL), "gopaymethod": ""}}
    with (
        patch("services.member_quote_svc.get_member_quote", return_value=_make_quote()),
        patch("services.saas_payment_v2_adapter.load_sign_key", return_value="SIGN"),
        patch("services.saas_payment_v2_adapter._run_inicis_prepare_exact", side_effect=_fake_run),
    ):
        prepare_saas_v2_vbank_from_quote(_make_sb(), _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert captured["plan_code"] is None


# ── VB07-VB09: Duplicate / state guard ────────────────────────────────────────

def test_VB07_already_paid_raises():
    """VB07: existing SUCCESS VBANK payment → QUOTE_ALREADY_PAID."""
    from services.saas_payment_v2_adapter import prepare_saas_v2_vbank_from_quote, SaasPaymentV2AdapterError
    existing = _vbank_pending_row(status="SUCCESS")
    sb = _make_sb(existing_vbank=existing)
    with (
        patch("services.member_quote_svc.get_member_quote", return_value=_make_quote()),
        patch("services.saas_payment_v2_adapter.load_sign_key", return_value="SIGN"),
    ):
        with pytest.raises(SaasPaymentV2AdapterError) as exc_info:
            prepare_saas_v2_vbank_from_quote(sb, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc_info.value.code == "QUOTE_ALREADY_PAID"


def test_VB08_other_user_pending_raises():
    """VB08: different user has PENDING VBANK → QUOTE_PAYMENT_PENDING."""
    from services.saas_payment_v2_adapter import prepare_saas_v2_vbank_from_quote, SaasPaymentV2AdapterError
    existing = _vbank_pending_row(user_id=_OTHER_USER_ID, status="PENDING")
    sb = _make_sb(existing_vbank=existing)
    with (
        patch("services.member_quote_svc.get_member_quote", return_value=_make_quote()),
        patch("services.saas_payment_v2_adapter.load_sign_key", return_value="SIGN"),
    ):
        with pytest.raises(SaasPaymentV2AdapterError) as exc_info:
            prepare_saas_v2_vbank_from_quote(sb, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc_info.value.code == "QUOTE_PAYMENT_PENDING"


def test_VB09_same_user_pending_returns_reuse_response():
    """VB09: same-user PENDING VBANK → reuse response (gopaymethod=Vbank)."""
    from services.saas_payment_v2_adapter import prepare_saas_v2_vbank_from_quote
    existing = _vbank_pending_row(user_id=_USER_ID, status="PENDING")
    sb = _make_sb(existing_vbank=existing)
    with (
        patch("services.member_quote_svc.get_member_quote", return_value=_make_quote()),
        patch("services.saas_payment_v2_adapter.load_sign_key", return_value="SIGN"),
    ):
        result = prepare_saas_v2_vbank_from_quote(sb, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert result["status"] == "success"
    assert result["data"]["gopaymethod"] == "Vbank"
    assert result["data"]["payment_id"] == _PAY_ID


# ── VB10: Monthly blocked ──────────────────────────────────────────────────────

def test_VB10_monthly_recurring_blocked():
    """VB10: payment_months=1 → VBANK_NOT_SUPPORTED_FOR_RECURRING."""
    from services.saas_payment_v2_adapter import prepare_saas_v2_vbank_from_quote, SaasPaymentV2AdapterError
    sb = _make_sb()
    with (
        patch("services.member_quote_svc.get_member_quote", return_value=_make_quote(payment_months=1)),
        patch("services.saas_payment_v2_adapter.load_sign_key", return_value="SIGN"),
    ):
        with pytest.raises(SaasPaymentV2AdapterError) as exc_info:
            prepare_saas_v2_vbank_from_quote(sb, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc_info.value.code == "VBANK_NOT_SUPPORTED_FOR_RECURRING"


# ── VB11-VB13: Quote validation errors ────────────────────────────────────────

def test_VB11_quote_not_found():
    """VB11: missing quote → QUOTE_NOT_FOUND."""
    from services.saas_payment_v2_adapter import prepare_saas_v2_vbank_from_quote, SaasPaymentV2AdapterError
    with patch("services.member_quote_svc.get_member_quote", return_value=None):
        with pytest.raises(SaasPaymentV2AdapterError) as exc_info:
            prepare_saas_v2_vbank_from_quote(_make_sb(), _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc_info.value.code == "QUOTE_NOT_FOUND"


def test_VB12_quote_not_owned():
    """VB12: company_id mismatch → QUOTE_NOT_OWNED."""
    from services.saas_payment_v2_adapter import prepare_saas_v2_vbank_from_quote, SaasPaymentV2AdapterError
    quote = _make_quote(company_id="OTHER-COMPANY")
    with patch("services.member_quote_svc.get_member_quote", return_value=quote):
        with pytest.raises(SaasPaymentV2AdapterError) as exc_info:
            prepare_saas_v2_vbank_from_quote(_make_sb(), _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc_info.value.code == "QUOTE_NOT_OWNED"


def test_VB13_quote_not_issued():
    """VB13: status_code != ISSUED → QUOTE_NOT_ISSUED."""
    from services.saas_payment_v2_adapter import prepare_saas_v2_vbank_from_quote, SaasPaymentV2AdapterError
    quote = _make_quote(status="DRAFT")
    with patch("services.member_quote_svc.get_member_quote", return_value=quote):
        with pytest.raises(SaasPaymentV2AdapterError) as exc_info:
            prepare_saas_v2_vbank_from_quote(_make_sb(), _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc_info.value.code == "QUOTE_NOT_ISSUED"


# ── VB14: Legacy VBANK still blocks SAAS ──────────────────────────────────────

def test_VB14_legacy_vbank_prepare_body_rejects_saas():
    """VB14: VbankPrepareBody.validate_vbank_product still rejects product_type=SAAS."""
    from pydantic import ValidationError
    from schemas.payment import VbankPrepareBody
    with pytest.raises((ValidationError, ValueError)):
        VbankPrepareBody(
            product_type="SAAS",
            amount=110000,
            goodname="test",
        )


# ── VB15-VB16: VBANK callback → existing runtime reuse ────────────────────────

def test_VB15_process_vbank_deposit_calls_on_payment_success_sync():
    """VB15: process_vbank_deposit → on_payment_success_sync (shared with CARD)."""
    from services import payment_svc

    sb = MagicMock()
    payment_row = {
        "id": _PAY_ID,
        "status_code": "PENDING",
        "user_id": _USER_ID,
        "company_id": _COMPANY_ID,
        "total_amount": _TOTAL,
        "product_type": "SAAS",
        "matching_contract_id": None,
    }
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[payment_row]
    )
    sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    called_with = []
    def _fake_sync(pid):
        called_with.append(pid)

    with (
        patch("services.payment_svc.get_supabase", return_value=sb),
        patch("services.payment_svc.now_iso", return_value="2026-10-02T00:00:00+09:00"),
        patch("services.payment_post_process.on_payment_success_sync", side_effect=_fake_sync),
    ):
        payment_svc.process_vbank_deposit(_ORDER_ID, "00", "테스트예금주", {})

    assert _PAY_ID in called_with


def test_VB16_on_payment_success_sync_routes_saas_vbank_to_initial_runtime():
    """VB16: on_payment_success_sync with product_type=SAAS, payment_type=VBANK → apply_saas_v2_initial_payment_runtime."""
    from services.payment_post_process import on_payment_success_sync

    payment_row = {
        "id": _PAY_ID,
        "status_code": "SUCCESS",
        "product_type": "SAAS",
        "payment_type": "VBANK",
        "user_id": _USER_ID,
        "company_id": _COMPANY_ID,
        "quote_id": _QUOTE_ID,
        "plan_code": None,
        "contract_id": None,
        "total_amount": _TOTAL,
    }
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[payment_row]
    )

    runtime_called = []
    def _fake_runtime(sb, pay):
        runtime_called.append(pay["payment_type"])
        return {"status": "APPLIED"}

    with (
        patch("services.payment_post_process.get_supabase", return_value=sb),
        patch("services.payment_post_process._bootstrap_buyer_company_admin"),
        patch("services.payment_post_process._fire_automation"),
        patch("services.payment_post_process.send_payment_notification"),
        patch(
            "services.saas_initial_payment_runtime_v2.apply_saas_v2_initial_payment_runtime",
            side_effect=_fake_runtime,
        ),
    ):
        on_payment_success_sync(_PAY_ID)

    assert "VBANK" in runtime_called


# ── VB17: V3 activation predicate trusts VBANK quote ──────────────────────────

def test_VB17_is_commercial_v3_saas_payment_true_for_vbank():
    """VB17: VBANK payment with valid SAAS quote passes _is_commercial_v3_saas_payment."""
    from services.payment_post_process import _is_commercial_v3_saas_payment
    from schemas.saas_quote_v2 import SAAS_QUOTE_SCHEMA_VERSION

    pay = {
        "id": _PAY_ID,
        "product_type": "SAAS",
        "payment_type": "VBANK",
        "company_id": _COMPANY_ID,
        "quote_id": _QUOTE_ID,
    }
    quote_row = {
        "id": _QUOTE_ID,
        "company_id": _COMPANY_ID,
        "source": "member_auto",
        "service_type": "SAAS",
        "items": [{"quote_schema_version": SAAS_QUOTE_SCHEMA_VERSION}],
    }
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[quote_row]
    )
    assert _is_commercial_v3_saas_payment(sb, pay) is True


# ── VB18: CARD adapter regression ─────────────────────────────────────────────

def test_VB18_card_adapter_find_existing_unaffected():
    """VB18: _find_existing_v2_payment still filters payment_type=CARD (unaffected by VBANK addition)."""
    from services.saas_payment_v2_adapter import _find_existing_v2_payment

    sb = MagicMock()
    # Expect CARD filter still in place
    chain = sb.table.return_value.select.return_value
    chain.eq.return_value.eq.return_value.eq.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

    result = _find_existing_v2_payment(sb, _QUOTE_ID)
    assert result is None

    # Verify payment_type=CARD was passed in the third .eq call of the chain
    # chain: select → .eq(quote_id) → .eq(product_type) → .eq(payment_type="CARD")
    third_eq_call = chain.eq.return_value.eq.return_value.eq.call_args
    assert third_eq_call is not None
    call_str = str(third_eq_call)
    assert "CARD" in call_str
