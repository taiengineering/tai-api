"""WP-1C-B2-B: Public Data Scheduler Bridge tests — PB01~PB13 + handler registration."""
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
    _make_completion_resolver,
    tick_public_data_sources,
)

_NOW = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)


def _result(status: RunStatus, source_id="src-a", finished_at=None) -> RunResult:
    return RunResult(
        run_id=str(uuid4()),
        source_id=source_id,
        status=status,
        started_at=_NOW,
        finished_at=finished_at or _NOW,
    )


def _fake_store(due_sources: list[str]) -> MagicMock:
    store = MagicMock()
    store.list_due_sources.return_value = due_sources
    return store


# ---------------------------------------------------------------------------
# PB01 — no due sources → empty result
# ---------------------------------------------------------------------------

def test_pb01_no_due_sources():
    store = _fake_store([])
    results = tick_public_data_sources(store=store, cadence_seconds=3600)
    assert results == []


# ---------------------------------------------------------------------------
# PB02 — due source → execute_due_source called
# ---------------------------------------------------------------------------

def test_pb02_due_source_executed():
    store = _fake_store(["src-a"])
    with patch("services.public_data_sync.scheduler_bridge.execute_due_source") as mock_exec:
        mock_exec.return_value = _result(RunStatus.SUCCESS)
        results = tick_public_data_sources(store=store, cadence_seconds=3600)
    mock_exec.assert_called_once()
    assert mock_exec.call_args[0][0] == "src-a"
    assert len(results) == 1


# ---------------------------------------------------------------------------
# PB03 — limit cap respected (default 2)
# ---------------------------------------------------------------------------

def test_pb03_limit_default_two():
    store = _fake_store(["src-a", "src-b", "src-c"])
    executed = []

    def _exec(sid, **kw):
        executed.append(sid)
        return _result(RunStatus.SUCCESS, source_id=sid)

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", side_effect=_exec):
        tick_public_data_sources(store=store, cadence_seconds=3600)

    # list_due_sources returns 3 but limit=2 slices to first 2
    assert executed == ["src-a", "src-b"]


# ---------------------------------------------------------------------------
# PB04 — limit > _MAX_LIMIT clamps to _MAX_LIMIT
# ---------------------------------------------------------------------------

def test_pb04_limit_clamps_to_max():
    store = _fake_store(["src-%d" % i for i in range(15)])
    executed = []

    def _exec(sid, **kw):
        executed.append(sid)
        return _result(RunStatus.SUCCESS, source_id=sid)

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", side_effect=_exec):
        tick_public_data_sources(store=store, cadence_seconds=3600, limit=50)

    assert len(executed) == 10  # _MAX_LIMIT = 10


# ---------------------------------------------------------------------------
# PB05 — cadence_seconds default used when not supplied
# ---------------------------------------------------------------------------

def test_pb05_cadence_default():
    store = _fake_store([])
    # Just confirm no error when cadence_seconds not passed (uses default _DEFAULT_CADENCE_SECONDS)
    results = tick_public_data_sources(store=store)
    assert results == []


# ---------------------------------------------------------------------------
# PB06 — SUCCESS → next_due = finished + cadence (via resolver)
# ---------------------------------------------------------------------------

def test_pb06_success_advances_by_cadence():
    finished = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)
    cadence = 3600
    resolver = _make_completion_resolver(cadence_seconds=cadence, retry_delay_seconds=300)
    result = _result(RunStatus.SUCCESS, finished_at=finished)
    next_due, retry = resolver(result)
    assert next_due == finished + timedelta(seconds=cadence)
    assert retry is None


# ---------------------------------------------------------------------------
# PB07 — FAILED → next_due = finished, retry backoff applied
# ---------------------------------------------------------------------------

def test_pb07_failed_sets_retry():
    finished = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)
    retry_delay = 300
    resolver = _make_completion_resolver(cadence_seconds=3600, retry_delay_seconds=retry_delay)
    result = _result(RunStatus.FAILED, finished_at=finished)
    next_due, retry = resolver(result)
    assert next_due == finished
    assert retry == finished + timedelta(seconds=retry_delay)


# ---------------------------------------------------------------------------
# PB08 — NO_CHANGE advances by cadence (same as SUCCESS)
# ---------------------------------------------------------------------------

def test_pb08_no_change_advances_by_cadence():
    finished = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)
    cadence = 7200
    resolver = _make_completion_resolver(cadence_seconds=cadence, retry_delay_seconds=300)
    result = _result(RunStatus.NO_CHANGE, finished_at=finished)
    next_due, retry = resolver(result)
    assert next_due == finished + timedelta(seconds=cadence)
    assert retry is None


# ---------------------------------------------------------------------------
# PB09 — execute_due_source raises PublicDataSyncError → captured in summary
# ---------------------------------------------------------------------------

def test_pb09_public_data_sync_error_captured():
    store = _fake_store(["src-a"])

    def _exec(sid, **kw):
        raise RuntimeClaimError(source_id=sid)

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", side_effect=_exec):
        with pytest.raises(PublicDataSchedulerTickError) as exc_info:
            tick_public_data_sources(store=store, cadence_seconds=3600)

    summary = exc_info.value.summary
    assert summary["failed"] == 1
    assert summary["tick_errors"][0]["source_id"] == "src-a"
    assert summary["tick_errors"][0]["error"] == "RuntimeClaimError"


# ---------------------------------------------------------------------------
# PB10 — execute_due_source raises generic exception → captured, still raises
# ---------------------------------------------------------------------------

def test_pb10_generic_exception_captured():
    store = _fake_store(["src-a"])

    def _exec(sid, **kw):
        raise OSError("network timeout")

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", side_effect=_exec):
        with pytest.raises(PublicDataSchedulerTickError) as exc_info:
            tick_public_data_sources(store=store, cadence_seconds=3600)

    summary = exc_info.value.summary
    assert summary["failed"] == 1
    assert "network timeout" in summary["tick_errors"][0]["detail"]


# ---------------------------------------------------------------------------
# PB11 — direct://public_data_sync_tick registered in DIRECT_HANDLERS
# ---------------------------------------------------------------------------

def test_pb11_handler_registered():
    from services.scheduler.handlers import register_direct_handlers, DIRECT_HANDLERS
    register_direct_handlers()
    assert "direct://public_data_sync_tick" in DIRECT_HANDLERS


# ---------------------------------------------------------------------------
# PB12 — partial failure (one succeeds, one fails) → errors in summary
# ---------------------------------------------------------------------------

def test_pb12_partial_failure():
    store = _fake_store(["src-a", "src-b"])
    call_count = [0]

    def _exec(sid, **kw):
        call_count[0] += 1
        if sid == "src-a":
            return _result(RunStatus.SUCCESS, source_id=sid)
        raise RuntimeFencedError(run_id="r1", source_id=sid)

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", side_effect=_exec):
        with pytest.raises(PublicDataSchedulerTickError) as exc_info:
            tick_public_data_sources(store=store, cadence_seconds=3600, limit=2)

    summary = exc_info.value.summary
    assert summary["succeeded"] == 1
    assert summary["failed"] == 1
    assert summary["tick_errors"][0]["source_id"] == "src-b"


# ---------------------------------------------------------------------------
# PB13 — result dict has expected keys
# ---------------------------------------------------------------------------

def test_pb13_result_dict_keys():
    store = _fake_store(["src-a"])

    def _exec(sid, **kw):
        return _result(RunStatus.SUCCESS, source_id=sid)

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", side_effect=_exec):
        results = tick_public_data_sources(store=store, cadence_seconds=3600)

    assert len(results) == 1
    row = results[0]
    assert "source_id" in row
    assert "run_id" in row
    assert "status" in row
    assert row["status"] == "SUCCESS"


# ---------------------------------------------------------------------------
# PB14 — execute_due_source returns None (skipped) → not in results
# ---------------------------------------------------------------------------

def test_pb14_skipped_source_not_in_results():
    store = _fake_store(["src-a"])

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", return_value=None):
        results = tick_public_data_sources(store=store, cadence_seconds=3600)

    assert results == []


# ---------------------------------------------------------------------------
# PB15 — PublicDataSchedulerTickError.summary accessible via getattr (dispatcher compat)
# ---------------------------------------------------------------------------

def test_pb15_error_summary_getattr():
    exc = PublicDataSchedulerTickError({"tick_errors": [], "succeeded": 0, "failed": 1})
    assert getattr(exc, "summary", None) is not None
    assert exc.summary["failed"] == 1
