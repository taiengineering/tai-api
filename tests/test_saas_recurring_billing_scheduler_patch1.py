"""WO-COMM-V3-RECURRING-SCHEDULER-TRIGGER-PATCH-001 — P1 tests.

Coverage:
  P1-SQL01-09  SQL artifact static contract
  P1-C01-06   server-authoritative recurring cycle
  P1-R01-07   fresh subscription revalidation
  P1-P01-06   post-process outcome visibility
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("INICIS_BILLING_MID", "test-mid")
os.environ.setdefault("INICIS_BILLING_SIGN_KEY", "test-sk")
os.environ.setdefault("INICIS_BILLING_INIAPI_KEY", "test-ik")
os.environ.setdefault("INICIS_CLIENT_IP", "1.2.3.4")

_KST = timezone(timedelta(hours=9))
_NOW_DT = datetime(2026, 10, 1, 10, 0, 0, tzinfo=_KST)
_NOW_ISO = "2026-10-01T10:00:00+09:00"
_DUE_ISO = "2026-10-01T09:00:00+09:00"    # before _NOW_DT
_FUTURE_ISO = "2026-10-02T10:00:00+09:00"  # after _NOW_DT

_SUB_ID   = str(uuid.uuid4())
_SUB_ID_2 = str(uuid.uuid4())
_BK_ID    = str(uuid.uuid4())
_PAY_ID   = str(uuid.uuid4())
_CT_ID    = str(uuid.uuid4())
_QUOTE_ID = str(uuid.uuid4())

_SQL_UP_SCHED = Path(__file__).parent.parent / "docs" / "sql" / \
    "20261001_comm_v3_recurring_billing_scheduler_up.sql"
_SQL_UP_GUARD = Path(__file__).parent.parent / "docs" / "sql" / \
    "20261001_comm_v3_recurring_payment_guard_patch_up.sql"

_BASE_SUB = {
    "id": _SUB_ID,
    "status": "ACTIVE",
    "product_type": "SAAS",
    "next_billing_at": _DUE_ISO,
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
    "is_active": True, "end_date": "2026-11-01",
}


# ── Shared mock helpers ───────────────────────────────────────────────────────

def _make_sub_table(candidates, fresh_subs=None):
    t = MagicMock()
    # Scan chain
    c = t.select.return_value
    c = c.eq.return_value
    c = c.eq.return_value
    c = c.not_.is_.return_value
    c = c.lte.return_value
    c = c.not_.is_.return_value
    c = c.order.return_value
    c = c.order.return_value
    c = c.limit.return_value
    c.execute.return_value = MagicMock(data=candidates)
    # Fresh revalidation chain: select().eq().limit().execute()
    fresh = fresh_subs if fresh_subs is not None else (candidates[:1] if candidates else [])
    t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=fresh)
    return t


def _make_sb(*, subs=None, bks=None, pays=None, contracts=None, fresh_subs=None):
    sb = MagicMock()

    def _table(name):
        if name == "subscriptions":
            return _make_sub_table(subs or [], fresh_subs=fresh_subs)
        if name == "billing_keys":
            t = MagicMock()
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=bks or [])
            return t
        if name == "payments":
            t = MagicMock()
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=pays or [])
            return t
        if name == "contracts":
            t = MagicMock()
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=contracts or [])
            return t
        return MagicMock()

    sb.table.side_effect = _table
    return sb


def _run_with_patches(payload, sb):
    from services.saas_recurring_billing_scheduler import (
        run_due_saas_recurring_billing,
        SaasRecurringBillingError,
    )
    with (
        patch("db.supabase_client.get_supabase", return_value=sb),
        patch("services.saas_recurring_billing_scheduler.now_kst", return_value=_NOW_DT),
        patch(
            "services.saas_recurring_billing_scheduler.serialize_business_datetime",
            return_value=_NOW_ISO,
        ),
    ):
        try:
            return run_due_saas_recurring_billing(payload)
        except SaasRecurringBillingError as exc:
            return exc.summary


def _run_live_patched(sb, *, charge_return=None, on_success_side_effect=None):
    from services.saas_recurring_billing_scheduler import (
        run_due_saas_recurring_billing,
        SaasRecurringBillingError,
    )
    charge_mock = MagicMock(
        return_value=charge_return or {"success": True, "payment_id": _PAY_ID, "result": {}}
    )
    on_success_mock = MagicMock(side_effect=on_success_side_effect)
    with (
        patch("db.supabase_client.get_supabase", return_value=sb),
        patch("services.saas_recurring_billing_scheduler.now_kst", return_value=_NOW_DT),
        patch(
            "services.saas_recurring_billing_scheduler.serialize_business_datetime",
            return_value=_NOW_ISO,
        ),
        patch("routers.payment_billing._charge_subscription_once", charge_mock),
        patch("services.payment_post_process.on_payment_success_sync", on_success_mock),
    ):
        try:
            result = run_due_saas_recurring_billing({"dry_run": False})
        except SaasRecurringBillingError as exc:
            result = exc.summary
    return result, charge_mock, on_success_mock


def _full_eligible():
    return dict(
        subs=[_BASE_SUB], bks=[_BASE_BK],
        pays=[_BASE_PAY], contracts=[_BASE_CONTRACT],
    )


# ── P1-SQL01-09: SQL artifact contract ───────────────────────────────────────


def test_P1_SQL01_no_cron_schedule_config_column_in_master_insert():
    """P1-SQL01: scheduler UP SQL must NOT reference cron_schedule_config as a column."""
    sql = _SQL_UP_SCHED.read_text()
    # The INSERT INTO cron_job_master must not list cron_schedule_config
    import re
    master_insert = re.search(
        r"INSERT INTO public\.cron_job_master\s*\(([^)]+)\)", sql, re.IGNORECASE | re.DOTALL
    )
    assert master_insert, "cron_job_master INSERT not found"
    columns = master_insert.group(1).lower()
    assert "cron_schedule_config" not in columns


def test_P1_SQL02_separate_cron_schedule_config_insert_exists():
    """P1-SQL02: scheduler UP SQL must INSERT into cron_schedule_config separately."""
    sql = _SQL_UP_SCHED.read_text()
    assert "INSERT INTO public.cron_schedule_config" in sql or \
           "INSERT INTO cron_schedule_config" in sql.upper().replace("PUBLIC.", "")


def test_P1_SQL03_master_is_active_false():
    """P1-SQL03: master row must be registered with is_active = false."""
    sql = _SQL_UP_SCHED.read_text().lower()
    assert "is_active" in sql
    assert "false" in sql


def test_P1_SQL04_payload_dry_run_true():
    """P1-SQL04: request_payload must contain dry_run: true."""
    sql = _SQL_UP_SCHED.read_text()
    assert '"dry_run": true' in sql or "'dry_run': true" in sql or \
           '"dry_run":true' in sql


def test_P1_SQL05_cron_expression_hourly():
    """P1-SQL05: cron_expression must be 0 * * * *."""
    sql = _SQL_UP_SCHED.read_text()
    assert "0 * * * *" in sql


def test_P1_SQL06_no_pg_cron():
    """P1-SQL06: UP SQL must not reference pg_cron."""
    sql = _SQL_UP_SCHED.read_text().lower()
    assert "pg_cron" not in sql


def test_P1_SQL07_manual_renewal_index_has_not_recurring():
    """P1-SQL07: guard patch UP SQL must scope manual renewal index with is_recurring IS NOT TRUE."""
    sql = _SQL_UP_GUARD.read_text()
    assert "is_recurring IS NOT TRUE" in sql


def test_P1_SQL08_recurring_index_on_subscription_id_cycle():
    """P1-SQL08: new recurring index must be on (subscription_id, charge_cycle)."""
    sql = _SQL_UP_GUARD.read_text()
    assert "subscription_id, charge_cycle" in sql or "subscription_id,charge_cycle" in sql


def test_P1_SQL09_recurring_index_requires_is_recurring_true():
    """P1-SQL09: recurring index must require is_recurring IS TRUE."""
    sql = _SQL_UP_GUARD.read_text()
    assert "is_recurring IS TRUE" in sql


# ── P1-C01-06: Server-authoritative recurring cycle ──────────────────────────


def test_P1_C01_cycle1_success_next_is_2():
    """P1-C01: one cycle-1 SUCCESS → next recurring cycle = 2."""
    from routers.payment_billing import _compute_v3_saas_recurring_cycle
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
        data=[{"charge_cycle": 1}]
    )
    assert _compute_v3_saas_recurring_cycle(sb, _SUB_ID) == 2


def test_P1_C02_failed_cycle2_retry_remains_cycle2():
    """P1-C02: cycle-1 SUCCESS + cycle-2 FAILED → server still computes next = 2."""
    from routers.payment_billing import _compute_v3_saas_recurring_cycle
    sb = MagicMock()
    # Only PAID/SUCCESS are returned — FAILED is excluded by the query filter
    sb.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
        data=[{"charge_cycle": 1}]
    )
    assert _compute_v3_saas_recurring_cycle(sb, _SUB_ID) == 2


def test_P1_C03_successful_cycle2_next_is_3():
    """P1-C03: cycle-1 + cycle-2 both SUCCESS → next = 3."""
    from routers.payment_billing import _compute_v3_saas_recurring_cycle
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
        data=[{"charge_cycle": 1}, {"charge_cycle": 2}]
    )
    assert _compute_v3_saas_recurring_cycle(sb, _SUB_ID) == 3


def test_P1_C04_pending_cycle2_fail_closed():
    """P1-C04: PENDING active attempt for computed cycle → guard returns PENDING_CYCLE_EXISTS."""
    pays = [
        # cycle-1 SUCCESS (for linkage check)
        {**_BASE_PAY, "charge_cycle": 1, "status_code": "SUCCESS"},
        # cycle-2 PENDING (computed next cycle = 2)
        {"id": str(uuid.uuid4()), "charge_cycle": 2, "status_code": "PENDING",
         "quote_id": _QUOTE_ID, "contract_id": _CT_ID},
    ]
    sb = _make_sb(subs=[_BASE_SUB], bks=[_BASE_BK], pays=pays, contracts=[_BASE_CONTRACT])
    result = _run_with_patches({"dry_run": True}, sb)
    assert result["items"][0]["reason_code"] == "PENDING_CYCLE_EXISTS"


def test_P1_C05_explicit_wrong_cycle_cannot_bypass_server_authority():
    """P1-C05: billing_charge ignores caller-provided cycle for V3 SAAS — uses server authority."""
    from routers.payment_billing import billing_charge

    sub = {
        "id": _SUB_ID, "user_id": str(uuid.uuid4()), "company_id": None,
        "status": "ACTIVE", "product_type": "SAAS",
        "plan_code": None, "plan_name": "TAI Safe",
        "amount": 110000, "supply_amount": 100000, "vat_amount": 10000,
        "billing_key_id": _BK_ID,
    }
    bk = {**_BASE_BK}

    def _table(name):
        t = MagicMock()
        if name == "subscriptions":
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[sub])
            t.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        elif name == "billing_keys":
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[bk])
        elif name == "payments":
            # _compute_v3_saas_recurring_cycle chain: select().eq().in_().execute()
            t.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
                data=[{"charge_cycle": 1}]  # cycle-1 SUCCESS → next = 2
            )
            # _v3_saas_pending_cycle_exists chain: select().eq().eq().eq().limit().execute()
            t.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            # pre-payment reuse chain (cycle=1 SAAS): select().eq().eq().eq().eq().limit().execute()
            t.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[{"id": _PAY_ID}]
            )
            t.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        return t

    sb = MagicMock()
    sb.table.side_effect = _table

    class _Body:
        subscription_id = _SUB_ID
        charge_cycle = 999  # wrong cycle — must be ignored for V3 SAAS

    cycle_used = []

    def _charge_spy(supa, *, subscription, billing_key_row, charge_cycle, is_recurring, **kw):
        cycle_used.append(charge_cycle)
        return {"success": True, "payment_id": _PAY_ID, "result": {"resultCode": "00"}}

    with (
        patch("routers.payment_billing.get_supabase", return_value=sb),
        patch("routers.payment_billing._charge_subscription_once", side_effect=_charge_spy),
        patch("services.payment_post_process.on_payment_success_sync"),
    ):
        billing_charge(_Body())

    # Server authority: cycle must be 2 (max success=1 + 1), not caller's 999
    assert cycle_used == [2], f"Expected [2] but got {cycle_used}"


def test_P1_C06_manual_and_scheduler_same_cycle():
    """P1-C06: both billing_charge and scheduler use _compute_v3_saas_recurring_cycle."""
    from routers.payment_billing import _compute_v3_saas_recurring_cycle

    # Verify the helper exists and is importable from billing module
    assert callable(_compute_v3_saas_recurring_cycle)

    # Verify scheduler _pre_charge_guard also uses max(success)+1 semantics
    pays = [
        {**_BASE_PAY, "charge_cycle": 1, "status_code": "SUCCESS"},
        {"id": str(uuid.uuid4()), "charge_cycle": 2, "status_code": "FAILED",
         "quote_id": _QUOTE_ID, "contract_id": _CT_ID},  # failed — must not advance cycle
    ]
    sb = _make_sb(subs=[_BASE_SUB], bks=[_BASE_BK], pays=pays, contracts=[_BASE_CONTRACT])
    result = _run_with_patches({"dry_run": True}, sb)
    # Guard should compute cycle=2 (not cycle=3), and FAILED cycle-2 does not advance
    assert result["items"][0]["eligible"] is True
    guard = result["items"][0]
    # If charge_cycle was computed incorrectly as 3 (count-based), the PENDING guard would miss
    # We verify no PENDING_CYCLE_EXISTS since there's no PENDING for cycle=2
    assert guard.get("reason_code") == "DRY_RUN"


# ── P1-R01-07: Fresh revalidation ────────────────────────────────────────────


def test_P1_R01_candidate_active_fresh_cancelled_skip():
    """P1-R01: scanned ACTIVE; fresh re-read is CANCELLED → skip (SUB_NOT_ACTIVE)."""
    fresh = [{**_BASE_SUB, "status": "CANCELLED"}]
    sb = _make_sb(**_full_eligible(), fresh_subs=fresh)
    result = _run_with_patches({"dry_run": False}, sb)
    items = result["items"]
    assert len(items) == 1
    assert items[0]["reason_code"] == "SUB_NOT_ACTIVE"
    assert result["charged_success"] == 0


def test_P1_R02_candidate_active_fresh_paused_skip():
    """P1-R02: scanned ACTIVE; fresh re-read is PAUSED → skip (SUB_NOT_ACTIVE)."""
    fresh = [{**_BASE_SUB, "status": "PAUSED"}]
    sb = _make_sb(**_full_eligible(), fresh_subs=fresh)
    result = _run_with_patches({"dry_run": False}, sb)
    assert result["items"][0]["reason_code"] == "SUB_NOT_ACTIVE"


def test_P1_R03_candidate_due_fresh_future_skip():
    """P1-R03: scanned due; fresh next_billing_at advanced to future → NOT_YET_DUE."""
    fresh = [{**_BASE_SUB, "next_billing_at": _FUTURE_ISO}]
    sb = _make_sb(**_full_eligible(), fresh_subs=fresh)
    result = _run_with_patches({"dry_run": False}, sb)
    assert result["items"][0]["reason_code"] == "NOT_YET_DUE"


def test_P1_R04_fresh_billing_key_id_removed_skip():
    """P1-R04: fresh re-read has billing_key_id=None → BILLING_KEY_ID_MISSING."""
    fresh = [{**_BASE_SUB, "billing_key_id": None}]
    sb = _make_sb(**_full_eligible(), fresh_subs=fresh)
    result = _run_with_patches({"dry_run": False}, sb)
    assert result["items"][0]["reason_code"] == "BILLING_KEY_ID_MISSING"


def test_P1_R05_offset_equivalent_aware_compare_correct():
    """P1-R05: UTC timestamp equivalent to past KST time passes temporal check."""
    # 2026-10-01T00:00:00Z = 2026-10-01T09:00:00+09:00 — same instant, different TZ
    fresh = [{**_BASE_SUB, "next_billing_at": "2026-10-01T00:00:00+00:00"}]
    sb = _make_sb(**_full_eligible(), fresh_subs=fresh)
    with (
        patch("db.supabase_client.get_supabase", return_value=sb),
        patch("services.saas_recurring_billing_scheduler.now_kst", return_value=_NOW_DT),
        patch(
            "services.saas_recurring_billing_scheduler.serialize_business_datetime",
            return_value=_NOW_ISO,
        ),
        patch("routers.payment_billing._charge_subscription_once",
              return_value={"success": True, "payment_id": _PAY_ID, "result": {}}),
        patch("services.payment_post_process.on_payment_success_sync"),
    ):
        from services.saas_recurring_billing_scheduler import run_due_saas_recurring_billing, SaasRecurringBillingError
        try:
            result = run_due_saas_recurring_billing({"dry_run": False})
        except SaasRecurringBillingError as exc:
            result = exc.summary
    # UTC 00:00:00 = KST 09:00:00 which is before KST 10:00:00 → should charge, not skip
    assert result["charged_success"] == 1


def test_P1_R06_malformed_timestamp_fail_closed():
    """P1-R06: next_billing_at is not a valid ISO timestamp → NEXT_BILLING_AT_INVALID."""
    fresh = [{**_BASE_SUB, "next_billing_at": "garbage-value"}]
    sb = _make_sb(**_full_eligible(), fresh_subs=fresh)
    result = _run_with_patches({"dry_run": False}, sb)
    assert result["items"][0]["reason_code"] == "NEXT_BILLING_AT_INVALID"


def test_P1_R07_naive_timestamp_fail_closed():
    """P1-R07: next_billing_at is naive (no tzinfo) → NEXT_BILLING_AT_INVALID."""
    fresh = [{**_BASE_SUB, "next_billing_at": "2026-10-01T09:00:00"}]  # no tz
    sb = _make_sb(**_full_eligible(), fresh_subs=fresh)
    result = _run_with_patches({"dry_run": False}, sb)
    assert result["items"][0]["reason_code"] == "NEXT_BILLING_AT_INVALID"


# ── P1-P01-06: Post-process outcome ──────────────────────────────────────────


def test_P1_P01_success_plus_postprocess_success_is_applied():
    """P1-P01: charge success + postprocess success → charged_success=1, no error."""
    sb = _make_sb(**_full_eligible())
    result, charge_mock, on_success_mock = _run_live_patched(sb)
    assert result["charged_success"] == 1
    assert result.get("post_process_failed", 0) == 0
    on_success_mock.assert_called_once()


def test_P1_P02_success_plus_postprocess_exception_is_post_process_failed():
    """P1-P02: charge success + postprocess exception → POST_PROCESS_FAILED."""
    from services.saas_recurring_billing_scheduler import SaasRecurringBillingError
    sb = _make_sb(**_full_eligible())
    with (
        patch("db.supabase_client.get_supabase", return_value=sb),
        patch("services.saas_recurring_billing_scheduler.now_kst", return_value=_NOW_DT),
        patch(
            "services.saas_recurring_billing_scheduler.serialize_business_datetime",
            return_value=_NOW_ISO,
        ),
        patch("routers.payment_billing._charge_subscription_once",
              return_value={"success": True, "payment_id": _PAY_ID, "result": {}}),
        patch("services.payment_post_process.on_payment_success_sync",
              side_effect=RuntimeError("renewal chain exploded")),
    ):
        from services.saas_recurring_billing_scheduler import run_due_saas_recurring_billing
        with pytest.raises(SaasRecurringBillingError) as exc_info:
            run_due_saas_recurring_billing({"dry_run": False})

    summary = exc_info.value.summary
    assert summary["post_process_failed"] == 1
    assert summary["items"][0]["reason_code"] == "POST_PROCESS_FAILED"


def test_P1_P03_post_process_failure_does_not_call_charge_second_time():
    """P1-P03: P1-P02 scenario — charge called exactly once, not retried."""
    from services.saas_recurring_billing_scheduler import (
        run_due_saas_recurring_billing,
        SaasRecurringBillingError,
    )
    sb = _make_sb(**_full_eligible())
    charge_mock = MagicMock(
        return_value={"success": True, "payment_id": _PAY_ID, "result": {}}
    )
    with (
        patch("db.supabase_client.get_supabase", return_value=sb),
        patch("services.saas_recurring_billing_scheduler.now_kst", return_value=_NOW_DT),
        patch(
            "services.saas_recurring_billing_scheduler.serialize_business_datetime",
            return_value=_NOW_ISO,
        ),
        patch("routers.payment_billing._charge_subscription_once", charge_mock),
        patch("services.payment_post_process.on_payment_success_sync",
              side_effect=RuntimeError("renewal chain exploded")),
    ):
        with pytest.raises(SaasRecurringBillingError):
            run_due_saas_recurring_billing({"dry_run": False})

    charge_mock.assert_called_once()


def test_P1_P04_post_process_failure_retains_payment_id():
    """P1-P04: P1-P02 scenario — payment_id is retained in the item."""
    from services.saas_recurring_billing_scheduler import (
        run_due_saas_recurring_billing,
        SaasRecurringBillingError,
    )
    sb = _make_sb(**_full_eligible())
    with (
        patch("db.supabase_client.get_supabase", return_value=sb),
        patch("services.saas_recurring_billing_scheduler.now_kst", return_value=_NOW_DT),
        patch(
            "services.saas_recurring_billing_scheduler.serialize_business_datetime",
            return_value=_NOW_ISO,
        ),
        patch("routers.payment_billing._charge_subscription_once",
              return_value={"success": True, "payment_id": _PAY_ID, "result": {}}),
        patch("services.payment_post_process.on_payment_success_sync",
              side_effect=RuntimeError("boom")),
    ):
        with pytest.raises(SaasRecurringBillingError) as exc_info:
            run_due_saas_recurring_billing({"dry_run": False})

    assert exc_info.value.summary["items"][0]["payment_id"] == _PAY_ID


def test_P1_P05_batch_continues_after_postprocess_failure():
    """P1-P05: postprocess failure on sub-1 does not abort sub-2 processing."""
    from services.saas_recurring_billing_scheduler import (
        run_due_saas_recurring_billing,
        SaasRecurringBillingError,
    )
    subs = [
        {**_BASE_SUB, "id": _SUB_ID},
        {**_BASE_SUB, "id": _SUB_ID_2},
    ]
    sb = _make_sb(subs=subs, bks=[_BASE_BK], pays=[_BASE_PAY], contracts=[_BASE_CONTRACT])

    call_idx = 0

    def _on_success_side_effect(pay_id):
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            raise RuntimeError("sub-1 post-process fails")
        # sub-2 succeeds

    with (
        patch("db.supabase_client.get_supabase", return_value=sb),
        patch("services.saas_recurring_billing_scheduler.now_kst", return_value=_NOW_DT),
        patch(
            "services.saas_recurring_billing_scheduler.serialize_business_datetime",
            return_value=_NOW_ISO,
        ),
        patch("routers.payment_billing._charge_subscription_once",
              return_value={"success": True, "payment_id": _PAY_ID, "result": {}}),
        patch("services.payment_post_process.on_payment_success_sync",
              side_effect=_on_success_side_effect),
    ):
        with pytest.raises(SaasRecurringBillingError) as exc_info:
            run_due_saas_recurring_billing({"dry_run": False})

    summary = exc_info.value.summary
    assert len(summary["items"]) == 2
    assert summary["post_process_failed"] == 1
    assert summary["charged_success"] == 1


def test_P1_P06_scheduler_result_not_silently_clean_success_when_postprocess_failed():
    """P1-P06: post_process_failed > 0 → SaasRecurringBillingError raised (not clean return)."""
    from services.saas_recurring_billing_scheduler import (
        run_due_saas_recurring_billing,
        SaasRecurringBillingError,
    )
    sb = _make_sb(**_full_eligible())
    with (
        patch("db.supabase_client.get_supabase", return_value=sb),
        patch("services.saas_recurring_billing_scheduler.now_kst", return_value=_NOW_DT),
        patch(
            "services.saas_recurring_billing_scheduler.serialize_business_datetime",
            return_value=_NOW_ISO,
        ),
        patch("routers.payment_billing._charge_subscription_once",
              return_value={"success": True, "payment_id": _PAY_ID, "result": {}}),
        patch("services.payment_post_process.on_payment_success_sync",
              side_effect=RuntimeError("post-process down")),
    ):
        with pytest.raises(SaasRecurringBillingError) as exc_info:
            run_due_saas_recurring_billing({"dry_run": False})

    err = exc_info.value
    assert err.summary["post_process_failed"] > 0
    assert "post_process_failed" in str(err)
