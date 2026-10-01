"""WO-COMM-V3-RECURRING-SCHEDULER-TRIGGER-PATCH-004 — P4 tests.

Coverage:
  P4-M01-M08  PATCH4-A: manual V3 billing_charge post-process outcome
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("INICIS_BILLING_MID", "test-mid")
os.environ.setdefault("INICIS_BILLING_SIGN_KEY", "test-sk")
os.environ.setdefault("INICIS_BILLING_INIAPI_KEY", "test-ik")
os.environ.setdefault("INICIS_CLIENT_IP", "1.2.3.4")

_KST = timezone(timedelta(hours=9))
_NOW = datetime(2026, 10, 1, 10, 0, 0, tzinfo=_KST)

_SUB_ID = str(uuid.uuid4())
_BK_ID = str(uuid.uuid4())
_PAY_ID = str(uuid.uuid4())
_CT_ID = str(uuid.uuid4())
_QUOTE_ID = str(uuid.uuid4())

_BASE_SUB = {
    "id": _SUB_ID, "status": "ACTIVE", "product_type": "SAAS",
    "next_billing_at": "2026-10-01T00:00:00+09:00",
    "billing_key_id": _BK_ID,
    "amount": 110000, "supply_amount": 100000, "vat_amount": 10000,
    "user_id": str(uuid.uuid4()),
}
_BASE_BK = {"id": _BK_ID, "status": "ACTIVE", "bill_key": "bk-secret", "mid": "test-mid"}

_ELIGIBLE_CTX = {
    "eligible": True, "reason_code": "OK",
    "subscription": _BASE_SUB,
    "billing_key_row": _BASE_BK,
    "contract_id": _CT_ID, "quote_id": _QUOTE_ID,
    "charge_cycle": 2,
}


def _make_sb(product_type="SAAS"):
    """Minimal supabase mock for billing_charge initial sub read + payments lookup."""
    sub = {**_BASE_SUB, "product_type": product_type}
    sb = MagicMock()

    sub_t = MagicMock()
    sub_t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[sub])

    pay_t = MagicMock()
    pay_t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"contract_id": _CT_ID}]
    )
    pay_t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    bk_t = MagicMock()
    bk_t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[_BASE_BK])

    def _table(name):
        if name == "subscriptions":
            return sub_t
        if name == "payments":
            return pay_t
        if name == "billing_keys":
            return bk_t
        return MagicMock()

    sb.table.side_effect = _table
    return sb


def _call_billing_charge(sb, *, charge_cycle=None, product_type="SAAS"):
    from routers.payment_billing import billing_charge, BillingChargeBody
    body = BillingChargeBody(subscription_id=_SUB_ID, charge_cycle=charge_cycle)
    with patch("routers.payment_billing.get_supabase", return_value=sb):
        return billing_charge(body)


# ── P4-M01: V3 monetary fail → existing failed response ──────────────────────


def test_P4_M01_v3_monetary_fail_returns_failed_status():
    """P4-M01: INICIS charge fails → status=failed, no post_process field."""
    sb = _make_sb()
    with (
        patch("services.saas_recurring_billing_scheduler.build_v3_recurring_charge_context",
              return_value=_ELIGIBLE_CTX),
        patch("routers.payment_billing._charge_subscription_once",
              return_value={"success": False, "payment_id": _PAY_ID, "result": {"msg": "card_declined"}}),
        patch("services.payment_post_process.on_payment_success_sync") as mock_pp,
    ):
        result = _call_billing_charge(sb)

    assert result["status"] == "failed"
    assert "post_process" not in result["data"]
    mock_pp.assert_not_called()


# ── P4-M02: charge success + postprocess success → full success ──────────────


def test_P4_M02_charge_success_postprocess_success_is_full_success():
    """P4-M02: charge OK + postprocess OK → status=success."""
    sb = _make_sb()
    with (
        patch("services.saas_recurring_billing_scheduler.build_v3_recurring_charge_context",
              return_value=_ELIGIBLE_CTX),
        patch("routers.payment_billing._charge_subscription_once",
              return_value={"success": True, "payment_id": _PAY_ID, "result": {}}),
        patch("services.payment_post_process.on_payment_success_sync"),
        patch("routers.payment_billing._align_v3_subscription_next_billing_to_contract_end"),
    ):
        result = _call_billing_charge(sb)

    assert result["status"] == "success"
    assert result["data"]["payment_id"] == _PAY_ID
    assert "post_process" not in result["data"]


# ── P4-M03: charge success + postprocess exception → POST_PROCESS_FAILED ─────


def test_P4_M03_charge_success_postprocess_exception_is_post_process_failed():
    """P4-M03: charge OK + on_payment_success_sync raises → status=partial, POST_PROCESS_FAILED."""
    sb = _make_sb()
    with (
        patch("services.saas_recurring_billing_scheduler.build_v3_recurring_charge_context",
              return_value=_ELIGIBLE_CTX),
        patch("routers.payment_billing._charge_subscription_once",
              return_value={"success": True, "payment_id": _PAY_ID, "result": {}}),
        patch("services.payment_post_process.on_payment_success_sync",
              side_effect=RuntimeError("renewal chain error")),
    ):
        result = _call_billing_charge(sb)

    assert result["status"] == "partial"
    assert result["data"]["post_process"] == "FAILED"
    assert result["data"]["reason_code"] == "POST_PROCESS_FAILED"


# ── P4-M04: P4-M03 charge call count = 1 ────────────────────────────────────


def test_P4_M04_charge_called_exactly_once_on_postprocess_failure():
    """P4-M04: exactly one _charge_subscription_once call when post-process fails."""
    sb = _make_sb()
    with (
        patch("services.saas_recurring_billing_scheduler.build_v3_recurring_charge_context",
              return_value=_ELIGIBLE_CTX),
        patch("routers.payment_billing._charge_subscription_once",
              return_value={"success": True, "payment_id": _PAY_ID, "result": {}}) as mock_charge,
        patch("services.payment_post_process.on_payment_success_sync",
              side_effect=RuntimeError("renewal chain error")),
    ):
        _call_billing_charge(sb)

    mock_charge.assert_called_once()


# ── P4-M05: P4-M03 payment_id retained ──────────────────────────────────────


def test_P4_M05_payment_id_retained_on_postprocess_failure():
    """P4-M05: payment_id present in POST_PROCESS_FAILED response."""
    sb = _make_sb()
    with (
        patch("services.saas_recurring_billing_scheduler.build_v3_recurring_charge_context",
              return_value=_ELIGIBLE_CTX),
        patch("routers.payment_billing._charge_subscription_once",
              return_value={"success": True, "payment_id": _PAY_ID, "result": {}}),
        patch("services.payment_post_process.on_payment_success_sync",
              side_effect=RuntimeError("renewal chain error")),
    ):
        result = _call_billing_charge(sb)

    assert result["data"]["payment_id"] == _PAY_ID
    assert result["data"]["payment_charged"] is True


# ── P4-M06: alignment failure → POST_PROCESS_FAILED ─────────────────────────


def test_P4_M06_alignment_failure_is_post_process_failed():
    """P4-M06: on_payment_success_sync OK but alignment raises → POST_PROCESS_FAILED."""
    sb = _make_sb()
    with (
        patch("services.saas_recurring_billing_scheduler.build_v3_recurring_charge_context",
              return_value=_ELIGIBLE_CTX),
        patch("routers.payment_billing._charge_subscription_once",
              return_value={"success": True, "payment_id": _PAY_ID, "result": {}}),
        patch("services.payment_post_process.on_payment_success_sync"),
        patch("routers.payment_billing._align_v3_subscription_next_billing_to_contract_end",
              side_effect=ValueError("contract end_date missing")),
    ):
        result = _call_billing_charge(sb)

    assert result["status"] == "partial"
    assert result["data"]["post_process"] == "FAILED"
    assert result["data"]["reason_code"] == "POST_PROCESS_FAILED"


# ── P4-M07: retry_charge = False in POST_PROCESS_FAILED ─────────────────────


def test_P4_M07_retry_charge_false_on_postprocess_failure():
    """P4-M07: caller must not be instructed to retry monetary charge."""
    sb = _make_sb()
    with (
        patch("services.saas_recurring_billing_scheduler.build_v3_recurring_charge_context",
              return_value=_ELIGIBLE_CTX),
        patch("routers.payment_billing._charge_subscription_once",
              return_value={"success": True, "payment_id": _PAY_ID, "result": {}}),
        patch("services.payment_post_process.on_payment_success_sync",
              side_effect=RuntimeError("renewal chain error")),
    ):
        result = _call_billing_charge(sb)

    assert result["data"]["retry_charge"] is False


# ── P4-M08: legacy non-SAAS response semantics unchanged ────────────────────


def test_P4_M08_legacy_non_saas_response_unchanged():
    """P4-M08: non-SAAS product_type → standard success/failed response, no post_process."""
    sb = _make_sb(product_type="PROCESS")
    with (
        patch("services.saas_recurring_billing_scheduler.build_v3_recurring_charge_context") as mock_ctx,
        patch("routers.payment_billing._charge_subscription_once",
              return_value={"success": True, "payment_id": _PAY_ID, "result": {}}),
    ):
        result = _call_billing_charge(sb, charge_cycle=2, product_type="PROCESS")

    mock_ctx.assert_not_called()
    assert result["status"] == "success"
    assert "post_process" not in result["data"]
    assert "payment_charged" not in result["data"]
