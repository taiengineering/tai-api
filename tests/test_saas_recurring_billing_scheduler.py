"""WO-COMM-V3-RECURRING-SCHEDULER-TRIGGER-001 — RS01-RS24 + static contract.

Coverage:
  RS01-RS07  candidate selection
  RS08-RS11  dry-run mode
  RS12-RS18  pre-charge guards
  RS19-RS24  live orchestration
  Static     direct://saas_recurring_billing handler exists
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock, patch, call

import pytest

os.environ.setdefault("INICIS_BILLING_MID", "test-mid")
os.environ.setdefault("INICIS_BILLING_SIGN_KEY", "test-sk")
os.environ.setdefault("INICIS_BILLING_INIAPI_KEY", "test-ik")
os.environ.setdefault("INICIS_CLIENT_IP", "1.2.3.4")

# ── Fixed IDs ────────────────────────────────────────────────────────────────

_SUB_ID   = str(uuid.uuid4())
_SUB_ID_2 = str(uuid.uuid4())
_SUB_ID_3 = str(uuid.uuid4())
_BK_ID    = str(uuid.uuid4())
_PAY_ID   = str(uuid.uuid4())
_CT_ID    = str(uuid.uuid4())
_QUOTE_ID = str(uuid.uuid4())

_NOW    = "2026-10-01T10:00:00+09:00"
_DUE    = "2026-10-01T09:00:00+09:00"   # before _NOW
_FUTURE = "2026-10-02T10:00:00+09:00"   # after _NOW

# ── Base data fixtures ────────────────────────────────────────────────────────

_BASE_SUB = {
    "id": _SUB_ID,
    "status": "ACTIVE",
    "product_type": "SAAS",
    "next_billing_at": _DUE,
    "billing_key_id": _BK_ID,
    "amount": 110000,
    "supply_amount": 100000,
    "vat_amount": 10000,
    "user_id": str(uuid.uuid4()),
}

_BASE_BK = {
    "id": _BK_ID,
    "status": "ACTIVE",
    "bill_key": "test-bill-key-secret",
    "mid": "test-mid",
}

_BASE_PAY = {
    "id": _PAY_ID,
    "charge_cycle": 1,
    "status_code": "SUCCESS",
    "quote_id": _QUOTE_ID,
    "contract_id": _CT_ID,
}

_BASE_CONTRACT = {
    "id": _CT_ID,
    "status_code": "ACTIVE",
    "service_type": "SAAS",
    "is_active": True,
    "end_date": "2026-11-01",
}

# ── Mock builders ─────────────────────────────────────────────────────────────


def _make_sub_table(candidates, fresh_subs=None):
    """
    Subscriptions mock:
      Scan chain: complex ordering/filtering
      Fresh chain (per-id): select(*).eq("id", sub_id).limit(1).execute()
    """
    t = MagicMock()

    # Build per-ID lookup for fresh reads
    fresh_list = fresh_subs if fresh_subs is not None else candidates
    fresh_by_id = {s["id"]: s for s in fresh_list}

    # Scan chain
    c = t.select.return_value
    first_eq_rv = c.eq.return_value  # shared return value for first .eq()
    c = first_eq_rv
    c = c.eq.return_value
    c = c.not_.is_.return_value
    c = c.lte.return_value
    c = c.not_.is_.return_value
    c = c.order.return_value
    c = c.order.return_value
    c = c.limit.return_value
    c.execute.return_value = MagicMock(data=candidates)

    # Argument-aware fresh read: capture sub_id from .eq("id", sub_id) call
    class _IdCapture:
        last_id = None
    cap = _IdCapture()

    def _first_eq_side_effect(field, value=None):
        if field == "id":
            cap.last_id = value
        return first_eq_rv

    t.select.return_value.eq.side_effect = _first_eq_side_effect

    def _fresh_execute():
        sub = fresh_by_id.get(cap.last_id)
        return MagicMock(data=[sub] if sub else [])

    first_eq_rv.limit.return_value.execute.side_effect = _fresh_execute

    return t


def _make_bk_table(bks):
    """billing_keys chain: .select().eq().limit().execute()"""
    t = MagicMock()
    t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=bks)
    return t


def _make_pays_table(pays):
    """payments chain: .select().eq().execute()"""
    t = MagicMock()
    t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=pays)
    return t


def _make_contracts_table(contracts):
    """contracts chain: .select().eq().limit().execute()"""
    t = MagicMock()
    t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=contracts)
    return t


def _make_sb(*, subs=None, bks=None, pays=None, contracts=None, fresh_subs=None):
    sb = MagicMock()

    def _table(name):
        if name == "subscriptions":
            return _make_sub_table(subs or [], fresh_subs=fresh_subs)
        if name == "billing_keys":
            return _make_bk_table(bks or [])
        if name == "payments":
            return _make_pays_table(pays or [])
        if name == "contracts":
            return _make_contracts_table(contracts or [])
        return MagicMock()

    sb.table.side_effect = _table
    return sb


def _now_kst_dt():
    from datetime import datetime, timezone, timedelta
    return datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone(timedelta(hours=9)))


def _run(payload, *, subs=None, bks=None, pays=None, contracts=None, fresh_subs=None):
    """Helper: run with mocked supabase + fixed now. dry_run=True by default."""
    from services.saas_recurring_billing_scheduler import run_due_saas_recurring_billing
    sb = _make_sb(subs=subs, bks=bks, pays=pays, contracts=contracts, fresh_subs=fresh_subs)
    with (
        patch("db.supabase_client.get_supabase", return_value=sb),
        patch("services.saas_recurring_billing_scheduler.now_kst", return_value=_now_kst_dt()),
        patch(
            "services.saas_recurring_billing_scheduler.serialize_business_datetime",
            return_value=_NOW,
        ),
    ):
        return run_due_saas_recurring_billing(payload)


def _full_eligible(sub_override=None):
    """Return (subs, bks, pays, contracts) for a fully eligible candidate."""
    sub = {**_BASE_SUB, **(sub_override or {})}
    return dict(
        subs=[sub],
        bks=[_BASE_BK],
        pays=[_BASE_PAY],
        contracts=[_BASE_CONTRACT],
    )


# ── RS01-RS07: Candidate selection ───────────────────────────────────────────


def test_RS01_active_saas_due_is_candidate():
    """RS01: ACTIVE SAAS with past next_billing_at → eligible candidate."""
    result = _run({"dry_run": True}, **_full_eligible())
    assert result["scanned"] == 1
    assert result["eligible"] == 1
    assert result["items"][0]["eligible"] is True


def test_RS02_future_next_billing_at_excluded():
    """RS02: next_billing_at in the future → guard skips (NOT_YET_DUE)."""
    result = _run(
        {"dry_run": True},
        **_full_eligible(sub_override={"next_billing_at": _FUTURE}),
    )
    assert result["scanned"] == 1
    assert result["eligible"] == 0
    assert result["items"][0]["reason_code"] == "NOT_YET_DUE"


def test_RS03_cancelled_excluded():
    """RS03: status=CANCELLED → guard skips (SUB_NOT_ACTIVE)."""
    result = _run(
        {"dry_run": True},
        **_full_eligible(sub_override={"status": "CANCELLED"}),
    )
    assert result["eligible"] == 0
    assert result["items"][0]["reason_code"] == "SUB_NOT_ACTIVE"


def test_RS04_paused_excluded():
    """RS04: status=PAUSED → guard skips (SUB_NOT_ACTIVE)."""
    result = _run(
        {"dry_run": True},
        **_full_eligible(sub_override={"status": "PAUSED"}),
    )
    assert result["eligible"] == 0
    assert result["items"][0]["reason_code"] == "SUB_NOT_ACTIVE"


def test_RS05_non_saas_excluded():
    """RS05: product_type=PROCESS → guard skips (SUB_NOT_SAAS)."""
    result = _run(
        {"dry_run": True},
        **_full_eligible(sub_override={"product_type": "PROCESS"}),
    )
    assert result["eligible"] == 0
    assert result["items"][0]["reason_code"] == "SUB_NOT_SAAS"


def test_RS06_no_billing_key_id_excluded():
    """RS06: billing_key_id=None → guard skips (BILLING_KEY_ID_MISSING)."""
    result = _run(
        {"dry_run": True},
        **_full_eligible(sub_override={"billing_key_id": None}),
    )
    assert result["eligible"] == 0
    assert result["items"][0]["reason_code"] == "BILLING_KEY_ID_MISSING"


def test_RS07_limit_and_order_deterministic():
    """RS07: three candidates with different IDs all processed; limit applied."""
    subs = [
        {**_BASE_SUB, "id": _SUB_ID, "next_billing_at": "2026-10-01T01:00:00+09:00"},
        {**_BASE_SUB, "id": _SUB_ID_2, "next_billing_at": "2026-10-01T02:00:00+09:00"},
        {**_BASE_SUB, "id": _SUB_ID_3, "next_billing_at": "2026-10-01T03:00:00+09:00"},
    ]
    result = _run(
        {"dry_run": True, "limit": 3},
        subs=subs,
        bks=[_BASE_BK],
        pays=[_BASE_PAY],
        contracts=[_BASE_CONTRACT],
    )
    assert result["scanned"] == 3
    ids = [item["subscription_id"] for item in result["items"]]
    assert ids == [_SUB_ID, _SUB_ID_2, _SUB_ID_3]


# ── RS08-RS11: Dry-run ────────────────────────────────────────────────────────


def test_RS08_dry_run_default_true():
    """RS08: payload without dry_run → defaults to dry_run=True."""
    result = _run({}, **_full_eligible())
    assert result["dry_run"] is True
    assert result["charged_success"] == 0


def test_RS09_dry_run_inicis_calls_zero():
    """RS09: dry_run=True → _charge_subscription_once never called."""
    from services.saas_recurring_billing_scheduler import run_due_saas_recurring_billing
    sb = _make_sb(**_full_eligible())
    with (
        patch("db.supabase_client.get_supabase", return_value=sb),
        patch("services.saas_recurring_billing_scheduler.now_kst", return_value=_now_kst_dt()),
        patch(
            "services.saas_recurring_billing_scheduler.serialize_business_datetime",
            return_value=_NOW,
        ),
        patch("routers.payment_billing._charge_subscription_once") as mock_charge,
    ):
        run_due_saas_recurring_billing({"dry_run": True})

    mock_charge.assert_not_called()


def test_RS10_dry_run_db_writes_zero():
    """RS10: dry_run=True → no .update() or .insert() on supabase tables."""
    from services.saas_recurring_billing_scheduler import run_due_saas_recurring_billing
    sb = _make_sb(**_full_eligible())

    update_mock = MagicMock()
    insert_mock = MagicMock()
    original_side_effect = sb.table.side_effect

    def _table_spy(name):
        t = original_side_effect(name)
        t.update = update_mock
        t.insert = insert_mock
        return t

    sb.table.side_effect = _table_spy

    with (
        patch("db.supabase_client.get_supabase", return_value=sb),
        patch("services.saas_recurring_billing_scheduler.now_kst", return_value=_now_kst_dt()),
        patch(
            "services.saas_recurring_billing_scheduler.serialize_business_datetime",
            return_value=_NOW,
        ),
    ):
        run_due_saas_recurring_billing({"dry_run": True})

    update_mock.assert_not_called()
    insert_mock.assert_not_called()


def test_RS11_dry_run_no_secret_output():
    """RS11: dry_run items must not expose bill_key secret value."""
    result = _run({"dry_run": True}, **_full_eligible())
    for item in result["items"]:
        item_str = str(item)
        assert "test-bill-key-secret" not in item_str


# ── RS12-RS18: Pre-charge guards ──────────────────────────────────────────────


def test_RS12_billing_key_inactive_skipped():
    """RS12: billing_key.status != ACTIVE → BILLING_KEY_INACTIVE, no charge."""
    result = _run(
        {"dry_run": True},
        subs=[_BASE_SUB],
        bks=[{**_BASE_BK, "status": "REVOKED"}],
        pays=[_BASE_PAY],
        contracts=[_BASE_CONTRACT],
    )
    assert result["eligible"] == 0
    assert result["items"][0]["reason_code"] == "BILLING_KEY_INACTIVE"


def test_RS13_cycle1_success_missing_skipped():
    """RS13: no PAID/SUCCESS cycle-1 payment → CYCLE1_PAYMENT_NOT_FOUND."""
    result = _run(
        {"dry_run": True},
        subs=[_BASE_SUB],
        bks=[_BASE_BK],
        pays=[{**_BASE_PAY, "status_code": "FAILED"}],
        contracts=[_BASE_CONTRACT],
    )
    assert result["eligible"] == 0
    assert result["items"][0]["reason_code"] == "CYCLE1_PAYMENT_NOT_FOUND"


def test_RS13_no_payments_skipped():
    """RS13 variant: payments table empty → CYCLE1_PAYMENT_NOT_FOUND."""
    result = _run(
        {"dry_run": True},
        subs=[_BASE_SUB],
        bks=[_BASE_BK],
        pays=[],
        contracts=[_BASE_CONTRACT],
    )
    assert result["items"][0]["reason_code"] == "CYCLE1_PAYMENT_NOT_FOUND"


def test_RS14_quote_id_missing_skipped():
    """RS14: cycle-1 payment has no quote_id → QUOTE_ID_MISSING."""
    result = _run(
        {"dry_run": True},
        subs=[_BASE_SUB],
        bks=[_BASE_BK],
        pays=[{**_BASE_PAY, "quote_id": None}],
        contracts=[_BASE_CONTRACT],
    )
    assert result["items"][0]["reason_code"] == "QUOTE_ID_MISSING"


def test_RS15_contract_id_missing_skipped():
    """RS15: cycle-1 payment has no contract_id → CONTRACT_ID_MISSING."""
    result = _run(
        {"dry_run": True},
        subs=[_BASE_SUB],
        bks=[_BASE_BK],
        pays=[{**_BASE_PAY, "contract_id": None}],
        contracts=[_BASE_CONTRACT],
    )
    assert result["items"][0]["reason_code"] == "CONTRACT_ID_MISSING"


def test_RS16_contract_inactive_skipped():
    """RS16: contract.status_code != ACTIVE → CONTRACT_NOT_ACTIVE."""
    result = _run(
        {"dry_run": True},
        subs=[_BASE_SUB],
        bks=[_BASE_BK],
        pays=[_BASE_PAY],
        contracts=[{**_BASE_CONTRACT, "status_code": "EXPIRED"}],
    )
    assert result["items"][0]["reason_code"] == "CONTRACT_NOT_ACTIVE"


def test_RS17_contract_non_saas_skipped():
    """RS17: contract.service_type != SAAS → CONTRACT_NOT_SAAS."""
    result = _run(
        {"dry_run": True},
        subs=[_BASE_SUB],
        bks=[_BASE_BK],
        pays=[_BASE_PAY],
        contracts=[{**_BASE_CONTRACT, "service_type": "PROCESS"}],
    )
    assert result["items"][0]["reason_code"] == "CONTRACT_NOT_SAAS"


def test_RS18_contract_end_date_missing_skipped():
    """RS18: contract.end_date is None → CONTRACT_END_DATE_MISSING."""
    result = _run(
        {"dry_run": True},
        subs=[_BASE_SUB],
        bks=[_BASE_BK],
        pays=[_BASE_PAY],
        contracts=[{**_BASE_CONTRACT, "end_date": None}],
    )
    assert result["items"][0]["reason_code"] == "CONTRACT_END_DATE_MISSING"


# ── RS19-RS24: Live orchestration ─────────────────────────────────────────────


def _run_live(*, subs=None, bks=None, pays=None, contracts=None,
              charge_return=None, on_success_side_effect=None, fresh_subs=None):
    """Run with dry_run=False and mocked charge path. Handles SaasRecurringBillingError."""
    from services.saas_recurring_billing_scheduler import (
        run_due_saas_recurring_billing,
        SaasRecurringBillingError,
    )
    sb = _make_sb(subs=subs, bks=bks, pays=pays, contracts=contracts, fresh_subs=fresh_subs)
    charge_mock = MagicMock(return_value=charge_return or {"success": True, "payment_id": _PAY_ID, "result": {}})
    on_success_mock = MagicMock(side_effect=on_success_side_effect)
    with (
        patch("db.supabase_client.get_supabase", return_value=sb),
        patch("services.saas_recurring_billing_scheduler.now_kst", return_value=_now_kst_dt()),
        patch(
            "services.saas_recurring_billing_scheduler.serialize_business_datetime",
            return_value=_NOW,
        ),
        patch("routers.payment_billing._charge_subscription_once", charge_mock),
        patch("services.payment_post_process.on_payment_success_sync", on_success_mock),
    ):
        try:
            result = run_due_saas_recurring_billing({"dry_run": False})
        except SaasRecurringBillingError as exc:
            result = exc.summary
    return result, charge_mock, on_success_mock


def test_RS19_one_eligible_calls_charge_once():
    """RS19: one eligible candidate → existing charge path called exactly once."""
    result, charge_mock, _ = _run_live(**_full_eligible())
    charge_mock.assert_called_once()


def test_RS20_success_calls_on_payment_success_sync_once():
    """RS20: successful charge → on_payment_success_sync called once with payment_id."""
    result, _, on_success_mock = _run_live(
        **_full_eligible(),
        charge_return={"success": True, "payment_id": _PAY_ID, "result": {}},
    )
    on_success_mock.assert_called_once_with(_PAY_ID)
    assert result["charged_success"] == 1


def test_RS21_failure_no_success_post_process():
    """RS21: charge fails → on_payment_success_sync NOT called."""
    result, _, on_success_mock = _run_live(
        **_full_eligible(),
        charge_return={"success": False, "payment_id": _PAY_ID, "result": {"error": "fail"}},
    )
    on_success_mock.assert_not_called()
    assert result["charged_failed"] == 1


def test_RS22_item_exception_does_not_abort_next():
    """RS22: exception on first candidate does not abort second candidate."""
    subs = [
        {**_BASE_SUB, "id": _SUB_ID},
        {**_BASE_SUB, "id": _SUB_ID_2},
    ]
    from services.saas_recurring_billing_scheduler import (
        run_due_saas_recurring_billing,
        SaasRecurringBillingError,
    )
    sb = _make_sb(subs=subs, bks=[_BASE_BK], pays=[_BASE_PAY], contracts=[_BASE_CONTRACT])

    call_count = 0

    def _charge_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("first candidate explodes")
        return {"success": True, "payment_id": _PAY_ID, "result": {}}

    with (
        patch("db.supabase_client.get_supabase", return_value=sb),
        patch("services.saas_recurring_billing_scheduler.now_kst", return_value=_now_kst_dt()),
        patch(
            "services.saas_recurring_billing_scheduler.serialize_business_datetime",
            return_value=_NOW,
        ),
        patch("routers.payment_billing._charge_subscription_once", side_effect=_charge_side_effect),
        patch("services.payment_post_process.on_payment_success_sync"),
    ):
        try:
            result = run_due_saas_recurring_billing({"dry_run": False})
        except SaasRecurringBillingError as exc:
            result = exc.summary

    assert result["errors"] == 1
    assert result["charged_success"] == 1
    assert len(result["items"]) == 2


def test_RS23_no_inline_retry_within_occurrence():
    """RS23: a failed charge is counted once; no retry loop inside the handler."""
    result, charge_mock, _ = _run_live(
        **_full_eligible(),
        charge_return={"success": False, "payment_id": _PAY_ID, "result": {}},
    )
    # charge called exactly once — no retry
    assert charge_mock.call_count == 1
    assert result["charged_failed"] == 1


def test_RS24_handler_summary_exact():
    """RS24: summary fields are exact — scanned, eligible, charged_success, etc."""
    subs = [
        {**_BASE_SUB, "id": _SUB_ID},   # will succeed
        {**_BASE_SUB, "id": _SUB_ID_2},  # will fail charge
        {**_BASE_SUB, "id": _SUB_ID_3, "billing_key_id": None},  # guard skip
    ]
    from services.saas_recurring_billing_scheduler import (
        run_due_saas_recurring_billing,
        SaasRecurringBillingError,
    )
    sb = _make_sb(subs=subs, bks=[_BASE_BK], pays=[_BASE_PAY], contracts=[_BASE_CONTRACT])

    call_idx = 0

    def _charge_side_effect(*args, **kwargs):
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            return {"success": True, "payment_id": _PAY_ID, "result": {}}
        return {"success": False, "payment_id": _PAY_ID, "result": {}}

    with (
        patch("db.supabase_client.get_supabase", return_value=sb),
        patch("services.saas_recurring_billing_scheduler.now_kst", return_value=_now_kst_dt()),
        patch(
            "services.saas_recurring_billing_scheduler.serialize_business_datetime",
            return_value=_NOW,
        ),
        patch("routers.payment_billing._charge_subscription_once", side_effect=_charge_side_effect),
        patch("services.payment_post_process.on_payment_success_sync"),
    ):
        try:
            result = run_due_saas_recurring_billing({"dry_run": False})
        except SaasRecurringBillingError as exc:
            result = exc.summary

    assert result["scanned"] == 3
    assert result["eligible"] == 2
    assert result["charged_success"] == 1
    assert result["charged_failed"] == 1
    assert result["skipped"] == 1
    assert result["errors"] == 0
    assert len(result["items"]) == 3


# ── Static contract ───────────────────────────────────────────────────────────


def test_static_direct_handler_registered():
    """direct://saas_recurring_billing must exist in DIRECT_HANDLERS registry."""
    from services.scheduler.handlers import register_direct_handlers
    handlers = register_direct_handlers()
    assert "direct://saas_recurring_billing" in handlers


def test_static_handler_callable():
    """The registered handler is callable."""
    from services.scheduler.handlers import register_direct_handlers
    handlers = register_direct_handlers()
    assert callable(handlers["direct://saas_recurring_billing"])
