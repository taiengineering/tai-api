"""KR-01 ~ KR-09 — KECO scheduled refresh RETRY recovery tests.

Verifies that claim_due_targets() includes RETRY in eligible statuses
and that PENDING/FAILED/CONFLICT remain excluded.

All tests use DB mocks — zero external API calls.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch
from uuid import uuid4

import pytest

from services.keco_chemical.contract import (
    TARGET_STATUS_CONFLICT,
    TARGET_STATUS_DONE,
    TARGET_STATUS_EMPTY,
    TARGET_STATUS_FAILED,
    TARGET_STATUS_PENDING,
    TARGET_STATUS_RETRY,
    TARGET_STATUS_RUNNING,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _past() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()


def _future() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=25)).isoformat()


def _make_db_target(status: str, next_refresh_at: str, tid: str | None = None) -> dict:
    return {
        "id": tid or str(uuid4()),
        "target_type": "CAS",
        "target_value": "7664-41-7",
        "attempt_count": 0,
        "status": status,
        "next_refresh_at": next_refresh_at,
    }


def _mock_db_chain(return_rows: list[dict]):
    """Build a mock Supabase query chain that returns given rows."""
    execute_mock = MagicMock()
    execute_mock.data = return_rows

    chain = MagicMock()
    chain.table.return_value = chain
    chain.select.return_value = chain
    chain.in_.return_value = chain
    chain.lte.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.execute.return_value = execute_mock
    chain.update.return_value = chain

    return chain


def _captured_in_statuses(mock_chain) -> list[str] | None:
    """Extract the status list passed to .in_('status', [...])."""
    for c in mock_chain.in_.call_args_list:
        args = c[0]
        if args and args[0] == "status":
            return list(args[1])
    return None


# ─────────────────────────────────────────────────────────────────────────────
# KR-01 — DONE eligible (regression)
# ─────────────────────────────────────────────────────────────────────────────

def test_kr_01_done_eligible():
    """DONE + past next_refresh_at → included in .in_() statuses."""
    target = _make_db_target(TARGET_STATUS_DONE, _past())
    db_chain = _mock_db_chain([target])

    mock_client = MagicMock()
    mock_client.schema.return_value = db_chain

    from services.keco_chemical.store import KecoReferenceStore

    store = KecoReferenceStore.__new__(KecoReferenceStore)

    with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
        store.claim_due_targets("run-001", 10)

    statuses = _captured_in_statuses(db_chain)
    assert statuses is not None
    assert TARGET_STATUS_DONE in statuses


# ─────────────────────────────────────────────────────────────────────────────
# KR-02 — EMPTY eligible (regression)
# ─────────────────────────────────────────────────────────────────────────────

def test_kr_02_empty_eligible():
    target = _make_db_target(TARGET_STATUS_EMPTY, _past())
    db_chain = _mock_db_chain([target])

    mock_client = MagicMock()
    mock_client.schema.return_value = db_chain

    from services.keco_chemical.store import KecoReferenceStore
    store = KecoReferenceStore.__new__(KecoReferenceStore)

    with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
        store.claim_due_targets("run-001", 10)

    statuses = _captured_in_statuses(db_chain)
    assert statuses is not None
    assert TARGET_STATUS_EMPTY in statuses


# ─────────────────────────────────────────────────────────────────────────────
# KR-03 — RETRY eligible (blocker fix)
# ─────────────────────────────────────────────────────────────────────────────

def test_kr_03_retry_eligible():
    """RETRY + past next_refresh_at → included in .in_() statuses (core blocker)."""
    target = _make_db_target(TARGET_STATUS_RETRY, _past())
    db_chain = _mock_db_chain([target])

    mock_client = MagicMock()
    mock_client.schema.return_value = db_chain

    from services.keco_chemical.store import KecoReferenceStore
    store = KecoReferenceStore.__new__(KecoReferenceStore)

    with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
        result = store.claim_due_targets("run-001", 10)

    statuses = _captured_in_statuses(db_chain)
    assert statuses is not None, "in_() was not called with status filter"
    assert TARGET_STATUS_RETRY in statuses, (
        f"RETRY must be in eligible statuses; got {statuses}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# KR-04 — RETRY future next_refresh_at excluded by lte filter
# ─────────────────────────────────────────────────────────────────────────────

def test_kr_04_retry_future_not_claimed():
    """RETRY with future next_refresh_at → DB returns empty (lte filter excludes it)."""
    db_chain = _mock_db_chain([])  # DB returns nothing (future timestamp > now)

    mock_client = MagicMock()
    mock_client.schema.return_value = db_chain

    from services.keco_chemical.store import KecoReferenceStore
    store = KecoReferenceStore.__new__(KecoReferenceStore)

    with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
        result = store.claim_due_targets("run-001", 10)

    assert result == []
    # Verify lte was called with next_refresh_at
    lte_calls = db_chain.lte.call_args_list
    assert any(c[0][0] == "next_refresh_at" for c in lte_calls), (
        "lte('next_refresh_at', ...) must be called"
    )


# ─────────────────────────────────────────────────────────────────────────────
# KR-05 — FAILED excluded
# ─────────────────────────────────────────────────────────────────────────────

def test_kr_05_failed_not_eligible():
    """FAILED is not in the eligible statuses list."""
    db_chain = _mock_db_chain([])

    mock_client = MagicMock()
    mock_client.schema.return_value = db_chain

    from services.keco_chemical.store import KecoReferenceStore
    store = KecoReferenceStore.__new__(KecoReferenceStore)

    with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
        store.claim_due_targets("run-001", 10)

    statuses = _captured_in_statuses(db_chain)
    assert statuses is not None
    assert TARGET_STATUS_FAILED not in statuses


# ─────────────────────────────────────────────────────────────────────────────
# KR-06 — CONFLICT excluded
# ─────────────────────────────────────────────────────────────────────────────

def test_kr_06_conflict_not_eligible():
    db_chain = _mock_db_chain([])

    mock_client = MagicMock()
    mock_client.schema.return_value = db_chain

    from services.keco_chemical.store import KecoReferenceStore
    store = KecoReferenceStore.__new__(KecoReferenceStore)

    with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
        store.claim_due_targets("run-001", 10)

    statuses = _captured_in_statuses(db_chain)
    assert statuses is not None
    assert TARGET_STATUS_CONFLICT not in statuses


# ─────────────────────────────────────────────────────────────────────────────
# KR-07 — PENDING excluded
# ─────────────────────────────────────────────────────────────────────────────

def test_kr_07_pending_not_eligible():
    db_chain = _mock_db_chain([])

    mock_client = MagicMock()
    mock_client.schema.return_value = db_chain

    from services.keco_chemical.store import KecoReferenceStore
    store = KecoReferenceStore.__new__(KecoReferenceStore)

    with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
        store.claim_due_targets("run-001", 10)

    statuses = _captured_in_statuses(db_chain)
    assert statuses is not None
    assert TARGET_STATUS_PENDING not in statuses


# ─────────────────────────────────────────────────────────────────────────────
# KR-08 — bounded recovery lifecycle: Day2 reclaims Day1 RETRY
# ─────────────────────────────────────────────────────────────────────────────

def test_kr_08_bounded_recovery_lifecycle():
    """RETRY targets from a bounded partial are reclaimed on next scheduled run."""
    from services.keco_chemical.budget import RequestBudget
    from services.keco_chemical.sync import refresh_due_targets

    # Simulate Day1 run: adapter returned bounded SUCCESS (some targets were RETRY).
    # On Day2, store.claim_due_targets returns those RETRY targets because
    # RETRY is now in the eligible list.

    retry_target = {
        "id": "target-B",
        "target_type": "CAS",
        "target_value": "67-56-1",
        "attempt_count": 1,
        "status": TARGET_STATUS_RETRY,
    }

    run_id = str(uuid4())
    store = MagicMock()
    client = MagicMock()
    budget = RequestBudget(limit=9000)

    store.start_exclusive_run.return_value = (run_id, False)
    # Day2: RETRY target is now eligible
    store.claim_due_targets.return_value = [retry_target]

    from services.keco_chemical.sync import SyncTargetResult, SyncBatchResult
    fake_target_result = SyncTargetResult(
        target_id="target-B",
        target_type="CAS",
        target_value="67-56-1",
        status=TARGET_STATUS_DONE,
        api_requests=1,
        source_items=1,
        new_count=0,
        changed_count=1,
        unchanged_count=0,
        fact_insert_count=0,
    )
    from unittest.mock import patch as _patch
    with _patch("services.keco_chemical.sync.sync_one_target", return_value=fake_target_result):
        result = refresh_due_targets(client, store, budget, max_targets=10)

    # Verify claim_due_targets was called (Day2 reclaims)
    store.claim_due_targets.assert_called_once()
    assert result.targets_selected == 1
    assert result.changed == 1


# ─────────────────────────────────────────────────────────────────────────────
# KR-09 — FAILED remains manual-only
# ─────────────────────────────────────────────────────────────────────────────

def test_kr_09_failed_remains_manual():
    """FAILED targets are not returned by claim_due_targets (excluded from query)."""
    # DB returns empty because FAILED is not in eligible list
    db_chain = _mock_db_chain([])

    mock_client = MagicMock()
    mock_client.schema.return_value = db_chain

    from services.keco_chemical.store import KecoReferenceStore
    store = KecoReferenceStore.__new__(KecoReferenceStore)

    with patch("services.keco_chemical.store._get_supabase_client", return_value=mock_client):
        result = store.claim_due_targets("run-001", 10)

    assert result == []
    statuses = _captured_in_statuses(db_chain)
    assert TARGET_STATUS_FAILED not in statuses
    # Manual retry path (collect --mode retry) is preserved separately
    # and is not affected by this change (it uses a different query)
