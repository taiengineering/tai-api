"""WP-1C-B2-B (PATCH+FIXED-SLOT): Public Data Scheduler Bridge tests — PB01~PB24, FS01~FS08."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from services.public_data_sync.contracts import RunResult, RunStatus
from services.public_data_sync.errors import (
    PublicDataSyncError,
    RuntimeClaimError,
    RuntimeCompletionError,
    RuntimeFencedError,
)
from services.public_data_sync.scheduler_bridge import (
    PublicDataSchedulerTickError,
    _effective_retry_delay,
    _make_completion_resolver,
    tick_public_data_sources,
)

_NOW = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)
_DEFAULT_CADENCE = 3600
_SCHEDULED_FOR = _NOW


def _result(status: RunStatus, source_id="src-a", finished_at=None, error_code=None) -> RunResult:
    return RunResult(
        run_id=str(uuid4()),
        source_id=source_id,
        status=status,
        started_at=_NOW,
        finished_at=finished_at or _NOW,
        error_code=error_code,
    )


def _fake_store(
    due_sources: list[str],
    cadence: int | None = _DEFAULT_CADENCE,
    next_due_at: datetime | str | None = None,
) -> MagicMock:
    """Mock store with uniform get_source_runtime response."""
    store = MagicMock()
    store.list_due_sources.return_value = due_sources
    nd = (next_due_at or _NOW).isoformat() if isinstance(next_due_at or _NOW, datetime) else next_due_at
    store.get_source_runtime.return_value = {
        "source_id": due_sources[0] if due_sources else "src-a",
        "cadence_seconds": cadence,
        "next_due_at": nd,
    }
    return store


# ---------------------------------------------------------------------------
# PB01 — no due sources → empty result
# ---------------------------------------------------------------------------

def test_pb01_no_due_sources():
    store = _fake_store([])
    results = tick_public_data_sources(store=store)
    assert results == []


# ---------------------------------------------------------------------------
# PB02 — due source → execute_due_source called with source_id
# ---------------------------------------------------------------------------

def test_pb02_due_source_executed():
    store = _fake_store(["src-a"])
    with patch("services.public_data_sync.scheduler_bridge.execute_due_source") as mock_exec:
        mock_exec.return_value = _result(RunStatus.SUCCESS)
        results = tick_public_data_sources(store=store)
    mock_exec.assert_called_once()
    assert mock_exec.call_args[0][0] == "src-a"
    assert len(results) == 1


# ---------------------------------------------------------------------------
# PB03 — limit cap respected (default 2)
# ---------------------------------------------------------------------------

def test_pb03_limit_default_two():
    store = MagicMock()
    store.list_due_sources.return_value = ["src-a", "src-b", "src-c"]
    store.get_source_runtime.return_value = {"cadence_seconds": 3600, "next_due_at": _NOW.isoformat()}
    executed = []

    def _exec(sid, **kw):
        executed.append(sid)
        return _result(RunStatus.SUCCESS, source_id=sid)

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", side_effect=_exec):
        tick_public_data_sources(store=store)

    assert executed == ["src-a", "src-b"]


# ---------------------------------------------------------------------------
# PB04 — limit > _MAX_LIMIT clamps to _MAX_LIMIT
# ---------------------------------------------------------------------------

def test_pb04_limit_clamps_to_max():
    store = MagicMock()
    store.list_due_sources.return_value = ["src-%d" % i for i in range(15)]
    store.get_source_runtime.return_value = {"cadence_seconds": 3600, "next_due_at": _NOW.isoformat()}
    executed = []

    def _exec(sid, **kw):
        executed.append(sid)
        return _result(RunStatus.SUCCESS, source_id=sid)

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", side_effect=_exec):
        tick_public_data_sources(store=store, limit=50)

    assert len(executed) == 10


# ---------------------------------------------------------------------------
# PB05 — default params work without explicit cadence
# ---------------------------------------------------------------------------

def test_pb05_no_explicit_cadence_needed():
    store = _fake_store([])
    results = tick_public_data_sources(store=store)
    assert results == []


# ---------------------------------------------------------------------------
# PB06 — SUCCESS → next_due anchored to scheduled_for + cadence
# ---------------------------------------------------------------------------

def test_pb06_success_advances_by_cadence():
    scheduled = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)
    finished = scheduled + timedelta(minutes=20)
    cadence = 3600
    resolver = _make_completion_resolver(cadence, 3600, scheduled)
    result = _result(RunStatus.SUCCESS, finished_at=finished)
    next_due, retry = resolver(result)
    assert next_due == scheduled + timedelta(seconds=cadence)
    assert retry is None


# ---------------------------------------------------------------------------
# PB07 — FAILED → next_due = scheduled_for, retry backoff from finished
# ---------------------------------------------------------------------------

def test_pb07_failed_next_due_is_scheduled_for():
    scheduled = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)
    finished = scheduled + timedelta(minutes=25)
    retry_delay = 3600
    resolver = _make_completion_resolver(3600, retry_delay, scheduled)
    result = _result(RunStatus.FAILED, finished_at=finished)
    next_due, retry = resolver(result)
    assert next_due == scheduled
    assert retry == finished + timedelta(seconds=retry_delay)


# ---------------------------------------------------------------------------
# PB08 — NO_CHANGE advances by cadence (same as SUCCESS)
# ---------------------------------------------------------------------------

def test_pb08_no_change_advances_by_cadence():
    scheduled = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)
    finished = scheduled + timedelta(minutes=10)
    cadence = 7200
    resolver = _make_completion_resolver(cadence, 3600, scheduled)
    result = _result(RunStatus.NO_CHANGE, finished_at=finished)
    next_due, retry = resolver(result)
    assert next_due == scheduled + timedelta(seconds=cadence)
    assert retry is None


# ---------------------------------------------------------------------------
# PB09 — PublicDataSyncError → captured in summary
# ---------------------------------------------------------------------------

def test_pb09_public_data_sync_error_captured():
    store = _fake_store(["src-a"])

    def _exec(sid, **kw):
        raise RuntimeClaimError(source_id=sid)

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", side_effect=_exec):
        with pytest.raises(PublicDataSchedulerTickError) as exc_info:
            tick_public_data_sources(store=store)

    summary = exc_info.value.summary
    assert summary["failed"] == 1
    assert summary["tick_errors"][0]["source_id"] == "src-a"
    assert summary["tick_errors"][0]["error"] == "RuntimeClaimError"


# ---------------------------------------------------------------------------
# PB10 — generic exception → type only, no raw message
# ---------------------------------------------------------------------------

def test_pb10_generic_exception_captured():
    store = _fake_store(["src-a"])

    def _exec(sid, **kw):
        raise OSError("network timeout")

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", side_effect=_exec):
        with pytest.raises(PublicDataSchedulerTickError) as exc_info:
            tick_public_data_sources(store=store)

    summary = exc_info.value.summary
    assert summary["tick_errors"][0]["error"] == "OSError"
    assert "network timeout" not in str(summary)


# ---------------------------------------------------------------------------
# PB11 — handler registration
# ---------------------------------------------------------------------------

def test_pb11_handler_registered():
    from services.scheduler.handlers import register_direct_handlers, DIRECT_HANDLERS
    register_direct_handlers()
    assert "direct://public_data_sync_tick" in DIRECT_HANDLERS


# ---------------------------------------------------------------------------
# PB12 — partial failure
# ---------------------------------------------------------------------------

def test_pb12_partial_failure():
    store = MagicMock()
    store.list_due_sources.return_value = ["src-a", "src-b"]
    store.get_source_runtime.return_value = {"cadence_seconds": 3600, "next_due_at": _NOW.isoformat()}

    def _exec(sid, **kw):
        if sid == "src-a":
            return _result(RunStatus.SUCCESS, source_id=sid)
        raise RuntimeFencedError(run_id="r1", source_id=sid)

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", side_effect=_exec):
        with pytest.raises(PublicDataSchedulerTickError) as exc_info:
            tick_public_data_sources(store=store, limit=2)

    summary = exc_info.value.summary
    assert summary["succeeded"] == 1
    assert summary["failed"] == 1


# ---------------------------------------------------------------------------
# PB13 — result dict keys
# ---------------------------------------------------------------------------

def test_pb13_result_dict_keys():
    store = _fake_store(["src-a"])

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source",
               return_value=_result(RunStatus.SUCCESS)):
        results = tick_public_data_sources(store=store)

    row = results[0]
    assert "source_id" in row and "run_id" in row and "status" in row
    assert row["status"] == "SUCCESS"


# ---------------------------------------------------------------------------
# PB14 — None result (claim skipped) → not in results, no error
# ---------------------------------------------------------------------------

def test_pb14_skipped_source_not_in_results():
    store = _fake_store(["src-a"])
    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", return_value=None):
        results = tick_public_data_sources(store=store)
    assert results == []


# ---------------------------------------------------------------------------
# PB15 — PublicDataSchedulerTickError.summary via getattr
# ---------------------------------------------------------------------------

def test_pb15_error_summary_getattr():
    exc = PublicDataSchedulerTickError({"tick_errors": [], "succeeded": 0, "failed": 1})
    assert getattr(exc, "summary", None) is not None
    assert exc.summary["failed"] == 1


# ---------------------------------------------------------------------------
# PB16 — runtime cadence_seconds used per source
# ---------------------------------------------------------------------------

def test_pb16_runtime_cadence_used():
    source_cadence = 604800
    scheduled = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)
    finished = scheduled + timedelta(minutes=30)
    store = _fake_store(["src-a"], cadence=source_cadence, next_due_at=scheduled)
    captured = []

    def _exec(sid, completion_state_resolver=None, **kw):
        r = _result(RunStatus.SUCCESS, source_id=sid, finished_at=finished)
        if completion_state_resolver:
            next_due, retry = completion_state_resolver(r)
            captured.append((next_due, retry))
        return r

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", side_effect=_exec):
        tick_public_data_sources(store=store)

    assert len(captured) == 1
    next_due, retry = captured[0]
    assert next_due == scheduled + timedelta(seconds=source_cadence)
    assert retry is None


# ---------------------------------------------------------------------------
# PB17 — scheduled_for = runtime.next_due_at
# ---------------------------------------------------------------------------

def test_pb17_scheduled_for_from_runtime():
    expected = datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)
    store = MagicMock()
    store.list_due_sources.return_value = ["src-a"]
    store.get_source_runtime.return_value = {
        "cadence_seconds": 3600,
        "next_due_at": expected.isoformat(),
    }
    captured = []

    def _exec(sid, scheduled_for=None, **kw):
        captured.append(scheduled_for)
        return _result(RunStatus.SUCCESS, source_id=sid)

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", side_effect=_exec):
        tick_public_data_sources(store=store)

    assert len(captured) == 1
    sf = captured[0]
    assert sf is not None
    assert sf.hour == expected.hour and sf.day == expected.day


# ---------------------------------------------------------------------------
# PB18 — missing cadence → CONFIG_CADENCE_MISSING
# ---------------------------------------------------------------------------

def test_pb18_missing_cadence_skips_source():
    store = _fake_store(["src-a"], cadence=None)
    executed = []

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source",
               side_effect=lambda sid, **kw: executed.append(sid)):
        with pytest.raises(PublicDataSchedulerTickError) as exc_info:
            tick_public_data_sources(store=store)

    assert executed == []
    assert exc_info.value.summary["tick_errors"][0]["error"] == "CONFIG_CADENCE_MISSING"


def test_pb18b_zero_cadence_skips_source():
    store = _fake_store(["src-a"], cadence=0)
    with pytest.raises(PublicDataSchedulerTickError) as exc_info:
        with patch("services.public_data_sync.scheduler_bridge.execute_due_source"):
            tick_public_data_sources(store=store)
    assert exc_info.value.summary["tick_errors"][0]["error"] == "CONFIG_CADENCE_MISSING"


# ---------------------------------------------------------------------------
# PB19 — FAILED result → PublicDataSchedulerTickError
# ---------------------------------------------------------------------------

def test_pb19_failed_result_raises():
    store = _fake_store(["src-a"])
    with patch("services.public_data_sync.scheduler_bridge.execute_due_source",
               return_value=_result(RunStatus.FAILED, error_code="ADAPTER_ERROR")):
        with pytest.raises(PublicDataSchedulerTickError) as exc_info:
            tick_public_data_sources(store=store)

    err = exc_info.value.summary["tick_errors"][0]
    assert err["error"] == "SOURCE_EXECUTION_FAILED"
    assert err["status"] == "FAILED"
    assert err["error_code"] == "ADAPTER_ERROR"
    assert "error_message" not in err


# ---------------------------------------------------------------------------
# PB20 — PARTIAL result → PublicDataSchedulerTickError
# ---------------------------------------------------------------------------

def test_pb20_partial_result_raises():
    store = _fake_store(["src-a"])
    with patch("services.public_data_sync.scheduler_bridge.execute_due_source",
               return_value=_result(RunStatus.PARTIAL)):
        with pytest.raises(PublicDataSchedulerTickError):
            tick_public_data_sources(store=store)


# ---------------------------------------------------------------------------
# PB21 — secret-safe exception
# ---------------------------------------------------------------------------

def test_pb21_exception_secret_safe():
    secret = "Authorization: Bearer SUPER_SECRET_123"
    store = _fake_store(["src-a"])

    def _exec(sid, **kw):
        raise RuntimeError(secret)

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", side_effect=_exec):
        with pytest.raises(PublicDataSchedulerTickError) as exc_info:
            tick_public_data_sources(store=store)

    exc = exc_info.value
    assert secret not in str(exc)
    assert secret not in str(exc.summary)


# ---------------------------------------------------------------------------
# PB22 — default retry = 3600
# ---------------------------------------------------------------------------

def test_pb22_default_retry_delay_3600():
    from services.public_data_sync.scheduler_bridge import _DEFAULT_RETRY_DELAY_SECONDS
    assert _DEFAULT_RETRY_DELAY_SECONDS == 3600


# ---------------------------------------------------------------------------
# PB23 — retry clamp min
# ---------------------------------------------------------------------------

def test_pb23_retry_clamp_min():
    assert _effective_retry_delay(10) == 300
    assert _effective_retry_delay(0) == 300
    assert _effective_retry_delay(300) == 300


# ---------------------------------------------------------------------------
# PB24 — retry clamp max
# ---------------------------------------------------------------------------

def test_pb24_retry_clamp_max():
    assert _effective_retry_delay(1_000_000) == 86400
    assert _effective_retry_delay(86400) == 86400


# ============================================================================
# FS01~FS08 — Fixed Daily Slot tests
# ============================================================================

KST = timezone(timedelta(hours=9))


def _kst(y, mo, d, h, m) -> datetime:
    return datetime(y, mo, d, h, m, tzinfo=KST)


# ---------------------------------------------------------------------------
# FS01 — Normal: scheduled 02:10, finished 02:20 → next 다음날 02:10
# ---------------------------------------------------------------------------

def test_fs01_normal_slot_preserved():
    scheduled = _kst(2026, 10, 8, 2, 10)
    finished = _kst(2026, 10, 8, 2, 20)
    resolver = _make_completion_resolver(86400, 3600, scheduled)
    result = _result(RunStatus.SUCCESS, finished_at=finished)
    next_due, retry = resolver(result)
    assert next_due == _kst(2026, 10, 9, 2, 10)
    assert retry is None


# ---------------------------------------------------------------------------
# FS02 — Long run: scheduled 04:10, finished 06:30 → next 다음날 04:10
# ---------------------------------------------------------------------------

def test_fs02_long_run_slot_preserved():
    scheduled = _kst(2026, 10, 8, 4, 10)
    finished = _kst(2026, 10, 8, 6, 30)
    resolver = _make_completion_resolver(86400, 3600, scheduled)
    result = _result(RunStatus.NO_CHANGE, finished_at=finished)
    next_due, retry = resolver(result)
    assert next_due == _kst(2026, 10, 9, 4, 10)
    # Must NOT be finished + 24h
    assert next_due != finished + timedelta(seconds=86400)


# ---------------------------------------------------------------------------
# FS03 — Multi-day outage: scheduled 10/7 02:10, finished 10/10 05:00
#          → next 10/11 02:10 (no catch-up storm)
# ---------------------------------------------------------------------------

def test_fs03_multiday_outage_no_catchup():
    scheduled = _kst(2026, 10, 7, 2, 10)
    finished = _kst(2026, 10, 10, 5, 0)
    resolver = _make_completion_resolver(86400, 3600, scheduled)
    result = _result(RunStatus.SUCCESS, finished_at=finished)
    next_due, retry = resolver(result)
    assert next_due == _kst(2026, 10, 11, 2, 10)
    # Verify only one next_due returned (no list of catch-up dates)
    assert retry is None


# ---------------------------------------------------------------------------
# FS04 — FAILED: scheduled 02:10, finished 02:25, retry 3600
#          → next_due=02:10, retry_not_before=03:25
# ---------------------------------------------------------------------------

def test_fs04_failed_preserves_slot():
    scheduled = _kst(2026, 10, 8, 2, 10)
    finished = _kst(2026, 10, 8, 2, 25)
    resolver = _make_completion_resolver(86400, 3600, scheduled)
    result = _result(RunStatus.FAILED, finished_at=finished)
    next_due, retry = resolver(result)
    assert next_due == scheduled
    assert retry == finished + timedelta(seconds=3600)
    assert retry == _kst(2026, 10, 8, 3, 25)


# ---------------------------------------------------------------------------
# FS05 — Retry success: original scheduled 02:10, retry finished 03:40
#          → next 다음날 02:10 (NOT 03:40 + 24h)
# ---------------------------------------------------------------------------

def test_fs05_retry_success_anchors_to_original_slot():
    original_scheduled = _kst(2026, 10, 8, 2, 10)
    retry_finished = _kst(2026, 10, 8, 3, 40)
    # On retry, the bridge passes the original next_due_at as scheduled_for
    resolver = _make_completion_resolver(86400, 3600, original_scheduled)
    result = _result(RunStatus.SUCCESS, finished_at=retry_finished)
    next_due, retry = resolver(result)
    assert next_due == _kst(2026, 10, 9, 2, 10)
    # Must NOT drift to retry_finished + 24h
    assert next_due != retry_finished + timedelta(seconds=86400)


# ---------------------------------------------------------------------------
# FS06 — NO_CHANGE preserves slot, retry_not_before = None
# ---------------------------------------------------------------------------

def test_fs06_no_change_slot_preserved():
    scheduled = _kst(2026, 10, 8, 2, 10)
    finished = scheduled + timedelta(minutes=5)
    resolver = _make_completion_resolver(86400, 3600, scheduled)
    result = _result(RunStatus.NO_CHANGE, finished_at=finished)
    next_due, retry = resolver(result)
    assert next_due == _kst(2026, 10, 9, 2, 10)
    assert retry is None


# ---------------------------------------------------------------------------
# FS07 — PARTIAL: slot preserved, retry applied, aggregate FAILED
# ---------------------------------------------------------------------------

def test_fs07_partial_slot_preserved():
    scheduled = _kst(2026, 10, 8, 2, 10)
    finished = scheduled + timedelta(minutes=40)
    resolver = _make_completion_resolver(86400, 3600, scheduled)
    result = _result(RunStatus.PARTIAL, finished_at=finished)
    next_due, retry = resolver(result)
    assert next_due == scheduled
    assert retry == finished + timedelta(seconds=3600)


def test_fs07b_partial_raises_scheduler_failed():
    """PARTIAL result → PublicDataSchedulerTickError (scheduler aggregate FAILED)."""
    store = _fake_store(["src-a"], next_due_at=_kst(2026, 10, 8, 2, 10))
    with patch("services.public_data_sync.scheduler_bridge.execute_due_source",
               return_value=_result(RunStatus.PARTIAL)):
        with pytest.raises(PublicDataSchedulerTickError):
            tick_public_data_sources(store=store)


# ---------------------------------------------------------------------------
# FS08 — next_due_at missing → CONFIG_NEXT_DUE_MISSING, no execute call
# ---------------------------------------------------------------------------

def test_fs08_missing_next_due_skips_source():
    store = MagicMock()
    store.list_due_sources.return_value = ["src-a"]
    store.get_source_runtime.return_value = {
        "cadence_seconds": 86400,
        "next_due_at": None,
    }
    executed = []

    def _exec(sid, **kw):
        executed.append(sid)

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", side_effect=_exec):
        with pytest.raises(PublicDataSchedulerTickError) as exc_info:
            tick_public_data_sources(store=store)

    assert executed == []
    assert exc_info.value.summary["tick_errors"][0]["error"] == "CONFIG_NEXT_DUE_MISSING"
