"""WP-1C-B2-A: Scheduler occurrence heartbeat — migration static + unit/RPC tests."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from services.scheduler.db_store import DbStore
from services.scheduler.store import Claim, InMemoryStore
from tests.time.scheduler_atomic_fake import FakeSchedulerSB, SchedulerStateDB

ROOT = Path(__file__).resolve().parents[2]
SQL_UP = ROOT / "docs/sql/20260901_tai_scheduler_atomic_state_machine_up.sql"
MIGRATION = ROOT / "supabase/migrations/20261006190032_scheduler_occurrence_heartbeat_guard.sql"
KST = ZoneInfo("Asia/Seoul")
LEASE = timedelta(minutes=15)
NOW = datetime(2026, 10, 7, 9, 0, tzinfo=KST)


# ─── helpers ─────────────────────────────────────────────────────────────────


def _seed_running(db: SchedulerStateDB, job_code: str = "daily_health") -> Claim:
    db.seed_job(job_code, "0 9 * * *", NOW)
    store = DbStore(sb=FakeSchedulerSB(db))
    store.refresh(NOW)
    job = store.jobs[job_code]
    claim = store.claim(job, "w1", NOW, LEASE)
    assert claim is not None
    return claim


# ─── SCHED-M01~M16: migration static ─────────────────────────────────────────


def test_sched_m01_migration_file_exists():
    assert MIGRATION.exists(), f"migration not found: {MIGRATION}"


def test_sched_m02_heartbeat_function_name():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "tai_scheduler_heartbeat_occurrence" in sql


def test_sched_m03_heartbeat_security_invoker():
    sql = MIGRATION.read_text(encoding="utf-8")
    hb_block = sql[sql.index("tai_scheduler_heartbeat_occurrence"):]
    assert "SECURITY INVOKER" in hb_block
    assert "SECURITY DEFINER" not in hb_block.split("tai_scheduler_claim_occurrence")[0]


def test_sched_m04_heartbeat_null_lease_guard():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "p_lease IS NULL" in sql
    assert "p_lease <= interval '0'" in sql


def test_sched_m05_heartbeat_lease_not_null_guard():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "lease_until   IS NOT NULL" in sql or "lease_until IS NOT NULL" in sql


def test_sched_m06_heartbeat_lease_gt_now_guard():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "lease_until   > p_now" in sql or "lease_until > p_now" in sql


def test_sched_m07_heartbeat_identity_fence():
    sql = MIGRATION.read_text(encoding="utf-8")
    hb_fn = sql[sql.index("CREATE OR REPLACE FUNCTION public.tai_scheduler_heartbeat_occurrence"):]
    hb_fn = hb_fn[:hb_fn.index("$fn$;") + 5]
    assert "id            = p_log_id" in hb_fn or "id = p_log_id" in hb_fn
    assert "job_code      = p_job_code" in hb_fn or "job_code = p_job_code" in hb_fn
    assert "scheduled_for = p_scheduled_for" in hb_fn
    assert "attempt_no    = p_attempt_no" in hb_fn or "attempt_no = p_attempt_no" in hb_fn


def test_sched_m08_heartbeat_status_running_guard():
    sql = MIGRATION.read_text(encoding="utf-8")
    hb_fn = sql[sql.index("CREATE OR REPLACE FUNCTION public.tai_scheduler_heartbeat_occurrence"):]
    hb_fn = hb_fn[:hb_fn.index("$fn$;") + 5]
    assert "status        = 'RUNNING'" in hb_fn or "status = 'RUNNING'" in hb_fn


def test_sched_m09_heartbeat_revoke_anon_authenticated():
    sql = MIGRATION.read_text(encoding="utf-8")
    hb_revoke = sql[sql.index("REVOKE ALL ON FUNCTION public.tai_scheduler_heartbeat_occurrence"):]
    hb_revoke = hb_revoke[:hb_revoke.index(";") + 1]
    assert "anon" in hb_revoke
    assert "authenticated" in hb_revoke


def test_sched_m10_heartbeat_grant_service_role():
    sql = MIGRATION.read_text(encoding="utf-8")
    hb_grant = sql[sql.index("GRANT EXECUTE ON FUNCTION public.tai_scheduler_heartbeat_occurrence"):]
    hb_grant = hb_grant[:hb_grant.index(";") + 1]
    assert "service_role" in hb_grant


def test_sched_m11_claim_security_invoker():
    sql = MIGRATION.read_text(encoding="utf-8")
    claim_fn = sql[sql.index("CREATE OR REPLACE FUNCTION public.tai_scheduler_claim_occurrence"):]
    claim_fn = claim_fn[:claim_fn.index("$fn$;") + 5]
    assert "SECURITY INVOKER" in claim_fn
    assert "SECURITY DEFINER" not in claim_fn


def test_sched_m12_complete_security_invoker():
    sql = MIGRATION.read_text(encoding="utf-8")
    complete_fn = sql[sql.index("CREATE OR REPLACE FUNCTION public.tai_scheduler_complete_occurrence"):]
    complete_fn = complete_fn[:complete_fn.index("$fn$;") + 5]
    assert "SECURITY INVOKER" in complete_fn
    assert "SECURITY DEFINER" not in complete_fn


def test_sched_m13_claim_revoke_anon():
    sql = MIGRATION.read_text(encoding="utf-8")
    claim_revoke = sql[sql.index("REVOKE ALL ON FUNCTION public.tai_scheduler_claim_occurrence"):]
    claim_revoke = claim_revoke[:claim_revoke.index(";") + 1]
    assert "anon" in claim_revoke
    assert "authenticated" in claim_revoke


def test_sched_m14_complete_revoke_anon():
    sql = MIGRATION.read_text(encoding="utf-8")
    complete_revoke = sql[sql.index("REVOKE ALL ON FUNCTION public.tai_scheduler_complete_occurrence"):]
    complete_revoke = complete_revoke[:complete_revoke.index(";") + 1]
    assert "anon" in complete_revoke
    assert "authenticated" in complete_revoke


def test_sched_m15_heartbeat_search_path():
    sql = MIGRATION.read_text(encoding="utf-8")
    hb_fn = sql[sql.index("CREATE OR REPLACE FUNCTION public.tai_scheduler_heartbeat_occurrence"):]
    hb_fn = hb_fn[:hb_fn.index("$fn$;") + 5]
    assert "search_path" in hb_fn
    assert "pg_temp" in hb_fn


def test_sched_m16_heartbeat_returns_boolean():
    sql = MIGRATION.read_text(encoding="utf-8")
    hb_fn = sql[sql.index("CREATE OR REPLACE FUNCTION public.tai_scheduler_heartbeat_occurrence"):]
    hb_fn = hb_fn[:hb_fn.index("AS $fn$")]
    assert "RETURNS boolean" in hb_fn


# ─── HB01~HB14: heartbeat unit / RPC ─────────────────────────────────────────


def test_hb01_inmemory_heartbeat_returns_true_on_valid_claim():
    store = InMemoryStore()
    from uuid import uuid4
    log_id = str(uuid4())
    job_code = "j1"
    scheduled_for = NOW
    store.logs[(job_code, scheduled_for)] = {
        "id": log_id,
        "job_code": job_code,
        "scheduled_for": scheduled_for,
        "status": "RUNNING",
        "attempt_no": 1,
        "lease_until": NOW + LEASE,
    }
    claim = Claim(
        job_code=job_code,
        scheduled_for=scheduled_for,
        worker_id="w1",
        attempt_no=1,
        lease_until=NOW + LEASE,
        log_id=log_id,
        trace_id="",
    )
    result = store.heartbeat_occurrence(claim, now=NOW + timedelta(minutes=5), lease=LEASE)
    assert result is True


def test_hb02_inmemory_heartbeat_false_if_not_running():
    store = InMemoryStore()
    from uuid import uuid4
    log_id = str(uuid4())
    job_code = "j1"
    scheduled_for = NOW
    store.logs[(job_code, scheduled_for)] = {
        "id": log_id,
        "job_code": job_code,
        "scheduled_for": scheduled_for,
        "status": "SUCCESS",
        "attempt_no": 1,
        "lease_until": NOW + LEASE,
    }
    claim = Claim(
        job_code=job_code,
        scheduled_for=scheduled_for,
        worker_id="w1",
        attempt_no=1,
        lease_until=NOW + LEASE,
        log_id=log_id,
        trace_id="",
    )
    assert store.heartbeat_occurrence(claim, now=NOW, lease=LEASE) is False


def test_hb03_inmemory_heartbeat_false_if_lease_expired():
    store = InMemoryStore()
    from uuid import uuid4
    log_id = str(uuid4())
    job_code = "j1"
    scheduled_for = NOW
    store.logs[(job_code, scheduled_for)] = {
        "id": log_id,
        "job_code": job_code,
        "scheduled_for": scheduled_for,
        "status": "RUNNING",
        "attempt_no": 1,
        "lease_until": NOW - timedelta(seconds=1),
    }
    claim = Claim(
        job_code=job_code,
        scheduled_for=scheduled_for,
        worker_id="w1",
        attempt_no=1,
        lease_until=NOW + LEASE,
        log_id=log_id,
        trace_id="",
    )
    assert store.heartbeat_occurrence(claim, now=NOW, lease=LEASE) is False


def test_hb04_inmemory_heartbeat_false_if_wrong_log_id():
    store = InMemoryStore()
    from uuid import uuid4
    log_id = str(uuid4())
    job_code = "j1"
    scheduled_for = NOW
    store.logs[(job_code, scheduled_for)] = {
        "id": log_id,
        "job_code": job_code,
        "scheduled_for": scheduled_for,
        "status": "RUNNING",
        "attempt_no": 1,
        "lease_until": NOW + LEASE,
    }
    wrong_claim = Claim(
        job_code=job_code,
        scheduled_for=scheduled_for,
        worker_id="w1",
        attempt_no=1,
        lease_until=NOW + LEASE,
        log_id=str(uuid4()),
        trace_id="",
    )
    assert store.heartbeat_occurrence(wrong_claim, now=NOW, lease=LEASE) is False


def test_hb05_inmemory_heartbeat_false_if_wrong_attempt_no():
    store = InMemoryStore()
    from uuid import uuid4
    log_id = str(uuid4())
    job_code = "j1"
    scheduled_for = NOW
    store.logs[(job_code, scheduled_for)] = {
        "id": log_id,
        "job_code": job_code,
        "scheduled_for": scheduled_for,
        "status": "RUNNING",
        "attempt_no": 2,
        "lease_until": NOW + LEASE,
    }
    stale_claim = Claim(
        job_code=job_code,
        scheduled_for=scheduled_for,
        worker_id="w1",
        attempt_no=1,
        lease_until=NOW + LEASE,
        log_id=log_id,
        trace_id="",
    )
    assert store.heartbeat_occurrence(stale_claim, now=NOW, lease=LEASE) is False


def test_hb06_inmemory_heartbeat_extends_lease():
    store = InMemoryStore()
    from uuid import uuid4
    log_id = str(uuid4())
    job_code = "j1"
    scheduled_for = NOW
    store.logs[(job_code, scheduled_for)] = {
        "id": log_id,
        "job_code": job_code,
        "scheduled_for": scheduled_for,
        "status": "RUNNING",
        "attempt_no": 1,
        "lease_until": NOW + timedelta(minutes=5),
    }
    claim = Claim(
        job_code=job_code,
        scheduled_for=scheduled_for,
        worker_id="w1",
        attempt_no=1,
        lease_until=NOW + LEASE,
        log_id=log_id,
        trace_id="",
    )
    now2 = NOW + timedelta(minutes=3)
    assert store.heartbeat_occurrence(claim, now=now2, lease=LEASE) is True
    assert store.logs[(job_code, scheduled_for)]["lease_until"] == now2 + LEASE


def test_hb07_inmemory_heartbeat_false_if_lease_until_none():
    store = InMemoryStore()
    from uuid import uuid4
    log_id = str(uuid4())
    job_code = "j1"
    scheduled_for = NOW
    store.logs[(job_code, scheduled_for)] = {
        "id": log_id,
        "job_code": job_code,
        "scheduled_for": scheduled_for,
        "status": "RUNNING",
        "attempt_no": 1,
        "lease_until": None,
    }
    claim = Claim(
        job_code=job_code,
        scheduled_for=scheduled_for,
        worker_id="w1",
        attempt_no=1,
        lease_until=NOW + LEASE,
        log_id=log_id,
        trace_id="",
    )
    assert store.heartbeat_occurrence(claim, now=NOW, lease=LEASE) is False


def test_hb08_dbstore_heartbeat_sends_correct_rpc_params():
    db = SchedulerStateDB()
    claim = _seed_running(db)
    captured = {}

    class _FakeRpc:
        def execute(self):
            return type("R", (), {"data": True})()

    class CaptureSB:
        def rpc(self, name, params=None):
            captured["name"] = name
            captured["params"] = params
            return _FakeRpc()

    store = DbStore(sb=CaptureSB())
    now2 = NOW + timedelta(minutes=5)
    store.heartbeat_occurrence(claim, now=now2, lease=LEASE)
    assert captured["name"] == "tai_scheduler_heartbeat_occurrence"
    p = captured["params"]
    assert p["p_job_code"] == claim.job_code
    assert p["p_log_id"] == claim.log_id
    assert p["p_attempt_no"] == claim.attempt_no
    assert "seconds" in p["p_lease"]


def test_hb09_dbstore_heartbeat_returns_true_when_rpc_true():
    db = SchedulerStateDB()
    claim = _seed_running(db)
    store = DbStore(sb=FakeSchedulerSB(db))
    now2 = NOW + timedelta(minutes=5)
    result = store.heartbeat_occurrence(claim, now=now2, lease=LEASE)
    assert result is True


def test_hb10_dbstore_heartbeat_returns_false_when_fenced():
    db = SchedulerStateDB()
    claim = _seed_running(db)
    # Expire the lease in the fake
    key = db._key(claim.job_code, claim.scheduled_for)
    db.logs[key]["lease_until"] = NOW - timedelta(seconds=1)
    store = DbStore(sb=FakeSchedulerSB(db))
    now2 = NOW + timedelta(minutes=5)
    result = store.heartbeat_occurrence(claim, now=now2, lease=LEASE)
    assert result is False


def test_hb11_dbstore_heartbeat_propagates_rpc_exception():
    import pytest

    class FailSB:
        def rpc(self, name, params=None):
            raise ConnectionError("db down")

    db = SchedulerStateDB()
    claim = _seed_running(db)
    store = DbStore(sb=FailSB())
    with pytest.raises(ConnectionError):
        store.heartbeat_occurrence(claim, now=NOW, lease=LEASE)


def test_hb12_fake_heartbeat_false_if_attempt_no_mismatch():
    db = SchedulerStateDB()
    claim = _seed_running(db)
    key = db._key(claim.job_code, claim.scheduled_for)
    db.logs[key]["attempt_no"] = 99
    store = DbStore(sb=FakeSchedulerSB(db))
    result = store.heartbeat_occurrence(claim, now=NOW + timedelta(minutes=5), lease=LEASE)
    assert result is False


def test_hb13_fake_heartbeat_false_if_log_id_mismatch():
    from uuid import uuid4
    import pytest
    db = SchedulerStateDB()
    claim = _seed_running(db)
    bad_claim = Claim(
        job_code=claim.job_code,
        scheduled_for=claim.scheduled_for,
        worker_id=claim.worker_id,
        attempt_no=claim.attempt_no,
        lease_until=claim.lease_until,
        log_id=str(uuid4()),
        trace_id=claim.trace_id,
    )
    store = DbStore(sb=FakeSchedulerSB(db))
    result = store.heartbeat_occurrence(bad_claim, now=NOW + timedelta(minutes=5), lease=LEASE)
    assert result is False


def test_hb14_heartbeat_false_after_complete_commits():
    """After complete_and_advance, heartbeat must return False (status != RUNNING)."""
    from services.scheduler.cron_grammar import next_fire_after
    db = SchedulerStateDB()
    claim = _seed_running(db)
    store = DbStore(sb=FakeSchedulerSB(db))
    nxt = next_fire_after("0 9 * * *", NOW)
    fenced = store.complete_and_advance(claim, "SUCCESS", {}, NOW + timedelta(minutes=10), nxt)
    assert fenced is False
    result = store.heartbeat_occurrence(claim, now=NOW + timedelta(minutes=12), lease=LEASE)
    assert result is False
