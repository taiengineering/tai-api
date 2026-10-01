"""WO-COMM-V3-RECURRING-SCHEDULER-TRIGGER-PATCH-003 — patch3 tests.

Coverage:
  T01-T10  Contract boundary temporal authority (build_v3_recurring_charge_context)
  O01      Outage scheduler — scheduler fires at/after contract_end_boundary → zero charges
  M01-M06  Manual route convergence (billing_charge V3 SAAS uses build_v3_recurring_charge_context)
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

_SUB_ID = str(uuid.uuid4())
_BK_ID = str(uuid.uuid4())
_PAY_ID = str(uuid.uuid4())
_CT_ID = str(uuid.uuid4())
_QUOTE_ID = str(uuid.uuid4())

# Base fixture: contract end_date=2026-11-01 → contract_end_boundary=Nov 1 midnight KST
#               contract_due_at = Oct 31 midnight KST
# sub next_billing_at = "2026-10-31T00:00:00+09:00" = contract_due_at ✓
_BASE_SUB = {
    "id": _SUB_ID, "status": "ACTIVE", "product_type": "SAAS",
    "next_billing_at": "2026-10-31T00:00:00+09:00",
    "billing_key_id": _BK_ID,
    "amount": 110000, "supply_amount": 100000, "vat_amount": 10000,
    "user_id": str(uuid.uuid4()),
}
_BASE_BK = {"id": _BK_ID, "status": "ACTIVE", "bill_key": "bk-secret", "mid": "test-mid"}
_BASE_PAY = {
    "id": _PAY_ID, "charge_cycle": 1, "status_code": "SUCCESS",
    "quote_id": _QUOTE_ID, "contract_id": _CT_ID,
}
_BASE_CONTRACT = {
    "id": _CT_ID, "status_code": "ACTIVE", "service_type": "SAAS",
    "is_active": True, "end_date": "2026-11-01",
}


# ── Mock helpers ──────────────────────────────────────────────────────────────

def _make_ctx_sb(*, sub=None, bk=None, pays=None, contract=None):
    """Build supabase mock for build_v3_recurring_charge_context tests."""
    sb = MagicMock()

    def _table(name):
        if name == "subscriptions":
            t = MagicMock()
            data = [sub] if sub else []
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=data)
            return t
        if name == "billing_keys":
            t = MagicMock()
            data = [bk] if bk else []
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=data)
            return t
        if name == "payments":
            t = MagicMock()
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=pays or [])
            return t
        if name == "contracts":
            t = MagicMock()
            data = [contract] if contract else []
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=data)
            return t
        return MagicMock()

    sb.table.side_effect = _table
    return sb


def _ctx(*, sub=None, bk=None, pays=None, contract=None, now=None):
    """Call build_v3_recurring_charge_context with defaults."""
    from services.saas_recurring_billing_scheduler import build_v3_recurring_charge_context
    s = sub if sub is not None else _BASE_SUB
    b = bk if bk is not None else _BASE_BK
    p = pays if pays is not None else [_BASE_PAY]
    c = contract if contract is not None else _BASE_CONTRACT
    n = now if now is not None else datetime(2026, 10, 31, 12, 0, 0, tzinfo=_KST)
    sb = _make_ctx_sb(sub=s, bk=b, pays=p, contract=c)
    return build_v3_recurring_charge_context(sb, _SUB_ID, n)


def _make_billing_charge_sb(sub_override=None):
    """Minimal supabase mock for billing_charge() initial subscription read."""
    sub = {**_BASE_SUB, **(sub_override or {})}
    sb = MagicMock()
    sub_t = MagicMock()
    sub_t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[sub])
    bk_t = MagicMock()
    bk_t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[_BASE_BK])

    def _table(name):
        if name == "subscriptions":
            return sub_t
        if name == "billing_keys":
            return bk_t
        return MagicMock()

    sb.table.side_effect = _table
    return sb


def _make_full_sb(*, sub=None):
    """Full supabase mock for run_due_saas_recurring_billing (O01)."""
    s = sub if sub is not None else _BASE_SUB
    sb = MagicMock()

    def _table(name):
        if name == "subscriptions":
            t = MagicMock()
            # Scan chain
            scan_c = t.select.return_value
            first_eq_rv = scan_c.eq.return_value
            first_eq_rv.eq.return_value.not_.is_.return_value.lte.return_value.not_.is_.return_value.order.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[s]
            )
            # Fresh chain (argument-aware)
            class _Cap:
                last_id = None
            cap = _Cap()

            def _eq_se(field, value=None):
                if field == "id":
                    cap.last_id = value
                return first_eq_rv

            scan_c.eq.side_effect = _eq_se

            def _fresh_exec():
                return MagicMock(data=[s] if cap.last_id == _SUB_ID else [])

            first_eq_rv.limit.return_value.execute.side_effect = _fresh_exec
            return t
        if name == "billing_keys":
            t = MagicMock()
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[_BASE_BK])
            return t
        if name == "payments":
            t = MagicMock()
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[_BASE_PAY])
            return t
        if name == "contracts":
            t = MagicMock()
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[_BASE_CONTRACT])
            return t
        return MagicMock()

    sb.table.side_effect = _table
    return sb


# ── T01-T10: Contract boundary temporal authority ─────────────────────────────


def test_T01_now_equals_due_at_is_eligible():
    """T01: now == contract_due_at → eligible."""
    now = datetime(2026, 10, 31, 0, 0, 0, tzinfo=_KST)
    sub = {**_BASE_SUB, "next_billing_at": "2026-10-31T00:00:00+09:00"}
    ctx = _ctx(sub=sub, now=now)
    assert ctx["eligible"] is True


def test_T02_now_between_due_and_end_is_eligible():
    """T02: due_at < now < contract_end_boundary → eligible."""
    now = datetime(2026, 10, 31, 12, 0, 0, tzinfo=_KST)
    sub = {**_BASE_SUB, "next_billing_at": "2026-10-31T00:00:00+09:00"}
    ctx = _ctx(sub=sub, now=now)
    assert ctx["eligible"] is True


def test_T03_now_before_due_at_is_not_due():
    """T03: now < contract_due_at → CONTRACT_NOT_DUE."""
    now = datetime(2026, 10, 30, 23, 59, 0, tzinfo=_KST)
    sub = {**_BASE_SUB, "next_billing_at": "2026-10-31T00:00:00+09:00"}
    ctx = _ctx(sub=sub, now=now)
    assert ctx["eligible"] is False
    assert ctx["reason_code"] == "CONTRACT_NOT_DUE"


def test_T04_now_at_boundary_is_expired():
    """T04: now == contract_end_boundary → CONTRACT_EXPIRED_FOR_RECURRING."""
    now = datetime(2026, 11, 1, 0, 0, 0, tzinfo=_KST)
    sub = {**_BASE_SUB, "next_billing_at": "2026-10-31T00:00:00+09:00"}
    ctx = _ctx(sub=sub, now=now)
    assert ctx["eligible"] is False
    assert ctx["reason_code"] == "CONTRACT_EXPIRED_FOR_RECURRING"


def test_T05_now_after_boundary_is_expired():
    """T05: now > contract_end_boundary → CONTRACT_EXPIRED_FOR_RECURRING."""
    now = datetime(2026, 11, 1, 1, 0, 0, tzinfo=_KST)
    sub = {**_BASE_SUB, "next_billing_at": "2026-10-31T00:00:00+09:00"}
    ctx = _ctx(sub=sub, now=now)
    assert ctx["eligible"] is False
    assert ctx["reason_code"] == "CONTRACT_EXPIRED_FOR_RECURRING"


def test_T06_sub_due_earlier_than_contract_due_is_mismatch():
    """T06: subscription due earlier than contract due → SCHEDULE_CONTRACT_MISMATCH."""
    now = datetime(2026, 10, 31, 12, 0, 0, tzinfo=_KST)  # in eligible window
    sub = {**_BASE_SUB, "next_billing_at": "2026-10-30T00:00:00+09:00"}  # earlier than Oct 31
    ctx = _ctx(sub=sub, now=now)
    assert ctx["eligible"] is False
    assert ctx["reason_code"] == "SCHEDULE_CONTRACT_MISMATCH"


def test_T07_sub_due_later_than_contract_due_is_mismatch():
    """T07: subscription due later than contract due → SCHEDULE_CONTRACT_MISMATCH."""
    now = datetime(2026, 10, 31, 15, 0, 0, tzinfo=_KST)  # after noon, in eligible window
    sub = {**_BASE_SUB, "next_billing_at": "2026-10-31T12:00:00+09:00"}  # noon, not midnight
    ctx = _ctx(sub=sub, now=now)
    assert ctx["eligible"] is False
    assert ctx["reason_code"] == "SCHEDULE_CONTRACT_MISMATCH"


def test_T08_utc_kst_offset_equivalent_is_eligible():
    """T08: UTC offset-equivalent nba_dt == contract_due_at → eligible."""
    now = datetime(2026, 10, 31, 12, 0, 0, tzinfo=_KST)
    # 2026-10-30T15:00:00+00:00 == 2026-10-31T00:00:00+09:00 (same instant)
    sub = {**_BASE_SUB, "next_billing_at": "2026-10-30T15:00:00+00:00"}
    ctx = _ctx(sub=sub, now=now)
    assert ctx["eligible"] is True


def test_T09_malformed_contract_end_date_fails_closed():
    """T09: malformed contract.end_date → CONTRACT_END_DATE_INVALID."""
    now = datetime(2026, 10, 31, 12, 0, 0, tzinfo=_KST)
    bad_contract = {**_BASE_CONTRACT, "end_date": "not-a-date"}
    ctx = _ctx(
        sub={**_BASE_SUB, "next_billing_at": "2026-10-31T00:00:00+09:00"},
        contract=bad_contract,
        now=now,
    )
    assert ctx["eligible"] is False
    assert ctx["reason_code"] == "CONTRACT_END_DATE_INVALID"


def test_T10_naive_sub_next_billing_fails_closed():
    """T10: naive nba_dt → NEXT_BILLING_AT_INVALID."""
    now = datetime(2026, 10, 31, 12, 0, 0, tzinfo=_KST)
    sub = {**_BASE_SUB, "next_billing_at": "2026-10-31T00:00:00"}  # no tz
    ctx = _ctx(sub=sub, now=now)
    assert ctx["eligible"] is False
    assert ctx["reason_code"] == "NEXT_BILLING_AT_INVALID"


# ── O01: Outage scenario ──────────────────────────────────────────────────────


def test_O01_outage_scheduler_at_end_boundary_zero_charges():
    """O01: scheduler fires at/after contract_end_boundary → zero charges."""
    from services.saas_recurring_billing_scheduler import run_due_saas_recurring_billing

    outage_now = datetime(2026, 11, 1, 0, 0, 0, tzinfo=_KST)  # == contract_end_boundary
    # contract end_date=2026-11-01, due=Oct 31 midnight
    sub = {**_BASE_SUB, "next_billing_at": "2026-10-31T00:00:00+09:00"}

    sb = _make_full_sb(sub=sub)
    with (
        patch("db.supabase_client.get_supabase", return_value=sb),
        patch("services.saas_recurring_billing_scheduler.now_kst", return_value=outage_now),
        patch("services.saas_recurring_billing_scheduler.serialize_business_datetime",
              return_value="2026-11-01T00:00:00+09:00"),
        patch("routers.payment_billing._charge_subscription_once") as mock_charge,
    ):
        result = run_due_saas_recurring_billing({"dry_run": True})

    mock_charge.assert_not_called()
    assert result["scanned"] == 1
    assert result["eligible"] == 0
    assert result["items"][0]["reason_code"] == "CONTRACT_EXPIRED_FOR_RECURRING"


# ── M01-M06: Manual route convergence ────────────────────────────────────────


def test_M01_v3_manual_calls_shared_fresh_context():
    """M01: V3 SAAS manual route calls build_v3_recurring_charge_context."""
    from routers.payment_billing import billing_charge, BillingChargeBody
    body = BillingChargeBody(subscription_id=_SUB_ID, charge_cycle=None)

    mock_ctx = {
        "eligible": True, "reason_code": "OK",
        "subscription": {**_BASE_SUB, "product_type": "SAAS"},
        "billing_key_row": _BASE_BK,
        "contract_id": _CT_ID, "quote_id": _QUOTE_ID,
        "charge_cycle": 2,
    }
    with (
        patch("routers.payment_billing.get_supabase", return_value=_make_billing_charge_sb()),
        patch("services.saas_recurring_billing_scheduler.build_v3_recurring_charge_context",
              return_value=mock_ctx) as mock_ctx_fn,
        patch("routers.payment_billing._charge_subscription_once",
              return_value={"success": False, "payment_id": None, "result": {}}),
    ):
        billing_charge(body)

    mock_ctx_fn.assert_called_once()


def test_M02_v3_manual_early_charge_is_409():
    """M02: V3 manual before contract due → 409, zero charge."""
    from fastapi import HTTPException
    from routers.payment_billing import billing_charge, BillingChargeBody
    body = BillingChargeBody(subscription_id=_SUB_ID, charge_cycle=None)

    mock_ctx = {"eligible": False, "reason_code": "CONTRACT_NOT_DUE"}
    with (
        patch("routers.payment_billing.get_supabase", return_value=_make_billing_charge_sb()),
        patch("services.saas_recurring_billing_scheduler.build_v3_recurring_charge_context",
              return_value=mock_ctx),
        patch("routers.payment_billing._charge_subscription_once") as mock_charge,
    ):
        with pytest.raises(HTTPException) as exc_info:
            billing_charge(body)

    mock_charge.assert_not_called()
    assert exc_info.value.status_code == 409
    assert "CONTRACT_NOT_DUE" in exc_info.value.detail


def test_M03_v3_manual_after_boundary_is_409():
    """M03: V3 manual after contract_end_boundary → 409, zero charge."""
    from fastapi import HTTPException
    from routers.payment_billing import billing_charge, BillingChargeBody
    body = BillingChargeBody(subscription_id=_SUB_ID, charge_cycle=None)

    mock_ctx = {"eligible": False, "reason_code": "CONTRACT_EXPIRED_FOR_RECURRING"}
    with (
        patch("routers.payment_billing.get_supabase", return_value=_make_billing_charge_sb()),
        patch("services.saas_recurring_billing_scheduler.build_v3_recurring_charge_context",
              return_value=mock_ctx),
        patch("routers.payment_billing._charge_subscription_once") as mock_charge,
    ):
        with pytest.raises(HTTPException) as exc_info:
            billing_charge(body)

    mock_charge.assert_not_called()
    assert exc_info.value.status_code == 409
    assert "CONTRACT_EXPIRED_FOR_RECURRING" in exc_info.value.detail


def test_M04_v3_manual_due_uses_ctx_charge_cycle():
    """M04: V3 manual due → _charge_subscription_once called with ctx.charge_cycle."""
    from routers.payment_billing import billing_charge, BillingChargeBody
    body = BillingChargeBody(subscription_id=_SUB_ID, charge_cycle=None)

    mock_ctx = {
        "eligible": True, "reason_code": "OK",
        "subscription": {**_BASE_SUB, "product_type": "SAAS"},
        "billing_key_row": _BASE_BK,
        "contract_id": _CT_ID, "quote_id": _QUOTE_ID,
        "charge_cycle": 3,
    }
    with (
        patch("routers.payment_billing.get_supabase", return_value=_make_billing_charge_sb()),
        patch("services.saas_recurring_billing_scheduler.build_v3_recurring_charge_context",
              return_value=mock_ctx),
        patch("routers.payment_billing._charge_subscription_once",
              return_value={"success": False, "payment_id": None, "result": {}}) as mock_charge,
    ):
        billing_charge(body)

    assert mock_charge.call_args.kwargs["charge_cycle"] == 3


def test_M05_caller_charge_cycle_cannot_override_v3():
    """M05: caller-provided charge_cycle=5 ignored; ctx.charge_cycle=2 used."""
    from routers.payment_billing import billing_charge, BillingChargeBody
    body = BillingChargeBody(subscription_id=_SUB_ID, charge_cycle=5)  # caller says 5

    mock_ctx = {
        "eligible": True, "reason_code": "OK",
        "subscription": {**_BASE_SUB, "product_type": "SAAS"},
        "billing_key_row": _BASE_BK,
        "contract_id": _CT_ID, "quote_id": _QUOTE_ID,
        "charge_cycle": 2,  # server authority says 2
    }
    with (
        patch("routers.payment_billing.get_supabase", return_value=_make_billing_charge_sb()),
        patch("services.saas_recurring_billing_scheduler.build_v3_recurring_charge_context",
              return_value=mock_ctx),
        patch("routers.payment_billing._charge_subscription_once",
              return_value={"success": False, "payment_id": None, "result": {}}) as mock_charge,
    ):
        billing_charge(body)

    used_cycle = mock_charge.call_args.kwargs.get("charge_cycle") or mock_charge.call_args.args[3]
    assert used_cycle == 2
    assert used_cycle != 5


def test_M06_legacy_route_does_not_call_v3_context():
    """M06: legacy (non-SAAS) product_type → build_v3_recurring_charge_context NOT called."""
    from routers.payment_billing import billing_charge, BillingChargeBody
    body = BillingChargeBody(subscription_id=_SUB_ID, charge_cycle=2)

    sb = _make_billing_charge_sb(sub_override={"product_type": "PROCESS"})
    with (
        patch("routers.payment_billing.get_supabase", return_value=sb),
        patch("services.saas_recurring_billing_scheduler.build_v3_recurring_charge_context") as mock_ctx_fn,
        patch("routers.payment_billing._charge_subscription_once",
              return_value={"success": False, "payment_id": None, "result": {}}),
    ):
        billing_charge(body)

    mock_ctx_fn.assert_not_called()
