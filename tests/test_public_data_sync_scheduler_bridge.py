"""WP-1C-B2-B (PATCH): Public Data Scheduler Bridge tests — PB01~PB24 + handler."""
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


def _result(status: RunStatus, source_id="src-a", finished_at=None, error_code=None) -> RunResult:
    return RunResult(
        run_id=str(uuid4()),
        source_id=source_id,
        status=status,
        started_at=_NOW,
        finished_at=finished_at or _NOW,
        error_code=error_code,
    )


def _fake_store(due_sources: list[str], cadence: int | None = _DEFAULT_CADENCE) -> MagicMock:
    """Mock store: list_due_sources returns given list; get_source_runtime returns cadence."""
    store = MagicMock()
    store.list_due_sources.return_value = due_sources
    store.get_source_runtime.return_value = {
        "source_id": due_sources[0] if due_sources else "src-a",
        "cadence_seconds": cadence,
        "next_due_at": _NOW.isoformat(),
    }
    return store


def _fake_store_per_source(due_sources: list[str], runtimes: dict) -> MagicMock:
    """Mock store with per-source get_source_runtime responses."""
    store = MagicMock()
    store.list_due_sources.return_value = due_sources
    store.get_source_runtime.side_effect = lambda sid: runtimes.get(sid)
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

    assert len(executed) == 10  # _MAX_LIMIT = 10


# ---------------------------------------------------------------------------
# PB05 — default params work without explicit cadence (source SoT used)
# ---------------------------------------------------------------------------

def test_pb05_no_explicit_cadence_needed():
    store = _fake_store([])
    results = tick_public_data_sources(store=store)
    assert results == []


# ---------------------------------------------------------------------------
# PB06 — SUCCESS → next_due = finished + cadence (via resolver)
# ---------------------------------------------------------------------------

def test_pb06_success_advances_by_cadence():
    finished = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)
    cadence = 3600
    resolver = _make_completion_resolver(cadence_seconds=cadence, retry_delay_seconds=3600)
    result = _result(RunStatus.SUCCESS, finished_at=finished)
    next_due, retry = resolver(result)
    assert next_due == finished + timedelta(seconds=cadence)
    assert retry is None


# ---------------------------------------------------------------------------
# PB07 — FAILED → next_due = finished, retry backoff applied
# ---------------------------------------------------------------------------

def test_pb07_failed_sets_retry():
    finished = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)
    retry_delay = 3600
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
    resolver = _make_completion_resolver(cadence_seconds=cadence, retry_delay_seconds=3600)
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
            tick_public_data_sources(store=store)

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
            tick_public_data_sources(store=store)

    summary = exc_info.value.summary
    assert summary["failed"] == 1
    assert summary["tick_errors"][0]["error"] == "OSError"
    # raw exception message must NOT appear in the summary
    assert "network timeout" not in str(summary)


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
    assert summary["tick_errors"][0]["source_id"] == "src-b"


# ---------------------------------------------------------------------------
# PB13 — result dict has expected keys (SUCCESS only)
# ---------------------------------------------------------------------------

def test_pb13_result_dict_keys():
    store = _fake_store(["src-a"])

    def _exec(sid, **kw):
        return _result(RunStatus.SUCCESS, source_id=sid)

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", side_effect=_exec):
        results = tick_public_data_sources(store=store)

    assert len(results) == 1
    row = results[0]
    assert "source_id" in row
    assert "run_id" in row
    assert "status" in row
    assert row["status"] == "SUCCESS"


# ---------------------------------------------------------------------------
# PB14 — execute_due_source returns None (skipped) → not in results, no error
# ---------------------------------------------------------------------------

def test_pb14_skipped_source_not_in_results():
    store = _fake_store(["src-a"])

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", return_value=None):
        results = tick_public_data_sources(store=store)

    assert results == []


# ---------------------------------------------------------------------------
# PB15 — PublicDataSchedulerTickError.summary accessible via getattr (dispatcher compat)
# ---------------------------------------------------------------------------

def test_pb15_error_summary_getattr():
    exc = PublicDataSchedulerTickError({"tick_errors": [], "succeeded": 0, "failed": 1})
    assert getattr(exc, "summary", None) is not None
    assert exc.summary["failed"] == 1


# ============================================================================
# PB16~PB24 — PATCH-BRIDGE-CONTRACT-001
# ============================================================================

# ---------------------------------------------------------------------------
# PB16 — runtime cadence_seconds used, not global
# ---------------------------------------------------------------------------

def test_pb16_runtime_cadence_used():
    """Source's own cadence (604800) is used for next_due, not any global value."""
    finished = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)
    source_cadence = 604800  # 1 week

    store = _fake_store(["src-a"], cadence=source_cadence)
    captured_resolver_args = []

    original_make = _make_completion_resolver.__wrapped__ if hasattr(_make_completion_resolver, "__wrapped__") else None

    complete_calls = []

    def _exec(sid, completion_state_resolver=None, **kw):
        # Run the resolver with a fake result to inspect the cadence it uses
        r = _result(RunStatus.SUCCESS, source_id=sid, finished_at=finished)
        if completion_state_resolver:
            next_due, retry = completion_state_resolver(r)
            captured_resolver_args.append((next_due, retry))
        return r

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", side_effect=_exec):
        tick_public_data_sources(store=store)

    assert len(captured_resolver_args) == 1
    next_due, retry = captured_resolver_args[0]
    assert next_due == finished + timedelta(seconds=source_cadence)
    assert retry is None


# ---------------------------------------------------------------------------
# PB17 — scheduled_for = runtime.next_due_at
# ---------------------------------------------------------------------------

def test_pb17_scheduled_for_from_runtime():
    """execute_due_source receives scheduled_for=runtime.next_due_at."""
    expected_scheduled_for = datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)

    store = MagicMock()
    store.list_due_sources.return_value = ["src-a"]
    store.get_source_runtime.return_value = {
        "cadence_seconds": 3600,
        "next_due_at": expected_scheduled_for.isoformat(),
    }

    captured_scheduled_for = []

    def _exec(sid, scheduled_for=None, **kw):
        captured_scheduled_for.append(scheduled_for)
        return _result(RunStatus.SUCCESS, source_id=sid)

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", side_effect=_exec):
        tick_public_data_sources(store=store)

    assert len(captured_scheduled_for) == 1
    sf = captured_scheduled_for[0]
    assert sf is not None
    assert sf.year == expected_scheduled_for.year
    assert sf.month == expected_scheduled_for.month
    assert sf.day == expected_scheduled_for.day
    assert sf.hour == expected_scheduled_for.hour


# ---------------------------------------------------------------------------
# PB18 — cadence_seconds = null → CONFIG_CADENCE_MISSING, execute not called
# ---------------------------------------------------------------------------

def test_pb18_missing_cadence_skips_source():
    store = _fake_store(["src-a"], cadence=None)
    executed = []

    def _exec(sid, **kw):
        executed.append(sid)
        return _result(RunStatus.SUCCESS, source_id=sid)

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", side_effect=_exec):
        with pytest.raises(PublicDataSchedulerTickError) as exc_info:
            tick_public_data_sources(store=store)

    assert executed == []
    summary = exc_info.value.summary
    assert summary["tick_errors"][0]["error"] == "CONFIG_CADENCE_MISSING"
    assert summary["tick_errors"][0]["source_id"] == "src-a"


def test_pb18b_zero_cadence_skips_source():
    store = _fake_store(["src-a"], cadence=0)
    executed = []

    def _exec(sid, **kw):
        executed.append(sid)
        return _result(RunStatus.SUCCESS, source_id=sid)

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source", side_effect=_exec):
        with pytest.raises(PublicDataSchedulerTickError) as exc_info:
            tick_public_data_sources(store=store)

    assert executed == []
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

    summary = exc_info.value.summary
    assert summary["failed"] == 1
    err = summary["tick_errors"][0]
    assert err["error"] == "SOURCE_EXECUTION_FAILED"
    assert err["status"] == "FAILED"
    assert err["error_code"] == "ADAPTER_ERROR"
    # error_message must not appear
    assert "error_message" not in err


# ---------------------------------------------------------------------------
# PB20 — PARTIAL result → PublicDataSchedulerTickError
# ---------------------------------------------------------------------------

def test_pb20_partial_result_raises():
    store = _fake_store(["src-a"])

    with patch("services.public_data_sync.scheduler_bridge.execute_due_source",
               return_value=_result(RunStatus.PARTIAL)):
        with pytest.raises(PublicDataSchedulerTickError) as exc_info:
            tick_public_data_sources(store=store)

    assert exc_info.value.summary["tick_errors"][0]["status"] == "PARTIAL"


# ---------------------------------------------------------------------------
# PB21 — secret-safe exception handling
# ---------------------------------------------------------------------------

def test_pb21_exception_secret_safe():
    """Raw exception message must not appear in summary or error string."""
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
    for err in exc.summary.get("tick_errors", []):
        assert secret not in str(err)


# ---------------------------------------------------------------------------
# PB22 — default retry delay = 3600
# ---------------------------------------------------------------------------

def test_pb22_default_retry_delay_3600():
    from services.public_data_sync.scheduler_bridge import _DEFAULT_RETRY_DELAY_SECONDS
    assert _DEFAULT_RETRY_DELAY_SECONDS == 3600


# ---------------------------------------------------------------------------
# PB23 — retry delay clamp min (10 → 300)
# ---------------------------------------------------------------------------

def test_pb23_retry_clamp_min():
    assert _effective_retry_delay(10) == 300
    assert _effective_retry_delay(0) == 300
    assert _effective_retry_delay(299) == 300
    assert _effective_retry_delay(300) == 300


# ---------------------------------------------------------------------------
# PB24 — retry delay clamp max (1000000 → 86400)
# ---------------------------------------------------------------------------

def test_pb24_retry_clamp_max():
    assert _effective_retry_delay(1_000_000) == 86400
    assert _effective_retry_delay(86401) == 86400
    assert _effective_retry_delay(86400) == 86400
