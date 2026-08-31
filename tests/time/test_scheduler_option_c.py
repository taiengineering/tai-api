"""WP-TIME-SCHEDULER-C-01: universe, pg_cron map, handlers, persistence, weekday, TZ."""
from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from services.scheduler.cron_grammar import (
    CronGrammarError,
    assert_named_weekday,
    next_fire_after,
    next_fire_at_or_after,
)
from services.scheduler.dispatcher import tick
from services.scheduler.handlers import DIRECT_HANDLERS, register_direct_handlers
from services.scheduler.store import InMemoryStore, JobRow
from services.time import FixedClock, TAI_TIMEZONE

ROOT = Path(__file__).resolve().parents[2]
TIME = ROOT / "docs" / "time"
KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")
UTC = timezone.utc


def _u():
    return json.loads((TIME / "TAI_SCHEDULER_UNIVERSE_MANIFEST.json").read_text(encoding="utf-8"))


def _p():
    return json.loads((TIME / "TAI_PGCRON_RETIREMENT_MAP.json").read_text(encoding="utf-8"))


def _d():
    return json.loads((TIME / "TAI_CRON_DOW_NORMALIZATION.json").read_text(encoding="utf-8"))


def _clk(instant: datetime) -> FixedClock:
    return FixedClock(instant)


def test_universe_46():
    u = _u()
    assert u["universe_count"] == 46
    assert len(u["jobs"]) == 46
    by = {}
    for j in u["jobs"]:
        by.setdefault(j["source"], []).append(j)
    assert len(by["master"]) == 32
    assert len(by["pgcron"]) == 12
    assert len(by["code"]) == 2
    assert u["master_active"] == 21
    assert sum(1 for j in by["master"] if j["is_active"]) == 21
    assert u["config_count"] == 11
    assert u["master_without_config"] == 21
    assert u["config_without_master"] == 0


def test_pgcron_mapped_12_and_active_state():
    p = _p()
    assert p["mapped"] == 12
    assert len(p["jobs"]) == 12
    assert {j["jobid"] for j in p["jobs"]} == set(range(1, 13))
    assert p["active_old"] == 9
    assert p["inactive_old"] == 3
    inactive = {j["jobid"] for j in p["jobs"] if not j["active_old"]}
    assert inactive == {1, 3, 4}
    assert p["delete_unschedule"] is False
    sql = (ROOT / "docs/sql/20260831_tai_pgcron_retire.sql").read_text(encoding="utf-8")
    assert sql.count("SELECT cron.alter_job(") == 12
    assert "unschedule" not in sql.lower() or "DELETE/unschedule 금지" in sql
    assert "false);" in sql
    assert sql.lower().count("delete from cron") == 0


def test_master_and_config_coverage_sql():
    sql = (ROOT / "docs/sql/20260831_tai_scheduler_runtime_state_up.sql").read_text(encoding="utf-8")
    assert "cron_schedule_config" in sql
    assert "scheduled_for" in sql
    assert "attempt_no" in sql
    assert "lease_until" in sql
    assert "holiday_sync_annual" in sql
    assert "holiday_sync_quarterly" in sql
    for name in ("daily_assignments", "kosha_weekly", "cron_job_log_retention", "business_event_retention"):
        assert name in sql
    assert "safety-materials" in json.dumps(_p())


def test_code_only_after_zero():
    src = ast.parse((ROOT / "scheduler.py").read_text(encoding="utf-8"))
    calls = [
        n for n in ast.walk(src)
        if isinstance(n, ast.Call) and (
            (isinstance(n.func, ast.Attribute) and n.func.attr == "add_job")
            or (isinstance(n.func, ast.Name) and n.func.id == "add_job")
        )
    ]
    assert calls == []
    text = (ROOT / "scheduler.py").read_text(encoding="utf-8")
    assert "register_code_jobs" not in text
    assert "holiday_sync_annual" not in text


def test_direct_handler_uncovered_zero():
    register_direct_handlers()
    u = _u()
    missing = []
    for j in u["jobs"]:
        h = j.get("handler") or ""
        if str(h).startswith("direct://") and h not in DIRECT_HANDLERS:
            missing.append((j["job_code"], h))
    assert missing == []
    active_direct = [
        j for j in u["jobs"]
        if j["is_active"] and str(j.get("endpoint") or "").startswith("direct://")
    ]
    for j in active_direct:
        assert j["endpoint"] in DIRECT_HANDLERS


def test_numeric_weekday_after_zero():
    d = _d()
    assert d["numeric_before"] == 6
    assert d["numeric_after"] == 0
    assert d["contradiction_count"] == 0
    u = _u()
    for j in u["jobs"]:
        expr = j["cron_expression"]
        assert_named_weekday(expr)
    with pytest.raises(CronGrammarError, match="numeric weekday"):
        assert_named_weekday("0 7 * * 1")


def test_non_asia_seoul_trigger_zero():
    text = (ROOT / "scheduler.py").read_text(encoding="utf-8") + (ROOT / "scheduler_worker.py").read_text(encoding="utf-8")
    assert "timezone=\"UTC\"" not in text
    assert "timezone='UTC'" not in text
    from services.scheduler.cron_grammar import trigger_for
    t = trigger_for("0 0 * * *")
    assert getattr(t.timezone, "key", None) == TAI_TIMEZONE.key


def test_weekly_weekday_contract():
    instant = datetime(2026, 8, 31, 8, 0, tzinfo=KST)  # Monday
    nxt = next_fire_after("0 7 * * mon", instant)
    assert nxt.weekday() == 0
    assert nxt.hour == 7
    sun = next_fire_after("0 4 * * sun", instant)
    assert sun.weekday() == 6


def test_duplicate_claim():
    store = InMemoryStore()
    now = datetime(2026, 9, 1, 9, 0, tzinfo=KST)
    job = JobRow("daily_health", "0 9 * * *", True, "direct://daily_health_check", now)
    store.put_job(job)
    a = store.claim(job, "w1", now, timedelta(minutes=15))
    b = store.claim(job, "w2", now, timedelta(minutes=15))
    assert a is not None
    assert b is None


def test_stale_lease_recovery():
    store = InMemoryStore()
    now = datetime(2026, 9, 1, 9, 0, tzinfo=KST)
    job = JobRow("daily_health", "0 9 * * *", True, "direct://daily_health_check", now)
    store.put_job(job)
    first = store.claim(job, "w1", now, timedelta(minutes=15))
    assert first is not None
    later = now + timedelta(minutes=16)
    rec = store.claim(job, "w2", later, timedelta(minutes=15))
    assert rec is not None
    assert rec.attempt_no == 2
    assert rec.scheduled_for == now
    assert rec.worker_id == "w2"


def test_multi_dispatcher_race():
    store = InMemoryStore()
    now = datetime(2026, 9, 1, 0, 0, tzinfo=KST)
    job = JobRow("x", "0 0 * * *", True, "direct://alert_evaluate", now)
    store.put_job(job)
    claims = [store.claim(job, f"w{i}", now, timedelta(minutes=15)) for i in range(5)]
    won = [c for c in claims if c is not None]
    assert len(won) == 1


def test_restart_catchup_does_not_skip():
    store = InMemoryStore()
    missed = datetime(2026, 8, 31, 9, 0, tzinfo=KST)
    job = JobRow(
        "daily_health",
        "0 9 * * *",
        True,
        "direct://daily_health_check",
        missed,
    )
    store.put_job(job)

    def _fake_exec(j):
        return {"ok": True}

    import services.scheduler.dispatcher as disp
    orig = disp.execute_job
    disp.execute_job = _fake_exec
    try:
        now = datetime(2026, 9, 2, 10, 0, tzinfo=KST)
        out = tick(store, clock=_clk(now), worker_id="w1", tick_cap=1)
        assert len(out) == 1
        assert out[0]["scheduled_for"].startswith("2026-08-31T09:00")
        assert store.jobs["daily_health"].next_run_at == datetime(2026, 9, 1, 9, 0, tzinfo=KST)
        out2 = tick(store, clock=_clk(now), worker_id="w1", tick_cap=1)
        assert out2[0]["scheduled_for"].startswith("2026-09-01T09:00")
    finally:
        disp.execute_job = orig


def test_tz_matrix_same_kst_scheduled_for():
    expr = "0 0 * * *"
    utc_instant = datetime(2026, 8, 31, 15, 0, tzinfo=UTC)  # Sep 1 00:00 KST
    instants = [
        utc_instant,
        utc_instant.astimezone(KST),
        utc_instant.astimezone(NY),
    ]
    fires = [next_fire_at_or_after(expr, i) for i in instants]
    assert len({f.isoformat() for f in fires}) == 1
    assert fires[0] == datetime(2026, 9, 1, 0, 0, tzinfo=KST)


def test_sun_mon_month_year_and_utc_next_day_kst():
    # Sunday → Monday weekly
    sun = datetime(2026, 8, 30, 8, 0, tzinfo=KST)
    mon_fire = next_fire_after("0 7 * * mon", sun)
    assert mon_fire.date().isoformat() == "2026-08-31"
    # month end
    eom = datetime(2026, 8, 31, 23, 0, tzinfo=KST)
    nxt = next_fire_after("0 0 * * *", eom)
    assert nxt == datetime(2026, 9, 1, 0, 0, tzinfo=KST)
    # year end
    eoy = datetime(2026, 12, 31, 23, 0, tzinfo=KST)
    nxt_y = next_fire_after("0 0 * * *", eoy)
    assert nxt_y == datetime(2027, 1, 1, 0, 0, tzinfo=KST)
    # 23:xx UTC is next calendar day KST
    late_utc = datetime(2026, 8, 31, 15, 30, tzinfo=UTC)
    fire = next_fire_at_or_after("0 0 * * *", late_utc)
    assert fire.date().isoformat() == "2026-09-02" or fire == datetime(2026, 9, 1, 0, 0, tzinfo=KST)
    # 15:30 UTC = 00:30 Sep 1 KST, next midnight KST is Sep 2 00:00
    assert fire == datetime(2026, 9, 2, 0, 0, tzinfo=KST)


def test_kosha_weekly_safety_materials_preserved():
    import inspect
    from services.scheduler import handlers as h
    src = inspect.getsource(h._run_kosha_safety_materials)
    assert "safety-materials" in src
    assert "/kosha-collect/run" in src
    p = _p()
    weekly = next(j for j in p["jobs"] if j["jobid"] == 9)
    assert "target=safety-materials" in weekly["command"]


def test_scheduler_py_business_registration_zero():
    text = (ROOT / "scheduler.py").read_text(encoding="utf-8")
    assert "BackgroundScheduler" not in text
    assert "CronTrigger.from_crontab" not in text
    assert "register_code_jobs" not in text
    src = ast.parse(text)
    adds = [
        n for n in ast.walk(src)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "add_job"
    ]
    assert adds == []


def test_occurrence_identity_is_persisted_next_run():
    store = InMemoryStore()
    scheduled = datetime(2026, 9, 1, 9, 0, tzinfo=KST)
    job = JobRow("daily_health", "0 9 * * *", True, "direct://daily_health_check", scheduled)
    store.put_job(job)
    claim = store.claim(job, "w1", scheduled, timedelta(minutes=15))
    assert claim is not None
    assert claim.scheduled_for == scheduled
    assert (claim.job_code, claim.scheduled_for) == (job.job_code, job.next_run_at)


def test_retention_handler_forbids_localtimestamp():
    import inspect
    from services.scheduler import handlers as h
    src = inspect.getsource(h._run_cron_job_log_retention)
    assert "localtimestamp" not in src.lower()
    assert "now_kst" in src
