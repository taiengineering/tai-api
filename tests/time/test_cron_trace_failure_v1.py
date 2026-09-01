"""WP-OBS-CRON-01 REV-1 — trace identity + CRON_JOB_FAILED producer. No live DB."""
from __future__ import annotations

import ast
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import services.scheduler.db_store as db_store_mod
import services.scheduler.dispatcher as disp
import watch_engine.emitter as emitter_mod
import watch_engine.trace as trace_mod
from services.scheduler.cron_grammar import next_fire_after
from services.scheduler.db_store import DbStore
from services.scheduler.dispatcher import tick
from services.scheduler.gate import scheduler_enabled
from services.scheduler.store import InMemoryStore, JobRow
from services.time import FixedClock
from tests.time.scheduler_atomic_fake import FakeSchedulerSB, SchedulerStateDB
from watch_engine.trace import (
    TraceContext,
    create_trace,
    generate_trace_id,
    get_current_trace,
    trace_scope,
)

ROOT = Path(__file__).resolve().parents[2]
KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 9, 1, 9, 0, tzinfo=KST)
LEASE = timedelta(minutes=15)
SQL_RUNTIME = ROOT / "docs/sql/20260831_tai_scheduler_runtime_state_up.sql"
SQL_UP = ROOT / "docs/sql/20260901_tai_scheduler_atomic_state_machine_up.sql"
SQL_DOWN = ROOT / "docs/sql/20260901_tai_scheduler_atomic_state_machine_down.sql"
PAYLOAD_KEYS = frozenset({"job_code", "scheduled_for", "attempt_no", "log_id", "worker_id"})
PAYLOAD_DENY = ("error", "endpoint", "stack", "secret", "password", "token")


@pytest.fixture(autouse=True)
def _reset_trace():
    from watch_engine.trace import clear_trace
    clear_trace()
    yield
    clear_trace()


def _clk(instant: datetime = NOW) -> FixedClock:
    return FixedClock(instant)


def _job(store: InMemoryStore, scheduled_for: datetime = NOW) -> JobRow:
    job = JobRow("daily_health", "0 9 * * *", True, "direct://daily_health_check", scheduled_for)
    store.put_job(job)
    return job


class _FakeTable:
    def __init__(self, sink):
        self._sink = sink

    def insert(self, row):
        self._sink["row"] = row
        self._sink["insert_count"] = self._sink.get("insert_count", 0) + 1
        return self

    def execute(self):
        return {"data": []}


class _FakeSupabase:
    def __init__(self, sink):
        self._sink = sink

    def table(self, name):
        self._sink["table"] = name
        return _FakeTable(self._sink)


@pytest.fixture
def emit_sink(monkeypatch):
    s = {"insert_count": 0, "calls": []}
    monkeypatch.setattr(emitter_mod, "_get_supabase", lambda: _FakeSupabase(s))
    orig = disp.emit_event

    def _wrap(**kw):
        s["calls"].append(kw)
        return orig(**kw)

    monkeypatch.setattr(disp, "emit_event", _wrap)
    return s


@pytest.fixture
def emit_spy(monkeypatch):
    calls = []

    def _spy(**kw):
        calls.append(kw)
        return True

    monkeypatch.setattr(disp, "emit_event", _spy)
    return calls


# ─── T1–T7 trace ───

def test_t1_generate_trace_id_regression(monkeypatch):
    monkeypatch.setattr(trace_mod, "_generate_short_id", lambda: "abc123xyz789")
    assert generate_trace_id("login") == "login_abc123xyz789"
    ctx = create_trace("login", tenant_id="acme")
    assert ctx.trace_id == "login_abc123xyz789"
    assert get_current_trace() is ctx


def test_t2_first_occurrence_assigns_candidate():
    store = InMemoryStore()
    job = _job(store)
    a = store.claim(job, "w1", NOW, LEASE)
    assert a is not None
    assert a.trace_id.startswith("cron_job_")
    assert a.attempt_no == 1
    row = store.logs[(job.job_code, job.next_run_at)]
    assert row["trace_id"] == a.trace_id


def test_t3_reclaim_same_occurrence_same_trace():
    store = InMemoryStore()
    job = _job(store)
    first = store.claim(job, "w1", NOW, LEASE)
    later = NOW + timedelta(minutes=16)
    rec = store.claim(job, "w2", later, LEASE)
    assert first is not None and rec is not None
    assert rec.attempt_no == 2
    assert rec.trace_id == first.trace_id
    assert rec.log_id == first.log_id


def test_t4_different_occurrence_different_trace():
    store = InMemoryStore()
    job = _job(store)
    first = store.claim(job, "w1", NOW, LEASE)
    nxt = next_fire_after(job.cron_expression, NOW)
    assert store.complete_and_advance(first, "SUCCESS", {"ok": True}, NOW, nxt) is False
    job.next_run_at = nxt
    second = store.claim(job, "w1", nxt, LEASE)
    assert first is not None and second is not None
    assert first.scheduled_for != second.scheduled_for
    assert first.trace_id != second.trace_id


def test_t5_db_persisted_authority_discards_candidate(monkeypatch):
    ids = iter(["cand_first", "cand_reclaim"])
    monkeypatch.setattr(db_store_mod, "generate_trace_id", lambda flow: next(ids))
    db = SchedulerStateDB()
    db.seed_job("daily_health", "0 9 * * *", NOW)
    store = DbStore(sb=FakeSchedulerSB(db))
    store.refresh(NOW)
    job = store.jobs["daily_health"]
    first = store.claim(job, "A", NOW, LEASE)
    assert first is not None
    assert first.trace_id == "cand_first"
    later = NOW + timedelta(minutes=16)
    rec = store.claim(job, "B", later, LEASE)
    assert rec is not None
    assert rec.attempt_no == 2
    assert rec.trace_id == "cand_first"
    assert next(iter(db.logs.values()))["trace_id"] == "cand_first"


def test_t6_trace_scope_restores_prior_normal():
    outer = create_trace("outer", tenant_id="acme")
    inner = TraceContext(trace_id="cron_job_inner", flow_key="cron_job", tenant_id="platform")
    with trace_scope(inner):
        assert get_current_trace() is inner
    assert get_current_trace() is outer
    assert get_current_trace().trace_id == outer.trace_id


def test_t7_trace_scope_restores_prior_on_exception():
    outer = create_trace("outer", tenant_id="acme")
    inner = TraceContext(trace_id="cron_job_inner", flow_key="cron_job", tenant_id="platform")
    with pytest.raises(RuntimeError, match="boom"):
        with trace_scope(inner):
            assert get_current_trace() is inner
            raise RuntimeError("boom")
    assert get_current_trace() is outer


# ─── T8–T13 producer ───

def test_t8_handler_failed_emit_once(emit_spy, monkeypatch):
    store = InMemoryStore()
    _job(store)
    monkeypatch.setattr(disp, "execute_job", lambda j: (_ for _ in ()).throw(RuntimeError("boom")))
    out = tick(store, clock=_clk(), worker_id="w1", tick_cap=1)
    assert len(out) == 1
    assert out[0]["status"] == "FAILED"
    assert len(emit_spy) == 1
    assert emit_spy[0]["event_name"] == "CRON_JOB_FAILED"


def test_t9_complete_fail_emit_zero(emit_spy, monkeypatch):
    store = InMemoryStore()
    _job(store)
    monkeypatch.setattr(disp, "execute_job", lambda j: (_ for _ in ()).throw(RuntimeError("boom")))

    def _boom(*a, **k):
        raise TimeoutError("lost complete RPC")

    monkeypatch.setattr(store, "complete_and_advance", _boom)
    out = tick(store, clock=_clk(), worker_id="w1", tick_cap=1)
    assert out == []
    assert emit_spy == []
    row = next(iter(store.logs.values()))
    assert row["status"] == "RUNNING"


def test_t10_fenced_emit_zero(emit_spy, monkeypatch):
    store = InMemoryStore()
    _job(store)
    monkeypatch.setattr(disp, "execute_job", lambda j: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(store, "complete_and_advance", lambda *a, **k: True)
    out = tick(store, clock=_clk(), worker_id="w1", tick_cap=1)
    assert out == []
    assert emit_spy == []


def test_t11_success_emit_zero(emit_spy, monkeypatch):
    store = InMemoryStore()
    _job(store)
    monkeypatch.setattr(disp, "execute_job", lambda j: {"ok": True})
    out = tick(store, clock=_clk(), worker_id="w1", tick_cap=1)
    assert len(out) == 1
    assert out[0]["status"] == "SUCCESS"
    assert emit_spy == []


def test_t12_emitter_false_no_scheduler_effect(monkeypatch):
    store = InMemoryStore()
    job = _job(store)
    monkeypatch.setattr(disp, "execute_job", lambda j: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(disp, "emit_event", lambda **kw: False)
    out = tick(store, clock=_clk(), worker_id="w1", tick_cap=1)
    assert len(out) == 1
    assert out[0]["status"] == "FAILED"
    nxt = next_fire_after(job.cron_expression, NOW)
    assert store.jobs["daily_health"].next_run_at == nxt
    row = next(iter(store.logs.values()))
    assert row["status"] == "FAILED"


def test_t13_payload_safe(emit_spy, monkeypatch):
    store = InMemoryStore()
    _job(store)
    monkeypatch.setattr(disp, "execute_job", lambda j: (_ for _ in ()).throw(RuntimeError("secret-token boom")))
    tick(store, clock=_clk(), worker_id="w1", tick_cap=1)
    payload = emit_spy[0]["payload_summary"]
    assert set(payload) == PAYLOAD_KEYS
    blob = str(payload).lower()
    for bad in PAYLOAD_DENY:
        assert bad not in payload
        if bad == "error":
            assert "error" not in payload
        else:
            assert bad not in blob
    assert "secret-token boom" not in str(payload)


# ─── T14 canonical insert ───

def test_t14_canonical_row(emit_sink, monkeypatch):
    store = InMemoryStore()
    job = _job(store)
    monkeypatch.setattr(disp, "execute_job", lambda j: (_ for _ in ()).throw(RuntimeError("boom")))
    out = tick(store, clock=_clk(), worker_id="w1", tick_cap=1)
    assert out[0]["status"] == "FAILED"
    assert emit_sink["insert_count"] == 1
    row = emit_sink["row"]
    claim_trace = next(iter(store.logs.values()))["trace_id"]
    assert row["event_name"] == "CRON_JOB_FAILED"
    assert row["event_type"] == "cron_failure"
    assert row["event_version"] == 1
    assert row["tenant_id"] == "platform"
    assert row["service_key"] == "tai-api"
    assert row["flow_key"] == "cron_job"
    assert row["actor_kind"] == "CRON"
    assert row["actor_ref"] == f"cron:{job.job_code}"
    assert row["actor_type"] == "scheduler"
    assert row["result"] == "failure"
    assert row["outcome"] == "FAILURE"
    assert row["connector_type"] == "scheduler"
    assert row["step_key"] == "cron_job_failed"
    assert row["step_order"] == 1
    assert row["trace_id"] == claim_trace
    assert row["trace_id"].startswith("cron_job_")
    assert set(row["payload_summary"]) == PAYLOAD_KEYS
    assert "occurred_at" in row


def test_t15_tick_does_not_leak_trace(emit_spy, monkeypatch):
    outer = create_trace("outer", tenant_id="acme")
    store = InMemoryStore()
    _job(store)
    monkeypatch.setattr(disp, "execute_job", lambda j: (_ for _ in ()).throw(RuntimeError("boom")))
    tick(store, clock=_clk(), worker_id="w1", tick_cap=1)
    assert get_current_trace() is outer
    assert len(emit_spy) == 1


# ─── T16–T18 SQL static ───

def test_t16_sql_trace_id_added_backfill_zero():
    runtime = SQL_RUNTIME.read_text(encoding="utf-8")
    up = SQL_UP.read_text(encoding="utf-8")
    assert "EXECUTE = 0" in runtime
    assert "EXECUTE = 0" in up
    assert "ALTER TABLE public.cron_job_log ADD COLUMN IF NOT EXISTS trace_id text;" in runtime
    assert "trace_id text NOT NULL" not in runtime
    assert "UPDATE public.cron_job_log" not in runtime
    assert re.search(r"UPDATE\s+public\.cron_job_log\s+SET\s+trace_id", runtime, re.I) is None
    assert re.search(r"UPDATE\s+public\.cron_job_log\s+SET\s+trace_id", up, re.I) is None


def test_t16b_sql_scheduled_trace_check_constraint():
    runtime = SQL_RUNTIME.read_text(encoding="utf-8")
    assert "cron_job_log_scheduled_trace_chk" in runtime
    assert "scheduled_for IS NULL" in runtime
    assert "trace_id IS NOT NULL" in runtime
    assert "btrim(trace_id) <> ''" in runtime
    assert "NOT IN ('unknown', 'no_trace')" in runtime
    assert "unknown" in runtime
    assert "no_trace" in runtime
    assert "pg_constraint" in runtime
    assert "IF NOT EXISTS" in runtime
    assert "DO $$" in runtime
    assert "SET trace_id" not in runtime
    assert re.search(r"UPDATE\s+.*trace_id\s*=", runtime, re.I) is None
    assert "NOT VALID" not in runtime


def test_t17_sql_claim_returns_trace_reclaim_immutable():
    up = SQL_UP.read_text(encoding="utf-8")
    claim_body = up.split("$fn$")[1]
    assert "p_trace_id text" in up
    assert "RETURNS TABLE (log_id uuid, attempt_no integer, trace_id text)" in up
    assert "p_trace_id" in claim_body
    assert "trace_id := v_trace" in claim_body
    set_block = claim_body.split("UPDATE public.cron_job_log", 1)[1].split("WHERE", 1)[0]
    assert "trace_id" not in set_block
    assert "SECURITY DEFINER" in up
    assert "SET search_path = public" in up
    assert "REVOKE ALL ON FUNCTION public.tai_scheduler_claim_occurrence(text, timestamptz, timestamptz, interval, text) FROM PUBLIC" in up
    assert "GRANT EXECUTE ON FUNCTION public.tai_scheduler_claim_occurrence(text, timestamptz, timestamptz, interval, text) TO postgres, service_role" in up
    down = SQL_DOWN.read_text(encoding="utf-8")
    assert "tai_scheduler_claim_occurrence(text, timestamptz, timestamptz, interval, text)" in down
    assert down.count("DROP FUNCTION") == 2


def test_t18_producer_point_static():
    src = (ROOT / "services/scheduler/dispatcher.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    tick_fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "tick")
    emit_names = [
        n.func.id for n in ast.walk(tick_fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id in ("emit_event", "_emit_cron_job_failed")
    ]
    assert emit_names == ["_emit_cron_job_failed"]
    helper = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_emit_cron_job_failed")
    calls = [n for n in ast.walk(helper) if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "emit_event"]
    assert len(calls) == 1
    kw = {k.arg: k.value.value for k in calls[0].keywords if isinstance(k.value, ast.Constant)}
    assert kw["event_name"] == "CRON_JOB_FAILED"
    assert kw["event_type"] == "cron_failure"
    assert kw["step_key"] == "cron_job_failed"
    assert kw["step_order"] == 1
    assert kw["result"] == "failure"
    assert kw["connector_type"] == "scheduler"
    assert kw["actor_kind"] == "CRON"
    passed = {k.arg for k in calls[0].keywords}
    for forbidden in ("occurred_at", "outcome", "event_version", "tenant_id", "service_key", "environment"):
        assert forbidden not in passed
    assert "status == \"FAILED\"" in src
    assert "trace_scope" in src


# ─── T19–T20 scheduler / gate ───

def test_t19_at_least_once_fenced_no_silent_miss(monkeypatch):
    store = InMemoryStore()
    missed = datetime(2026, 8, 31, 9, 0, tzinfo=KST)
    job = JobRow("daily_health", "0 9 * * *", True, "direct://daily_health_check", missed)
    store.put_job(job)
    monkeypatch.setattr(disp, "execute_job", lambda j: {"ok": True})
    now = datetime(2026, 9, 2, 10, 0, tzinfo=KST)
    out = tick(store, clock=_clk(now), worker_id="w1", tick_cap=1)
    assert len(out) == 1
    assert out[0]["scheduled_for"].startswith("2026-08-31T09:00")
    live = store.jobs["daily_health"]
    saved = live.next_run_at
    live.next_run_at = missed
    assert store.claim(live, "stale", now, LEASE) is None
    live.next_run_at = saved
    first = store.claim(live, "w1", now, LEASE)
    rec = store.claim(live, "w2", now, LEASE)
    assert first is not None
    assert rec is None


def test_t20_disabled_scheduler_execution_zero(monkeypatch):
    monkeypatch.delenv("TAI_SCHEDULER_ENABLED", raising=False)
    assert scheduler_enabled() is False
    called: list[int] = []
    import scheduler
    import scheduler_worker

    monkeypatch.setattr(disp, "tick", lambda *a, **k: called.append(1))
    monkeypatch.setattr(scheduler_worker, "tick", lambda *a, **k: called.append(1))
    monkeypatch.setattr(scheduler_worker, "start_dispatcher_thread", scheduler_worker.start_dispatcher_thread)
    scheduler.scheduler.running = False
    try:
        scheduler.start_scheduler()
        scheduler_worker.start_dispatcher_thread()
        assert called == []
        assert scheduler.scheduler.running is False
    finally:
        scheduler.scheduler.running = False
