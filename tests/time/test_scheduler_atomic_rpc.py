"""WP-TIME-SCHEDULER-C-01 REV-2: atomic claim/complete RPC semantics via DbStore fake."""
from __future__ import annotations

import ast
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from services.scheduler.cron_grammar import next_fire_after
from services.scheduler.db_store import DbStore
from services.scheduler.dispatcher import tick
from services.scheduler.handlers import DIRECT_HANDLERS, register_direct_handlers
from services.time import FixedClock
from tests.time.scheduler_atomic_fake import FakeSchedulerSB, SchedulerStateDB

ROOT = Path(__file__).resolve().parents[2]
KST = ZoneInfo("Asia/Seoul")
SQL_UP = ROOT / "docs/sql/20260901_tai_scheduler_atomic_state_machine_up.sql"
SQL_DOWN = ROOT / "docs/sql/20260901_tai_scheduler_atomic_state_machine_down.sql"
LEASE = timedelta(minutes=15)
NOW = datetime(2026, 9, 1, 9, 0, tzinfo=KST)


def _clk(instant: datetime = NOW) -> FixedClock:
    return FixedClock(instant)


def test_sql_atomic_rpc_contract():
    up = SQL_UP.read_text(encoding="utf-8")
    down = SQL_DOWN.read_text(encoding="utf-8")
    assert "EXECUTE = 0" in up
    assert "ON CONFLICT (job_code, scheduled_for)" in up
    assert "DO NOTHING" in up
    assert "attempt_no = cron_job_log.attempt_no + 1" in up
    assert "lease_until <= p_now" in up
    assert "AND status = 'RUNNING'" in up
    assert "GET DIAGNOSTICS v_updated = ROW_COUNT" in up
    assert "RETURN true" in up
    assert "RETURN false" in up
    assert "cron_job_log_occurrence_uidx" in up
    assert "DROP INDEX" not in down.upper()
    assert down.count("DROP FUNCTION") == 2
    claim_body = up.split("$fn$")[1]
    assert "SELECT " not in claim_body
    disp = (ROOT / "services/scheduler/dispatcher.py").read_text(encoding="utf-8")
    tree = ast.parse(disp)
    attrs = [
        n.func.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr in ("complete", "complete_and_advance", "advance_next_run")
    ]
    assert attrs == ["complete_and_advance"]


def test_first_claim_race():
    db = SchedulerStateDB()
    db.seed_job("daily_health", "0 9 * * *", NOW)
    barrier = threading.Barrier(3)
    won = []

    def worker(wid: str):
        store = DbStore(sb=FakeSchedulerSB(db))
        store.refresh(NOW)
        job = store.jobs["daily_health"]
        barrier.wait()
        claim = store.claim(job, wid, NOW, LEASE)
        if claim is not None:
            won.append(claim)

    threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(won) == 1
    assert won[0].attempt_no == 1
    assert len(db.logs) == 1


def test_stale_reclaim_cas():
    db = SchedulerStateDB()
    db.seed_job("daily_health", "0 9 * * *", NOW)
    store0 = DbStore(sb=FakeSchedulerSB(db))
    store0.refresh(NOW)
    first = store0.claim(store0.jobs["daily_health"], "A", NOW, LEASE)
    assert first is not None
    assert first.attempt_no == 1
    later = NOW + timedelta(minutes=16)
    barrier = threading.Barrier(2)
    won = []

    def worker(wid: str):
        store = DbStore(sb=FakeSchedulerSB(db))
        store.refresh(later)
        job = store.jobs["daily_health"]
        job.next_run_at = NOW
        barrier.wait()
        claim = store.claim(job, wid, later, LEASE)
        if claim is not None:
            won.append(claim)

    threads = [threading.Thread(target=worker, args=(wid,)) for wid in ("B", "C")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(won) == 1
    assert won[0].attempt_no == 2
    row = next(iter(db.logs.values()))
    assert row["attempt_no"] == 2


def test_fencing():
    db = SchedulerStateDB()
    db.seed_job("daily_health", "0 9 * * *", NOW)
    store = DbStore(sb=FakeSchedulerSB(db))
    store.refresh(NOW)
    job = store.jobs["daily_health"]
    a = store.claim(job, "A", NOW, LEASE)
    assert a is not None
    later = NOW + timedelta(minutes=16)
    b = store.claim(job, "B", later, LEASE)
    assert b is not None
    assert b.attempt_no == 2
    nxt = next_fire_after("0 9 * * *", NOW)
    assert store.complete_and_advance(a, "SUCCESS", {"from": "A"}, later, nxt) is True
    row = next(iter(db.logs.values()))
    assert row["status"] == "RUNNING"
    assert row["attempt_no"] == 2
    assert store.complete_and_advance(b, "SUCCESS", {"from": "B"}, later, nxt) is False
    assert row["status"] == "SUCCESS"
    assert db.config["daily_health"]["next_run_at"] == nxt
    assert db.config["daily_health"]["next_run_at"] != NOW


def test_crash_window1():
    db = SchedulerStateDB()
    db.seed_job("daily_health", "0 9 * * *", NOW)
    store = DbStore(sb=FakeSchedulerSB(db))
    store.refresh(NOW)
    job = store.jobs["daily_health"]
    a = store.claim(job, "A", NOW, LEASE)
    assert a is not None
    assert next(iter(db.logs.values()))["status"] == "RUNNING"
    later = NOW + timedelta(minutes=16)
    rec = store.claim(job, "B", later, LEASE)
    assert rec is not None
    assert rec.attempt_no == 2
    assert rec.scheduled_for == NOW
    nxt = next_fire_after("0 9 * * *", NOW)
    assert store.complete_and_advance(rec, "SUCCESS", {"ok": True}, later, nxt) is False
    assert db.observe_split() == 0


def test_crash_window2():
    db = SchedulerStateDB()
    db.seed_job("daily_health", "0 9 * * *", NOW)
    store = DbStore(sb=FakeSchedulerSB(db))
    store.refresh(NOW)
    job = store.jobs["daily_health"]
    claim = store.claim(job, "A", NOW, LEASE)
    nxt = next_fire_after("0 9 * * *", NOW)
    assert store.complete_and_advance(claim, "SUCCESS", {"ok": True}, NOW, nxt) is False
    assert db.observe_split() == 0
    assert db.split_states == 0
    src = (ROOT / "services/scheduler/db_store.py").read_text(encoding="utf-8")
    assert "table(\"cron_job_log\").update" not in src
    assert "table(\"cron_schedule_config\").update" in src
    tree = ast.parse(src)
    rpc_names = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "rpc":
            if n.args and isinstance(n.args[0], ast.Constant):
                rpc_names.append(n.args[0].value)
    assert rpc_names == [
        "tai_scheduler_claim_occurrence",
        "tai_scheduler_complete_occurrence",
    ]


def test_lost_response():
    db = SchedulerStateDB()
    db.seed_job("daily_health", "0 9 * * *", NOW)
    store = DbStore(sb=FakeSchedulerSB(db))
    executed = []

    def _fake(job):
        executed.append(job.next_run_at)
        return {"ok": True}

    import services.scheduler.dispatcher as disp
    orig = disp.execute_job
    disp.execute_job = _fake
    db.drop_complete_response = True
    try:
        out = tick(store, clock=_clk(NOW), worker_id="w1", tick_cap=5)
        assert out == []
        assert db.complete_commits == 1
        assert next(iter(db.logs.values()))["status"] == "SUCCESS"
        db.drop_complete_response = False
        out2 = tick(store, clock=_clk(NOW), worker_id="w1", tick_cap=5)
        assert out2 == []
        assert executed == [NOW]
        nxt = next_fire_after("0 9 * * *", NOW)
        assert store.jobs["daily_health"].next_run_at == nxt
        later = datetime(2026, 9, 2, 9, 0, tzinfo=KST)
        out3 = tick(store, clock=_clk(later), worker_id="w1", tick_cap=5)
        assert len(out3) == 1
        assert out3[0]["scheduled_for"].startswith("2026-09-02T09:00")
    finally:
        disp.execute_job = orig
        db.drop_complete_response = False


def test_multi_dispatcher():
    db = SchedulerStateDB()
    db.seed_job("daily_health", "0 9 * * *", NOW)
    barrier = threading.Barrier(3)
    results = []
    executed = []

    def _fake(job):
        executed.append(threading.current_thread().name)
        return {"ok": True}

    import services.scheduler.dispatcher as disp
    orig = disp.execute_job
    disp.execute_job = _fake
    try:
        def worker(wid: str):
            store = DbStore(sb=FakeSchedulerSB(db))
            barrier.wait()
            results.append(tick(store, clock=_clk(NOW), worker_id=wid, tick_cap=5))

        threads = [threading.Thread(target=worker, args=(f"w{i}",), name=f"w{i}") for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        succeeded = [r for batch in results for r in batch]
        assert len(succeeded) == 1
        assert len(executed) == 1
        nxt = next_fire_after("0 9 * * *", NOW)
        assert db.config["daily_health"]["next_run_at"] == nxt
        assert db.observe_split() == 0
    finally:
        disp.execute_job = orig


def test_terminal_wedge():
    db = SchedulerStateDB()
    db.seed_job("daily_health", "0 9 * * *", NOW)
    key = ("daily_health", NOW.isoformat())
    from services.time import serialize_business_datetime
    key = ("daily_health", serialize_business_datetime(NOW))
    db.logs[key] = {
        "id": "wedge",
        "job_code": "daily_health",
        "scheduled_for": NOW,
        "status": "SUCCESS",
        "attempt_no": 1,
        "lease_until": NOW,
        "triggered_by": "SCHEDULE",
    }
    assert db.observe_split() == 1
    store = DbStore(sb=FakeSchedulerSB(db))
    store.refresh(NOW)
    nxt = next_fire_after("0 9 * * *", NOW)
    assert store.jobs["daily_health"].next_run_at == nxt
    assert db.config["daily_health"]["next_run_at"] == nxt
    assert db.observe_split() == 0


def test_option_c_invariants_unchanged():
    u = json.loads((ROOT / "docs/time/TAI_SCHEDULER_UNIVERSE_MANIFEST.json").read_text(encoding="utf-8"))
    p = json.loads((ROOT / "docs/time/TAI_PGCRON_RETIREMENT_MAP.json").read_text(encoding="utf-8"))
    d = json.loads((ROOT / "docs/time/TAI_CRON_DOW_NORMALIZATION.json").read_text(encoding="utf-8"))
    assert u["universe_count"] == 46
    assert p["mapped"] == 12
    assert d["numeric_after"] == 0
    retire = (ROOT / "docs/sql/20260831_tai_pgcron_retire.sql").read_text(encoding="utf-8")
    assert retire.count("SELECT cron.alter_job(") == 12
    assert "unschedule" in retire.lower()
    register_direct_handlers()
    missing = [
        j["job_code"] for j in u["jobs"]
        if str(j.get("handler") or "").startswith("direct://") and j["handler"] not in DIRECT_HANDLERS
    ]
    assert missing == []
    baseline = json.loads((ROOT / "time_debt_baseline.json").read_text(encoding="utf-8"))
    allow = json.loads((ROOT / "time_exception_allowlist.json").read_text(encoding="utf-8"))
    assert baseline == {}
    assert allow == {}
    active = json.loads((ROOT / "docs/time/TAI_TIME_ACTIVE_COLUMN_MANIFEST.json").read_text(encoding="utf-8"))
    cols = active if isinstance(active, list) else (active.get("columns") or active.get("rows") or [])
    assert len(cols) == 260
    up = (ROOT / "docs/sql/20260831_tai_time_kst_cutover_up.sql").read_text(encoding="utf-8")
    down = (ROOT / "docs/sql/20260831_tai_time_kst_cutover_down.sql").read_text(encoding="utf-8")
    import re
    alter_re = re.compile(
        r"ALTER TABLE public\.([A-Za-z_][A-Za-z0-9_]*) ALTER COLUMN ([A-Za-z_][A-Za-z0-9_]*) TYPE "
    )
    assert len(alter_re.findall(up)) == 237
    assert len(alter_re.findall(down)) == 237
    views = json.loads((ROOT / "docs/time/TAI_TIME_VIEW_MANIFEST.json").read_text(encoding="utf-8"))
    vlist = views.get("views") or views
    assert len(vlist) == 3
    iso = json.loads((ROOT / "docs/time/TAI_TIME_ISOLATED_ASSETS.json").read_text(encoding="utf-8"))
    icols = iso if isinstance(iso, list) else (iso.get("columns") or iso.get("rows") or [])
    iso_pairs = {(r["object_name"], r["column_name"]) for r in icols}
    for tbl, col in alter_re.findall(up) + alter_re.findall(down):
        assert (tbl, col) not in iso_pairs
