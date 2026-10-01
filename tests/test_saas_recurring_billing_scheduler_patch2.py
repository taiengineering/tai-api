"""WO-COMM-V3-RECURRING-SCHEDULER-TRIGGER-PATCH-002 — patch2 tests.

Coverage:
  A01-A04  PATCH2-A: contract-end next_billing alignment
  F01-F06  PATCH2-B: fresh monetary authority
  C01-C04  PATCH2-C: single cycle authority
  D01-D06  PATCH2-E: dispatcher safe exception detail
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
_PAST = datetime(2026, 10, 1, 9, 0, 0, tzinfo=_KST)

_SUB_ID = str(uuid.uuid4())
_BK_ID = str(uuid.uuid4())
_PAY_ID = str(uuid.uuid4())
_CT_ID = str(uuid.uuid4())
_QUOTE_ID = str(uuid.uuid4())

_BASE_SUB = {
    "id": _SUB_ID,
    "status": "ACTIVE",
    "product_type": "SAAS",
    "next_billing_at": "2026-10-01T00:00:00+09:00",  # contract_due_at = Oct 1 midnight KST (end_date Oct 2 - 1 day)
    "billing_key_id": _BK_ID,
    "amount": 110000,
    "supply_amount": 100000,
    "vat_amount": 10000,
    "user_id": str(uuid.uuid4()),
}

_BASE_BK = {"id": _BK_ID, "status": "ACTIVE", "bill_key": "bk-secret", "mid": "test-mid"}
_BASE_PAY = {
    "id": _PAY_ID, "charge_cycle": 1, "status_code": "SUCCESS",
    "quote_id": _QUOTE_ID, "contract_id": _CT_ID,
}
_BASE_CONTRACT = {
    "id": _CT_ID, "status_code": "ACTIVE", "service_type": "SAAS",
    "is_active": True, "end_date": "2026-10-02",  # contract_due_at = Oct 1 midnight KST; _NOW (Oct 1 10am) is in window
}

_MOCK_SUMMARY = {
    "dry_run": False,
    "scanned": 1,
    "eligible": 1,
    "charged_success": 1,
    "charged_failed": 0,
    "post_process_failed": 1,
    "skipped": 0,
    "errors": 0,
    "items": [
        {
            "subscription_id": _SUB_ID,
            "payment_id": _PAY_ID,
            "reason_code": "POST_PROCESS_FAILED",
            "charged": True,
            "eligible": True,
        }
    ],
}


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _make_contracts_mock(contracts):
    t = MagicMock()
    t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=contracts)
    return t


def _make_sub_update_mock():
    """Mock for subscriptions.update().eq().execute()."""
    t = MagicMock()
    t.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    return t


def _build_align_supabase(end_date: str, sub_id: str = _SUB_ID, contract_id: str = _CT_ID):
    """Build a minimal supabase mock for alignment tests."""
    sb = MagicMock()

    def _table(name):
        if name == "contracts":
            t = MagicMock()
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[{"end_date": end_date}]
            )
            return t
        if name == "subscriptions":
            t = MagicMock()
            t.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            return t
        return MagicMock()

    sb.table.side_effect = _table
    return sb


# ── A01-A04: Billing date alignment ──────────────────────────────────────────


def test_A01_contract_end_nov01_aligns_oct31():
    """A01: contract end_date=2026-11-01 → aligned=2026-10-31T00:00:00+09:00."""
    from routers.payment_billing import _align_v3_subscription_next_billing_to_contract_end
    sb = _build_align_supabase("2026-11-01")
    result = _align_v3_subscription_next_billing_to_contract_end(sb, _SUB_ID, _CT_ID)
    assert result == "2026-10-31T00:00:00+09:00"


def test_A02_contract_end_dec01_aligns_nov30():
    """A02: contract end_date=2026-12-01 → aligned=2026-11-30T00:00:00+09:00 (NOT 2026-11-29)."""
    from routers.payment_billing import _align_v3_subscription_next_billing_to_contract_end
    sb = _build_align_supabase("2026-12-01")
    result = _align_v3_subscription_next_billing_to_contract_end(sb, _SUB_ID, _CT_ID)
    assert result == "2026-11-30T00:00:00+09:00"


def test_A03_contract_end_jan01_aligns_dec31():
    """A03: contract end_date=2027-01-01 → aligned=2026-12-31T00:00:00+09:00."""
    from routers.payment_billing import _align_v3_subscription_next_billing_to_contract_end
    sb = _build_align_supabase("2027-01-01")
    result = _align_v3_subscription_next_billing_to_contract_end(sb, _SUB_ID, _CT_ID)
    assert result == "2026-12-31T00:00:00+09:00"


def test_A04_month_end_boundaries():
    """A04: various month-end and leap-year boundaries."""
    from routers.payment_billing import _align_v3_subscription_next_billing_to_contract_end

    cases = [
        # (end_date, expected_aligned)
        ("2026-03-01", "2026-02-28T00:00:00+09:00"),  # Feb boundary (not leap)
        ("2026-04-01", "2026-03-31T00:00:00+09:00"),  # March boundary
        ("2028-03-01", "2028-02-29T00:00:00+09:00"),  # Leap year Feb boundary
        ("2026-02-01", "2026-01-31T00:00:00+09:00"),  # Jan boundary
    ]
    for end_date, expected in cases:
        sb = _build_align_supabase(end_date)
        result = _align_v3_subscription_next_billing_to_contract_end(sb, _SUB_ID, _CT_ID)
        assert result == expected, f"end_date={end_date}: expected {expected}, got {result}"


# ── F01-F06: Fresh monetary authority ────────────────────────────────────────


def _make_ctx_sb(
    *,
    sub=None,
    bk=None,
    pays=None,
    contract=None,
):
    """Build supabase mock for build_v3_recurring_charge_context tests."""
    sb = MagicMock()

    def _table(name):
        if name == "subscriptions":
            t = MagicMock()
            data = [sub] if sub else []
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=data)
            t.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
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


def test_F01_fresh_read_uses_fresh_billing_key_id():
    """F01: billing_key_id changed from A to B between scan and fresh → fresh read uses B."""
    _BK_ID_B = str(uuid.uuid4())
    fresh_sub = {**_BASE_SUB, "billing_key_id": _BK_ID_B}
    fresh_bk = {**_BASE_BK, "id": _BK_ID_B}
    sb = _make_ctx_sb(sub=fresh_sub, bk=fresh_bk, pays=[_BASE_PAY], contract=_BASE_CONTRACT)

    from services.saas_recurring_billing_scheduler import build_v3_recurring_charge_context
    ctx = build_v3_recurring_charge_context(sb, _SUB_ID, _NOW)

    assert ctx["eligible"] is True
    assert ctx["billing_key_row"]["id"] == _BK_ID_B


def test_F02_fresh_billing_key_revoked_is_ineligible():
    """F02: fresh billing key status=REVOKED → BILLING_KEY_INACTIVE."""
    revoked_bk = {**_BASE_BK, "status": "REVOKED"}
    sb = _make_ctx_sb(sub=_BASE_SUB, bk=revoked_bk, pays=[_BASE_PAY], contract=_BASE_CONTRACT)

    from services.saas_recurring_billing_scheduler import build_v3_recurring_charge_context
    ctx = build_v3_recurring_charge_context(sb, _SUB_ID, _NOW)

    assert ctx["eligible"] is False
    assert ctx["reason_code"] == "BILLING_KEY_INACTIVE"


def test_F03_fresh_contract_expired_is_ineligible():
    """F03: fresh contract status_code=EXPIRED → CONTRACT_NOT_ACTIVE."""
    expired_ct = {**_BASE_CONTRACT, "status_code": "EXPIRED"}
    sb = _make_ctx_sb(sub=_BASE_SUB, bk=_BASE_BK, pays=[_BASE_PAY], contract=expired_ct)

    from services.saas_recurring_billing_scheduler import build_v3_recurring_charge_context
    ctx = build_v3_recurring_charge_context(sb, _SUB_ID, _NOW)

    assert ctx["eligible"] is False
    assert ctx["reason_code"] == "CONTRACT_NOT_ACTIVE"


def test_F04_no_cycle1_success_is_ineligible():
    """F04: all_pays has no cycle-1 SUCCESS → CYCLE1_PAYMENT_NOT_FOUND."""
    bad_pay = {**_BASE_PAY, "status_code": "FAILED"}
    sb = _make_ctx_sb(sub=_BASE_SUB, bk=_BASE_BK, pays=[bad_pay], contract=_BASE_CONTRACT)

    from services.saas_recurring_billing_scheduler import build_v3_recurring_charge_context
    ctx = build_v3_recurring_charge_context(sb, _SUB_ID, _NOW)

    assert ctx["eligible"] is False
    assert ctx["reason_code"] == "CYCLE1_PAYMENT_NOT_FOUND"


def test_F05_pending_for_computed_cycle_is_ineligible():
    """F05: all_pays has PENDING for computed cycle → PENDING_CYCLE_EXISTS."""
    pending_pay = {
        "id": str(uuid.uuid4()), "charge_cycle": 2, "status_code": "PENDING",
        "quote_id": _QUOTE_ID, "contract_id": _CT_ID,
    }
    pays = [_BASE_PAY, pending_pay]
    sb = _make_ctx_sb(sub=_BASE_SUB, bk=_BASE_BK, pays=pays, contract=_BASE_CONTRACT)

    from services.saas_recurring_billing_scheduler import build_v3_recurring_charge_context
    ctx = build_v3_recurring_charge_context(sb, _SUB_ID, _NOW)

    assert ctx["eligible"] is False
    assert ctx["reason_code"] == "PENDING_CYCLE_EXISTS"


def test_F06_dry_run_eligible_zero_charge_calls():
    """F06: dry_run=True + eligible → reason_code=DRY_RUN, zero charge calls."""
    from services.saas_recurring_billing_scheduler import run_due_saas_recurring_billing

    def _make_full_sb():
        sb = MagicMock()

        def _table(name):
            if name == "subscriptions":
                t = MagicMock()
                # Scan chain
                scan_c = t.select.return_value
                first_eq_rv = scan_c.eq.return_value
                first_eq_rv.eq.return_value.not_.is_.return_value.lte.return_value.not_.is_.return_value.order.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[_BASE_SUB]
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
                    return MagicMock(data=[_BASE_SUB] if cap.last_id == _SUB_ID else [])
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

    sb = _make_full_sb()
    with (
        patch("db.supabase_client.get_supabase", return_value=sb),
        patch("services.saas_recurring_billing_scheduler.now_kst", return_value=_NOW),
        patch("services.saas_recurring_billing_scheduler.serialize_business_datetime",
              return_value="2026-10-01T10:00:00+09:00"),
        patch("routers.payment_billing._charge_subscription_once") as mock_charge,
    ):
        result = run_due_saas_recurring_billing({"dry_run": True})

    mock_charge.assert_not_called()
    assert result["items"][0]["reason_code"] == "DRY_RUN"


# ── C01-C04: Single cycle authority ──────────────────────────────────────────


def test_C01_build_ctx_imports_v3_cycle_from_pays():
    """C01: build_v3_recurring_charge_context source imports _v3_cycle_from_pays from payment_billing."""
    import inspect
    from services import saas_recurring_billing_scheduler as m
    src = inspect.getsource(m.build_v3_recurring_charge_context)
    assert "_v3_cycle_from_pays" in src
    assert "payment_billing" in src


def test_C02_scheduler_has_no_inline_max_cycle_formula():
    """C02: scheduler module source does NOT contain inline max(successful_cycles)+1 formula."""
    import inspect
    from services import saas_recurring_billing_scheduler as m
    src = inspect.getsource(m)
    assert "max(successful_cycles) + 1" not in src


def test_C03_failed_attempt_does_not_advance_cycle():
    """C03: _v3_cycle_from_pays with FAILED attempt doesn't advance cycle."""
    from routers.payment_billing import _v3_cycle_from_pays
    pays = [
        {"charge_cycle": 1, "status_code": "SUCCESS"},
        {"charge_cycle": 2, "status_code": "FAILED"},
    ]
    # FAILED cycle-2 must not advance → next = 2
    assert _v3_cycle_from_pays(pays) == 2


def test_C04_success_advances_cycle():
    """C04: _v3_cycle_from_pays with SUCCESS advances cycle correctly."""
    from routers.payment_billing import _v3_cycle_from_pays
    pays = [
        {"charge_cycle": 1, "status_code": "SUCCESS"},
        {"charge_cycle": 2, "status_code": "SUCCESS"},
    ]
    assert _v3_cycle_from_pays(pays) == 3


# ── D01-D06: Persistent failure detail through dispatcher ─────────────────────


def _make_job(handler="direct://saas_recurring_billing"):
    from services.scheduler.store import JobRow
    return JobRow(
        job_code="SAAS_RECURRING_BILLING",
        cron_expression="0 * * * *",
        is_active=True,
        handler=handler,
        next_run_at=_PAST,
        payload={"dry_run": False},
    )


def _run_tick_with_execute(mock_execute):
    """Run tick with mocked execute_direct and now_kst. Returns (store, results)."""
    from services.scheduler.store import InMemoryStore
    from services.scheduler.dispatcher import tick
    from services.time import SYSTEM_CLOCK

    store = InMemoryStore()
    store.put_job(_make_job())

    with (
        patch("services.scheduler.dispatcher.now_kst", return_value=_NOW),
        patch("services.scheduler.dispatcher.execute_job", side_effect=mock_execute),
    ):
        results = tick(store)

    return store, results


def test_D01_saas_error_results_in_failed_status():
    """D01: execute raises SaasRecurringBillingError → tick log status=FAILED."""
    from services.saas_recurring_billing_scheduler import SaasRecurringBillingError

    def _raise_saas_error(job):
        raise SaasRecurringBillingError(_MOCK_SUMMARY)

    store, results = _run_tick_with_execute(_raise_saas_error)

    log = list(store.logs.values())[0]
    assert log["status"] == "FAILED"


def test_D02_result_detail_contains_expected_payment_id():
    """D02: result_detail["items"][0]["payment_id"] == expected payment_id."""
    from services.saas_recurring_billing_scheduler import SaasRecurringBillingError

    def _raise_saas_error(job):
        raise SaasRecurringBillingError(_MOCK_SUMMARY)

    store, _ = _run_tick_with_execute(_raise_saas_error)

    log = list(store.logs.values())[0]
    detail = log["result_detail"]
    assert detail["items"][0]["payment_id"] == _PAY_ID


def test_D03_result_detail_reason_code_post_process_failed():
    """D03: result_detail["items"][0]["reason_code"] == "POST_PROCESS_FAILED"."""
    from services.saas_recurring_billing_scheduler import SaasRecurringBillingError

    def _raise_saas_error(job):
        raise SaasRecurringBillingError(_MOCK_SUMMARY)

    store, _ = _run_tick_with_execute(_raise_saas_error)

    log = list(store.logs.values())[0]
    detail = log["result_detail"]
    assert detail["items"][0]["reason_code"] == "POST_PROCESS_FAILED"


def test_D04_result_detail_does_not_contain_sensitive_keys():
    """D04: result_detail must NOT contain bill_key, card_number, or inicis_secret."""
    from services.saas_recurring_billing_scheduler import SaasRecurringBillingError

    # Include sensitive keys in summary to verify they are stripped
    summary_with_secrets = {
        **_MOCK_SUMMARY,
        "bill_key": "SUPER_SECRET",
        "card_number": "1234-5678",
        "inicis_secret": "secret-value",
    }

    def _raise_saas_error(job):
        raise SaasRecurringBillingError(summary_with_secrets)

    store, _ = _run_tick_with_execute(_raise_saas_error)

    log = list(store.logs.values())[0]
    detail = log["result_detail"]
    detail_str = str(detail)
    assert "SUPER_SECRET" not in detail_str
    assert "1234-5678" not in detail_str
    assert "secret-value" not in detail_str
    assert "bill_key" not in detail
    assert "card_number" not in detail
    assert "inicis_secret" not in detail


def test_D05_generic_runtime_error_stores_error_string():
    """D05: RuntimeError("generic error") → status=FAILED, detail={"error": "generic error"}."""
    def _raise_runtime(job):
        raise RuntimeError("generic error")

    store, _ = _run_tick_with_execute(_raise_runtime)

    log = list(store.logs.values())[0]
    assert log["status"] == "FAILED"
    assert log["result_detail"] == {"error": "generic error"}


def test_D06_charged_failed_is_success_not_system_error():
    """D06: card decline (charged_failed>0) returned normally → status=SUCCESS."""
    def _return_charged_failed(job):
        return {
            "dry_run": False,
            "scanned": 1,
            "eligible": 1,
            "charged_success": 0,
            "charged_failed": 1,
            "post_process_failed": 0,
            "skipped": 0,
            "errors": 0,
            "items": [{"subscription_id": _SUB_ID, "charged": False, "reason_code": "CHARGE_FAILED"}],
        }

    store, results = _run_tick_with_execute(_return_charged_failed)

    log = list(store.logs.values())[0]
    assert log["status"] == "SUCCESS"
