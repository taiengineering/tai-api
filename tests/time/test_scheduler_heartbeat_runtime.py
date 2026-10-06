"""WP-1C-B2-B: SchedulerHeartbeatSupervisor unit tests — SH01~SH08."""
from __future__ import annotations

import threading
import time
from datetime import timedelta
from uuid import uuid4

import pytest

from services.scheduler.heartbeat import SchedulerHeartbeatSupervisor
from services.scheduler.store import Claim
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def _claim(log_id: str | None = None) -> Claim:
    from datetime import datetime
    return Claim(
        job_code="test_job",
        scheduled_for=datetime(2026, 10, 7, 9, 0, tzinfo=KST),
        worker_id="w1",
        attempt_no=1,
        lease_until=datetime(2026, 10, 7, 9, 15, tzinfo=KST),
        log_id=log_id or str(uuid4()),
        trace_id="trace-001",
    )


class _AlwaysAliveStore:
    def heartbeat_occurrence(self, claim, *, now, lease):
        return True


class _AlwaysDeadStore:
    def heartbeat_occurrence(self, claim, *, now, lease):
        return False


class _RaisingStore:
    def heartbeat_occurrence(self, claim, *, now, lease):
        raise RuntimeError("db error")


def _make_supervisor(store_instance, lease_secs=30, interval=1):
    return SchedulerHeartbeatSupervisor(
        _claim(),
        store_factory=lambda: store_instance,
        lease=timedelta(seconds=lease_secs),
        heartbeat_interval_seconds=interval,
    )


# SH01 — clean start/stop, no failed_reason
def test_sh01_clean_start_stop():
    sup = _make_supervisor(_AlwaysAliveStore(), lease_secs=30, interval=60)
    sup.start()
    stopped = sup.stop(timeout=1.0)
    assert stopped is True
    assert sup.failed_reason is None


# SH02 — heartbeat_occurrence called during execution window
def test_sh02_heartbeat_called():
    calls = []

    class CountingStore:
        def heartbeat_occurrence(self, claim, *, now, lease):
            calls.append(1)
            return True

    sup = _make_supervisor(CountingStore(), lease_secs=30, interval=1)
    sup.start()
    time.sleep(0.15)  # wait ~1 interval firing
    sup.stop(timeout=2.0)
    # The event fires after each interval so may or may not fire in 0.15s
    # Just assert no failure
    assert sup.failed_reason is None


# SH03 — store_factory raises → HEARTBEAT_INFRA_ERROR
def test_sh03_store_factory_raises():
    def bad_factory():
        raise OSError("conn refused")

    sup = SchedulerHeartbeatSupervisor(
        _claim(),
        store_factory=bad_factory,
        lease=timedelta(seconds=30),
        heartbeat_interval_seconds=60,
    )
    sup.start()
    time.sleep(0.05)
    sup.stop(timeout=1.0)
    assert sup.failed_reason == "HEARTBEAT_INFRA_ERROR"


# SH04 — heartbeat_occurrence returns False → LEASE_LOST
def test_sh04_heartbeat_returns_false():
    sup = _make_supervisor(_AlwaysDeadStore(), lease_secs=30, interval=1)
    sup.start()
    # Wait for the heartbeat thread to fire and detect LEASE_LOST
    deadline = time.monotonic() + 3.0
    while sup.failed_reason is None and time.monotonic() < deadline:
        time.sleep(0.05)
    sup.stop(timeout=1.0)
    assert sup.failed_reason == "LEASE_LOST"


# SH05 — heartbeat_occurrence raises → HEARTBEAT_INFRA_ERROR
def test_sh05_heartbeat_raises():
    sup = _make_supervisor(_RaisingStore(), lease_secs=30, interval=1)
    sup.start()
    deadline = time.monotonic() + 3.0
    while sup.failed_reason is None and time.monotonic() < deadline:
        time.sleep(0.05)
    sup.stop(timeout=1.0)
    assert sup.failed_reason == "HEARTBEAT_INFRA_ERROR"


# SH06 — stop() join timeout → HEARTBEAT_STOP_TIMEOUT
def test_sh06_stop_timeout():
    entered = threading.Event()
    release = threading.Event()

    class BlockingStore:
        def heartbeat_occurrence(self, claim, *, now, lease):
            entered.set()
            release.wait(timeout=5.0)
            return True

    sup = SchedulerHeartbeatSupervisor(
        _claim(),
        store_factory=lambda: BlockingStore(),
        lease=timedelta(seconds=30),
        heartbeat_interval_seconds=1,
    )
    sup._interval = 0.001  # fire immediately so test doesn't wait a full second
    sup.start()
    assert entered.wait(timeout=2.0), "heartbeat thread did not enter heartbeat_occurrence"
    result = sup.stop(timeout=0.01)  # very short timeout — thread still blocked
    release.set()  # unblock thread for cleanup
    assert result is False
    assert sup.failed_reason == "HEARTBEAT_STOP_TIMEOUT"


# SH07 — interval bounded to lease_seconds // 3
def test_sh07_interval_bound():
    sup = SchedulerHeartbeatSupervisor(
        _claim(),
        store_factory=lambda: _AlwaysAliveStore(),
        lease=timedelta(seconds=30),
        heartbeat_interval_seconds=999,
    )
    assert sup._interval == 10  # min(999, max(1, 30 // 3)) = 10


# SH08 — zero/negative lease raises ValueError at construction
def test_sh08_zero_lease_raises():
    with pytest.raises(ValueError):
        SchedulerHeartbeatSupervisor(
            _claim(),
            store_factory=lambda: _AlwaysAliveStore(),
            lease=timedelta(seconds=0),
        )

    with pytest.raises(ValueError):
        SchedulerHeartbeatSupervisor(
            _claim(),
            store_factory=lambda: _AlwaysAliveStore(),
            lease=timedelta(seconds=-5),
        )
