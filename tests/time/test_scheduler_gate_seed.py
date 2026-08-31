"""REV-3: TAI_SCHEDULER_ENABLED gate + T0 next_run_at seed policy."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from services.scheduler.cron_grammar import next_fire_at_or_after
from services.scheduler.dispatcher import tick
from services.scheduler.gate import scheduler_enabled
from services.scheduler.seed import plan_next_run_seeds
from services.scheduler.store import InMemoryStore, JobRow
from services.time import FixedClock, parse_business_datetime

KST = ZoneInfo("Asia/Seoul")
T0 = datetime(2026, 9, 1, 9, 0, tzinfo=KST)


def test_gate_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TAI_SCHEDULER_ENABLED", raising=False)
    assert scheduler_enabled() is False
    monkeypatch.setenv("TAI_SCHEDULER_ENABLED", "0")
    assert scheduler_enabled() is False
    monkeypatch.setenv("TAI_SCHEDULER_ENABLED", "false")
    assert scheduler_enabled() is False


def test_gate_enabled_values(monkeypatch):
    for v in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("TAI_SCHEDULER_ENABLED", v)
        assert scheduler_enabled() is True, v


def test_gate_disabled_does_not_start_thread(monkeypatch):
    import scheduler
    import scheduler_worker

    called: list[bool] = []
    monkeypatch.delenv("TAI_SCHEDULER_ENABLED", raising=False)
    monkeypatch.setattr(scheduler_worker, "start_dispatcher_thread", lambda *a, **k: called.append(True))
    scheduler.scheduler.running = False
    try:
        scheduler.start_scheduler()
        assert called == []
        assert scheduler.scheduler.running is False
    finally:
        scheduler.scheduler.running = False


def test_gate_enabled_starts_handle(monkeypatch):
    import scheduler
    import scheduler_worker

    called: list[bool] = []
    monkeypatch.setenv("TAI_SCHEDULER_ENABLED", "true")
    monkeypatch.setattr(scheduler_worker, "start_dispatcher_thread", lambda *a, **k: called.append(True))
    scheduler.scheduler.running = False
    try:
        scheduler.start_scheduler()
        assert called == [True]
        assert scheduler.scheduler.running is True
    finally:
        scheduler.scheduler.running = False


def test_seed_null_only_and_t0_anchor():
    masters = [
        {"job_code": "daily_health", "is_active": True, "cron_expression": "0 9 * * *"},
        {"job_code": "already", "is_active": True, "cron_expression": "0 9 * * *"},
    ]
    configs = [
        {"job_code": "daily_health", "next_run_at": None, "is_enabled": True},
        {"job_code": "already", "next_run_at": "2026-09-02T09:00:00+09:00", "is_enabled": True},
    ]
    planned = plan_next_run_seeds(masters, configs, T0)
    assert [r["job_code"] for r in planned] == ["daily_health"]
    assert planned[0]["next_run_at"] == T0
    assert planned[0]["next_run_at_iso"].startswith("2026-09-01T09:00")


def test_seed_is_enabled_ignored_master_is_active_authoritative():
    masters = [
        {"job_code": "legacy_off", "is_active": False, "cron_expression": "0 9 * * *"},
        {"job_code": "legacy_on", "is_active": True, "cron_expression": "0 9 * * *"},
    ]
    configs = [
        {"job_code": "legacy_off", "next_run_at": None, "is_enabled": True},
        {"job_code": "legacy_on", "next_run_at": None, "is_enabled": False},
    ]
    planned = plan_next_run_seeds(masters, configs, T0)
    assert [r["job_code"] for r in planned] == ["legacy_on"]


def test_seed_idempotent_second_plan_empty():
    masters = [{"job_code": "daily_health", "is_active": True, "cron_expression": "0 9 * * *"}]
    first = plan_next_run_seeds(
        masters,
        [{"job_code": "daily_health", "next_run_at": None}],
        T0,
    )
    assert len(first) == 1
    second = plan_next_run_seeds(
        masters,
        [{"job_code": "daily_health", "next_run_at": first[0]["next_run_at_iso"]}],
        T0,
    )
    assert second == []


def test_seed_rejects_naive_t0():
    with pytest.raises(ValueError):
        plan_next_run_seeds([], [], datetime(2026, 9, 1, 9, 0))
    with pytest.raises(ValueError):
        parse_business_datetime("2026-09-01T09:00:00")


def test_t0_seed_then_tick_catchup():
    nxt = next_fire_at_or_after("0 9 * * *", T0)
    assert nxt == T0
    planned = plan_next_run_seeds(
        [{"job_code": "daily_health", "is_active": True, "cron_expression": "0 9 * * *"}],
        [{"job_code": "daily_health", "next_run_at": None, "is_enabled": False}],
        T0,
    )
    store = InMemoryStore()
    store.put_job(JobRow(
        "daily_health",
        "0 9 * * *",
        True,
        "direct://daily_health_check",
        planned[0]["next_run_at"],
    ))
    import services.scheduler.dispatcher as disp
    orig = disp.execute_job
    disp.execute_job = lambda j: {"ok": True}
    try:
        out = tick(store, clock=FixedClock(T0), worker_id="w1", tick_cap=1)
        assert len(out) == 1
        assert out[0]["scheduled_for"].startswith("2026-09-01T09:00")
        assert store.jobs["daily_health"].next_run_at == datetime(2026, 9, 2, 9, 0, tzinfo=KST)
    finally:
        disp.execute_job = orig
