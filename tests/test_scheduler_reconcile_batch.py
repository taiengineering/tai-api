"""
pytest unit tests for DbStore.reconcile_terminal_wedges() batch implementation.
WO-TAI-PERF-CORE-SCHEDULER-NPLUS1-007  T01–T10

Run: pytest tests/test_scheduler_reconcile_batch.py -v
"""
from __future__ import annotations

import math
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from services.scheduler.db_store import DbStore, _parse_ts
from services.scheduler.store import JobRow, TERMINAL

# ── timezone constants ────────────────────────────────────────────────────────

UTC = timezone.utc
KST = timezone(timedelta(hours=9))

# 2026-10-29T09:00+09:00  ≡  2026-10-29T00:00Z
T_WEDGE     = datetime(2026, 10, 29,  9,  0, tzinfo=KST)
T_WEDGE_UTC = datetime(2026, 10, 29,  0,  0, tzinfo=UTC)   # same instant, UTC
T_OLD       = datetime(2026, 10, 28,  9,  0, tzinfo=KST)   # yesterday's slot
T_NEXT      = datetime(2026, 10, 30,  9,  0, tzinfo=KST)   # mocked next_fire_after result


# ── helpers ───────────────────────────────────────────────────────────────────

def _job(code: str, *, next_run_at=T_WEDGE, expr: str = "0 9 * * *") -> JobRow:
    return JobRow(
        job_code=code,
        cron_expression=expr,
        is_active=True,
        handler="",
        next_run_at=next_run_at,
        payload={},
        timeout_seconds=300,
        http_method="POST",
        endpoint_url="",
    )


class _MockResult:
    """Minimal stand-in for Supabase APIResponse."""
    def __init__(self, data: list, count=None):
        self.data = data
        self.count = count


def _build_sb(log_result: _MockResult):
    """
    Build mock Supabase client that routes sb.table() by table name.
    Returns (sb, log_execute_mock, cfg_chain).
    """
    sb      = MagicMock()
    log_ch  = MagicMock()
    exec_m  = MagicMock(return_value=log_result)
    # chain: .select(...).in_(...).in_(...).in_(...).execute()
    log_ch.select.return_value.in_.return_value.in_.return_value.in_.return_value.execute = exec_m
    cfg_ch  = MagicMock()

    def _table(name):
        return log_ch if name == "cron_job_log" else cfg_ch

    sb.table.side_effect = _table
    return sb, exec_m, cfg_ch


def _make_store(*jobs: JobRow, log_result: _MockResult):
    sb, exec_m, cfg_ch = _build_sb(log_result)
    store = DbStore(sb=sb)
    for j in jobs:
        store.put_job(j)
    return store, exec_m, cfg_ch


# ── T01: no wedge, 1 batch query, no advance ──────────────────────────────────

def test_T01_no_wedge_single_batch_no_advance():
    """0 terminal rows returned → exactly 1 batch query, next_run_at unchanged."""
    jobs  = [_job(f"J{i}") for i in range(3)]
    store, exec_m, cfg_ch = _make_store(
        *jobs, log_result=_MockResult(data=[], count=0)
    )
    saved = {j.job_code: j.next_run_at for j in jobs}

    store.reconcile_terminal_wedges()

    assert exec_m.call_count == 1
    cfg_ch.update.assert_not_called()
    for j in jobs:
        assert j.next_run_at == saved[j.job_code]


# ── T02: exact-slot TERMINAL → advance (all 3 statuses, UTC return) ───────────

@pytest.mark.parametrize("status", sorted(TERMINAL))
def test_T02_exact_slot_wedge_healed(status):
    """Current-slot TERMINAL (all 3 statuses) → advance. Supabase UTC return handled."""
    job        = _job("DAILY")
    log_result = _MockResult(data=[{
        "job_code":      "DAILY",
        "status":        status,
        "scheduled_for": T_WEDGE_UTC.isoformat(),   # Supabase returns UTC
    }], count=1)
    store, _, cfg_ch = _make_store(job, log_result=log_result)

    with patch("services.scheduler.db_store.next_fire_after", return_value=T_NEXT):
        store.reconcile_terminal_wedges()

    assert job.next_run_at == T_NEXT
    assert cfg_ch.update.called


# ── T03: old-slot TERMINAL → no advance ──────────────────────────────────────

def test_T03_old_slot_not_healed():
    """TERMINAL row with yesterday's scheduled_for (different instant) → no advance."""
    job        = _job("DAILY")
    log_result = _MockResult(data=[{
        "job_code":      "DAILY",
        "status":        "SUCCESS",
        "scheduled_for": T_OLD.isoformat(),   # DIFFERENT instant from T_WEDGE
    }], count=1)
    store, _, cfg_ch = _make_store(job, log_result=log_result)

    with patch("services.scheduler.db_store.next_fire_after", return_value=T_NEXT):
        store.reconcile_terminal_wedges()

    assert job.next_run_at == T_WEDGE
    cfg_ch.update.assert_not_called()


# ── T04: timezone-aware instant comparison ────────────────────────────────────

def test_T04_kst_stored_utc_returned_same_instant_healed():
    """KST +09:00 slot stored; Supabase returns UTC +00:00 → same instant → healed."""
    assert T_WEDGE == T_WEDGE_UTC, "guard: T_WEDGE and T_WEDGE_UTC must be the same instant"
    job        = _job("KST_JOB", next_run_at=T_WEDGE)
    log_result = _MockResult(data=[{
        "job_code":      "KST_JOB",
        "status":        "FAILED",
        "scheduled_for": T_WEDGE_UTC.isoformat(),   # +00:00
    }], count=1)
    store, _, cfg_ch = _make_store(job, log_result=log_result)

    with patch("services.scheduler.db_store.next_fire_after", return_value=T_NEXT):
        store.reconcile_terminal_wedges()

    assert job.next_run_at == T_NEXT
    assert cfg_ch.update.called


def test_T04_naive_scheduled_for_skipped_safely():
    """Naive (no tzinfo) scheduled_for → skipped without raising, no advance."""
    job        = _job("NAIVE_JOB", next_run_at=T_WEDGE)
    log_result = _MockResult(data=[{
        "job_code":      "NAIVE_JOB",
        "status":        "SUCCESS",
        "scheduled_for": "2026-10-29T09:00:00",   # no tz — naive
    }], count=1)
    store, _, cfg_ch = _make_store(job, log_result=log_result)

    with patch("services.scheduler.db_store.next_fire_after", return_value=T_NEXT):
        store.reconcile_terminal_wedges()   # must NOT raise TypeError

    assert job.next_run_at == T_WEDGE      # not healed
    cfg_ch.update.assert_not_called()


# ── T05: chunk-split counts ───────────────────────────────────────────────────

@pytest.mark.parametrize("n_jobs,expected_queries", [
    (1,  1),
    (25, 1),
    (26, 2),
    (50, 2),
    (51, 3),
])
def test_T05_chunk_count(n_jobs, expected_queries):
    """ceil(N/25) batch queries issued for N candidate jobs."""
    jobs  = [_job(f"J{i:03d}") for i in range(n_jobs)]
    store, exec_m, _ = _make_store(
        *jobs, log_result=_MockResult(data=[], count=0)
    )

    store.reconcile_terminal_wedges()

    assert exec_m.call_count == expected_queries
    assert exec_m.call_count == math.ceil(n_jobs / 25)


# ── T06: count integrity → fail-closed ───────────────────────────────────────

@pytest.mark.parametrize("count_val,data_len,label", [
    (2,    1, "count_gt_len"),
    (0,    1, "count_lt_len"),
    (None, 1, "count_none"),
    ("x",  1, "count_non_int"),
])
def test_T06_count_mismatch_fail_closed(count_val, data_len, label):
    """count != len(rows) or count is None/non-int → chunk skipped, no advance."""
    job      = _job("DAILY")
    original = job.next_run_at
    row      = {"job_code": "DAILY", "status": "SUCCESS",
                "scheduled_for": T_WEDGE_UTC.isoformat()}
    store, _, cfg_ch = _make_store(
        job, log_result=_MockResult(data=[row] * data_len, count=count_val)
    )

    with patch("services.scheduler.db_store.next_fire_after", return_value=T_NEXT):
        store.reconcile_terminal_wedges()

    assert job.next_run_at == original, f"no advance expected for {label}"
    cfg_ch.update.assert_not_called()


# ── T07: DB exception → no propagation ───────────────────────────────────────

def test_T07_db_exception_no_propagation():
    """Batch query raises Exception → NOT propagated to caller, next_run_at unchanged."""
    jobs  = [_job(f"J{i}") for i in range(3)]
    saved = {j.job_code: j.next_run_at for j in jobs}

    sb     = MagicMock()
    log_ch = MagicMock()
    log_ch.select.return_value.in_.return_value.in_.return_value.in_.return_value \
        .execute.side_effect = Exception("connection timeout")
    cfg_ch = MagicMock()

    def _table(name):
        return log_ch if name == "cron_job_log" else cfg_ch

    sb.table.side_effect = _table
    store = DbStore(sb=sb)
    for j in jobs:
        store.put_job(j)

    store.reconcile_terminal_wedges()   # must NOT raise

    for j in jobs:
        assert j.next_run_at == saved[j.job_code]
    cfg_ch.update.assert_not_called()


# ── T08: CAS 0-row UPDATE — pre-existing local-advance documented ─────────────

def test_T08_cas_rejected_local_advance_preexisting():
    """
    PRE-EXISTING DEFECT DOCUMENTATION — not a test of correct behavior.

    When cron_schedule_config UPDATE returns 0 affected rows (race: another
    worker already advanced the slot), the current code still advances local
    job.next_run_at.  This test records that pre-existing behavior so that a
    future fix is visible as a test change.

    If this assertion fails after a future patch, CAS checking was added — good.
    """
    job      = _job("DAILY")
    original = job.next_run_at

    log_result = _MockResult(data=[{
        "job_code":      "DAILY",
        "status":        "SUCCESS",
        "scheduled_for": T_WEDGE_UTC.isoformat(),
    }], count=1)

    sb     = MagicMock()
    log_ch = MagicMock()
    exec_m = MagicMock(return_value=log_result)
    log_ch.select.return_value.in_.return_value.in_.return_value.in_.return_value.execute = exec_m
    cfg_ch = MagicMock()
    # Simulate CAS returning 0 rows (another worker won the race)
    cfg_ch.update.return_value.eq.return_value.eq.return_value.execute.return_value = \
        _MockResult(data=[], count=0)

    def _table(name):
        return log_ch if name == "cron_job_log" else cfg_ch

    sb.table.side_effect = _table
    store = DbStore(sb=sb)
    store.put_job(job)

    with patch("services.scheduler.db_store.next_fire_after", return_value=T_NEXT):
        store.reconcile_terminal_wedges()

    # PRE-EXISTING: local advance happens even when CAS returned 0 rows.
    assert job.next_run_at == T_NEXT, (
        "Pre-existing: local next_run_at advances regardless of CAS UPDATE row count"
    )
    assert job.next_run_at != original
    assert cfg_ch.update.called   # UPDATE was still attempted


# ── T09: no candidates → no DB call at all ───────────────────────────────────

def test_T09_no_candidates_no_db_call():
    """next_run_at=None or empty cron_expression → no DB call, early return."""
    jobs = [
        _job("J1", next_run_at=None),
        _job("J2", next_run_at=T_WEDGE, expr=""),
    ]
    sb = MagicMock()
    store = DbStore(sb=sb)
    for j in jobs:
        store.put_job(j)

    store.reconcile_terminal_wedges()

    sb.table.assert_not_called()


# ── T10: IN×IN cross-product — wrong-slot row rejected by re-matching ─────────

def test_T10_cross_product_wrong_slot_no_advance():
    """
    IN×IN may return rows for correct job_code but wrong scheduled_for slot.
    The per-row re-matching guard must reject them; neither job advances.
    """
    job_a = _job("JOB_A", next_run_at=T_WEDGE)
    job_b = _job("JOB_B", next_run_at=T_WEDGE)

    # Cross-product artifact: JOB_A row has T_OLD, not T_WEDGE
    log_result = _MockResult(data=[{
        "job_code":      "JOB_A",
        "status":        "SUCCESS",
        "scheduled_for": T_OLD.isoformat(),   # WRONG slot
    }], count=1)
    store, _, cfg_ch = _make_store(job_a, job_b, log_result=log_result)

    with patch("services.scheduler.db_store.next_fire_after", return_value=T_NEXT):
        store.reconcile_terminal_wedges()

    assert job_a.next_run_at == T_WEDGE   # not advanced
    assert job_b.next_run_at == T_WEDGE   # not advanced
    cfg_ch.update.assert_not_called()
