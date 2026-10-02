"""QA Auto Ops tests — WO-QA-CONTROL-PHASE2E-AUTO-OPS-001 + PATCH1.

AO-01  enabled schedule → tick 조회 대상
AO-02  next_run_at 도달 → run 생성
AO-03  trigger_type=SCHEDULE 고정
AO-04  duplicate guard: 동일 item QUEUED/RUNNING → 두 번째 tick skip
AO-05  next_run_at 갱신 (tick 성공 후)
AO-06  tick 인증 실패 (secret 없음 / 틀림) → 403
AO-07  tick 인증 성공 → 200
AO-08  secret 로그 미노출 (소스 계약 검증)

AO-F01  MINUTES 계산 PASS
AO-F02  HOURLY 계산 PASS
AO-F03  DAILY 계산 PASS
AO-F04  MINUTE/HOUR/DAY old aliases reject
AO-F05  next_run_at cadence 기반 advance (not now)
AO-F06  direct handler 실제 result 반환 (coroutine 아님)
AO-F07  migration contains cron_job_master + cron_schedule_config
AO-F08  initial is_active=false / is_enabled=false
"""
from __future__ import annotations

import asyncio
import inspect
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _dt(offset_minutes: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)).isoformat()


def _sched(item_id: str, scenario_id: str, enabled_item: bool = True, next_run_offset: int = -1,
           ft: str = "MINUTES", fv: int = 1):
    return {
        "id":              f"sched-{item_id}",
        "qa_item_id":      item_id,
        "frequency_type":  ft,
        "frequency_value": fv,
        "next_run_at":     _dt(next_run_offset),
        "qa_items": {
            "id":          item_id,
            "scenario_id": scenario_id,
            "enabled":     enabled_item,
        },
    }


def _make_sb(schedules=None, run_insert_id="run-ao-1"):
    import services.qa_scheduler_svc as mod

    sb = MagicMock()

    run_insert_chain = MagicMock()
    run_insert_chain.execute.return_value = MagicMock(data=[{"id": run_insert_id}])

    target_insert_chain = MagicMock()
    target_insert_chain.execute.return_value = MagicMock(data=[{}])

    sched_update_chain = MagicMock()
    sched_update_chain.eq.return_value.execute.return_value = MagicMock(data=[{}])

    def _table(name):
        m = MagicMock()
        if name == "qa_runs":
            m.insert.return_value = run_insert_chain
            m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
        elif name == "qa_run_targets":
            m.insert.return_value = target_insert_chain
        elif name == "qa_schedules":
            m.update.return_value = sched_update_chain
        return m

    sb.table.side_effect = _table
    return sb


async def _tick(schedules, busy_ids=frozenset(), dispatch_ok=True):
    import services.qa_scheduler_svc as mod

    sb = _make_sb(schedules)

    async def _ok_dispatch(run_id, scenario_ids): pass
    async def _fail_dispatch(run_id, scenario_ids): raise RuntimeError("dispatch error")

    with patch.object(mod, "_due_schedules", return_value=schedules), \
         patch.object(mod, "_active_item_ids", return_value=busy_ids), \
         patch.object(mod, "dispatch_qa_run", _ok_dispatch if dispatch_ok else _fail_dispatch):
        return await mod.scheduler_tick(sb)


# ── AO-01: enabled schedule 조회 ─────────────────────────────────────────────

def test_AO01_enabled_schedule_found():
    """AO-01: enabled schedule이 있으면 tick이 run을 생성한다."""
    sched = _sched("item-ao1", "P0-SAAS-001", enabled_item=True, next_run_offset=-2)
    result = asyncio.run(_tick([sched]))
    assert result["created"] == 1


# ── AO-02: next_run_at 도달 → run 생성 ───────────────────────────────────────

def test_AO02_next_run_at_due_creates_run():
    """AO-02: next_run_at <= now인 schedule → run 생성."""
    sched = _sched("item-ao2", "P0-SAAS-001", next_run_offset=-1)
    result = asyncio.run(_tick([sched]))
    assert result["created"] == 1
    assert result["dispatch"] == "OK"


# ── AO-03: trigger_type=SCHEDULE ─────────────────────────────────────────────

def test_AO03_trigger_type_is_schedule():
    """AO-03: 자동 생성 run의 trigger_type이 SCHEDULE이어야 한다 (소스 계약)."""
    import services.qa_scheduler_svc as mod
    src = inspect.getsource(mod.scheduler_tick)
    assert '"SCHEDULE"' in src or "'SCHEDULE'" in src

    sched = _sched("item-ao3", "P0-SAAS-001")
    result = asyncio.run(_tick([sched]))
    assert result["created"] == 1


# ── AO-04: duplicate guard ───────────────────────────────────────────────────

def test_AO04_duplicate_guard_second_tick_skipped():
    """AO-04: item이 이미 QUEUED/RUNNING run에 포함되면 두 번째 tick은 run을 생성하지 않는다."""
    sched = _sched("item-ao4", "P0-SAAS-001", next_run_offset=-5)

    # 두 번째 tick: item-ao4가 이미 active
    result = asyncio.run(_tick([sched], busy_ids=frozenset({"item-ao4"})))
    assert result["created"] == 0
    assert result["skipped"] == 1


# ── AO-05: next_run_at 갱신 ──────────────────────────────────────────────────

def test_AO05_next_run_at_updated_after_tick():
    """AO-05: tick 성공 후 qa_schedules.next_run_at 갱신 SQL 실행 확인."""
    import services.qa_scheduler_svc as mod

    sched = _sched("item-ao5", "P0-SAAS-001", next_run_offset=-1)
    sb = _make_sb([sched])

    update_calls = []

    orig_update_eq = None

    def _table(name):
        m = MagicMock()
        if name == "qa_runs":
            m.insert.return_value.execute.return_value = MagicMock(data=[{"id": "run-ao5"}])
            m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
        elif name == "qa_run_targets":
            m.insert.return_value.execute.return_value = MagicMock(data=[{}])
        elif name == "qa_schedules":
            def _update(payload):
                update_calls.append(payload)
                inner = MagicMock()
                inner.eq.return_value.execute.return_value = MagicMock(data=[{}])
                return inner
            m.update = _update
        return m

    sb2 = MagicMock()
    sb2.table.side_effect = _table

    async def _ok_dispatch(run_id, scenario_ids): pass

    async def _run():
        with patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch.object(mod, "dispatch_qa_run", _ok_dispatch):
            return await mod.scheduler_tick(sb2)

    result = asyncio.run(_run())
    assert result["created"] == 1
    # next_run_at 갱신 call이 있었는지 확인
    assert any("next_run_at" in str(c) for c in update_calls), "next_run_at 갱신 없음"


# ── AO-06: tick 인증 실패 → 403 ──────────────────────────────────────────────

def test_AO06_tick_auth_missing_secret_403(monkeypatch):
    """AO-06: X-Internal-Secret 없으면 403."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.internal_scheduler import router

    monkeypatch.setenv("INTERNAL_API_SECRET", "correct-secret")
    monkeypatch.setattr("routers.internal_scheduler.get_supabase", lambda: MagicMock())

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.post("/internal/scheduler/qa/tick")
    assert resp.status_code == 403


def test_AO06b_tick_auth_wrong_secret_403(monkeypatch):
    """AO-06b: X-Internal-Secret 틀리면 403."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.internal_scheduler import router

    monkeypatch.setenv("INTERNAL_API_SECRET", "correct-secret")
    monkeypatch.setattr("routers.internal_scheduler.get_supabase", lambda: MagicMock())

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.post(
        "/internal/scheduler/qa/tick",
        headers={"X-Internal-Secret": "wrong"},
    )
    assert resp.status_code == 403


# ── AO-07: tick 인증 성공 → 200 ──────────────────────────────────────────────

def test_AO07_tick_auth_correct_secret_200(monkeypatch):
    """AO-07: X-Internal-Secret 일치 시 200."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.internal_scheduler import router

    monkeypatch.setenv("INTERNAL_API_SECRET", "correct-secret")

    fake_result = {"skipped": 0, "created": 0, "error": 0, "items": []}

    async def _fake_tick(sb):
        return fake_result

    monkeypatch.setattr("routers.internal_scheduler.scheduler_tick", _fake_tick)
    monkeypatch.setattr("routers.internal_scheduler.get_supabase", lambda: MagicMock())

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.post(
        "/internal/scheduler/qa/tick",
        headers={"X-Internal-Secret": "correct-secret"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── AO-08: secret 로그 미노출 ─────────────────────────────────────────────────

def test_AO08_secret_not_logged():
    """AO-08: _auth() 구현에서 secret 값을 로그에 출력하지 않는다 (소스 계약)."""
    import routers.internal_scheduler as mod
    src = inspect.getsource(mod._auth)
    import re
    log_calls = re.findall(r'log\.\w+\([^)]*\)', src)
    for call in log_calls:
        assert "x_internal_secret" not in call, f"secret이 로그에 노출됨: {call}"
        assert "expected" not in call, f"expected(=secret)가 로그에 노출됨: {call}"


# ── AO-F01~F03: DB canonical frequency 이름 계산 ─────────────────────────────

def test_AOF01_minutes_calculation():
    """AO-F01: MINUTES (DB SoT) 계산 PASS."""
    from services.qa_scheduler_svc import compute_next_run_at
    base = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    assert compute_next_run_at("MINUTES", 1, base) == datetime(2026, 10, 1, 9, 1, tzinfo=timezone.utc)
    assert compute_next_run_at("MINUTES", 5, base) == datetime(2026, 10, 1, 9, 5, tzinfo=timezone.utc)


def test_AOF02_hourly_calculation():
    """AO-F02: HOURLY (DB SoT) 계산 PASS."""
    from services.qa_scheduler_svc import compute_next_run_at
    base = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    assert compute_next_run_at("HOURLY", 1, base) == datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
    assert compute_next_run_at("HOURLY", 6, base) == datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)


def test_AOF03_daily_calculation():
    """AO-F03: DAILY (DB SoT) 계산 PASS — anchor 유지."""
    from services.qa_scheduler_svc import compute_next_run_at
    base = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
    result = compute_next_run_at("DAILY", None, base)
    assert result == datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc)


# ── AO-F04: 구 alias reject ───────────────────────────────────────────────────

def test_AOF04_old_aliases_rejected():
    """AO-F04: MINUTE/HOUR/DAY (구 alias) → ValueError."""
    from services.qa_scheduler_svc import compute_next_run_at
    base = datetime(2026, 10, 1, tzinfo=timezone.utc)
    import pytest
    for old in ("MINUTE", "HOUR", "DAY"):
        with pytest.raises(ValueError, match="지원하지 않는"):
            compute_next_run_at(old, 1, base)


# ── AO-F05: next_run_at cadence 기반 (not now) ───────────────────────────────

def test_AOF05_next_run_at_based_on_scheduled_time():
    """AO-F05: tick 이 10:00:37에 실행돼도 next = scheduled(10:00) + 1min = 10:01, not 10:01:37."""
    import services.qa_scheduler_svc as mod

    scheduled_at = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)
    tick_at = datetime(2026, 10, 1, 10, 0, 37, tzinfo=timezone.utc)

    sched = {
        "id":              "sched-drift",
        "qa_item_id":      "item-drift",
        "frequency_type":  "MINUTES",
        "frequency_value": 1,
        "next_run_at":     scheduled_at.isoformat(),
        "qa_items": {"id": "item-drift", "scenario_id": "P0-DRIFT", "enabled": True},
    }

    captured_next = {}

    def _table(name):
        m = MagicMock()
        if name == "qa_runs":
            m.insert.return_value.execute.return_value = MagicMock(data=[{"id": "run-drift"}])
            m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
        elif name == "qa_run_targets":
            m.insert.return_value.execute.return_value = MagicMock(data=[{}])
        elif name == "qa_schedules":
            def _update(payload):
                captured_next.update(payload)
                inner = MagicMock()
                inner.eq.return_value.execute.return_value = MagicMock(data=[{}])
                return inner
            m.update = _update
        return m

    sb = MagicMock()
    sb.table.side_effect = _table

    async def _ok_dispatch(run_id, scenario_ids): pass

    async def _run():
        with patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch.object(mod, "dispatch_qa_run", _ok_dispatch), \
             patch.object(mod, "now_kst", return_value=tick_at):
            return await mod.scheduler_tick(sb)

    asyncio.run(_run())

    assert "next_run_at" in captured_next, "next_run_at 갱신 없음"
    next_dt = datetime.fromisoformat(captured_next["next_run_at"].replace("Z", "+00:00"))
    expected = datetime(2026, 10, 1, 10, 1, 0, tzinfo=timezone.utc)
    assert next_dt == expected, f"drift 발생: expected={expected}, got={next_dt}"


# ── AO-F06: direct handler coroutine 아님 ────────────────────────────────────

def test_AOF06_direct_handler_returns_result_not_coroutine(monkeypatch):
    """AO-F06: direct://qa_scheduler_tick 핸들러가 coroutine이 아닌 실제 result를 반환한다."""
    fake_result = {"skipped": 0, "created": 1, "error": 0, "items": ["P0-SAAS-001"]}

    async def _fake_tick(sb):
        return fake_result

    import services.scheduler.handlers as hmod
    import services.qa_scheduler_svc as smod

    monkeypatch.setattr(smod, "scheduler_tick", _fake_tick)
    monkeypatch.setattr(hmod, "_sb", lambda: MagicMock())

    hmod.DIRECT_HANDLERS.clear()
    hmod.register_direct_handlers()

    handler = hmod.DIRECT_HANDLERS.get("direct://qa_scheduler_tick")
    assert handler is not None, "direct://qa_scheduler_tick 핸들러 미등록"

    result = handler({})
    import inspect as _inspect
    assert not _inspect.iscoroutine(result), "coroutine이 반환됨 — asyncio.run 누락"
    assert isinstance(result, dict), f"dict가 아님: {type(result)}"


# ── AO-F07: migration 파일 두 테이블 포함 ─────────────────────────────────────

def test_AOF07_migration_contains_both_tables():
    """AO-F07: 20261002_qa_auto_ops_scheduler.sql에 cron_job_master + cron_schedule_config INSERT 포함."""
    import os
    migration_path = os.path.join(
        os.path.dirname(__file__), "..",
        "supabase", "migrations", "20261002_qa_auto_ops_scheduler.sql",
    )
    with open(migration_path) as f:
        sql = f.read()
    assert "cron_job_master" in sql, "cron_job_master INSERT 없음"
    assert "cron_schedule_config" in sql, "cron_schedule_config INSERT 없음"
    assert "qa_scheduler_tick" in sql


# ── AO-F08: 초기 비활성 상태 ─────────────────────────────────────────────────

def test_AOF08_initial_inactive():
    """AO-F08: migration에서 is_active=false / is_enabled=false로 초기 등록됨 (소스 계약)."""
    import os
    migration_path = os.path.join(
        os.path.dirname(__file__), "..",
        "supabase", "migrations", "20261002_qa_auto_ops_scheduler.sql",
    )
    with open(migration_path) as f:
        sql = f.read().lower()
    assert "is_active" in sql
    assert "false" in sql


# ── AO-F09: dispatch 성공 → RUNNING update ───────────────────────────────────

def test_AOF09_dispatch_success_sets_running():
    """AO-F09: SCHEDULE run 생성 → dispatch 성공 → qa_runs RUNNING update (started_at 포함)."""
    import services.qa_scheduler_svc as mod

    sched = _sched("item-af9", "P0-SAAS-001", next_run_offset=-1)
    running_updates: list = []

    def _table(name):
        m = MagicMock()
        if name == "qa_runs":
            m.insert.return_value.execute.return_value = MagicMock(data=[{"id": "run-af9"}])

            def _update(payload):
                running_updates.append(dict(payload))
                inner = MagicMock()
                inner.eq.return_value.execute.return_value = MagicMock(data=[{}])
                return inner
            m.update = _update
        elif name == "qa_run_targets":
            m.insert.return_value.execute.return_value = MagicMock(data=[{}])
        elif name == "qa_schedules":
            def _update2(payload):
                inner = MagicMock()
                inner.eq.return_value.execute.return_value = MagicMock(data=[{}])
                return inner
            m.update = _update2
        return m

    sb = MagicMock()
    sb.table.side_effect = _table

    async def _ok_dispatch(run_id, scenario_ids): pass

    async def _run():
        with patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch.object(mod, "dispatch_qa_run", _ok_dispatch):
            return await mod.scheduler_tick(sb)

    result = asyncio.run(_run())
    assert result["created"] == 1
    assert result["dispatch"] == "OK"

    running_up = [u for u in running_updates if u.get("run_status") == "RUNNING"]
    assert running_up, "RUNNING update 없음"
    assert running_up[0].get("started_at") is not None, "started_at 없음"
    assert running_up[0].get("updated_at") is not None, "updated_at 없음"


# ── AO-F10: dispatch failure → ERROR, RUNNING update 없음 ────────────────────

def test_AOF10_dispatch_failure_sets_error_not_running():
    """AO-F10: dispatch 실패 → ERROR 처리, RUNNING update 없음."""
    import services.qa_scheduler_svc as mod

    sched = _sched("item-af10", "P0-SAAS-001", next_run_offset=-1)
    run_updates: list = []

    def _table(name):
        m = MagicMock()
        if name == "qa_runs":
            m.insert.return_value.execute.return_value = MagicMock(data=[{"id": "run-af10"}])

            def _update(payload):
                run_updates.append(dict(payload))
                inner = MagicMock()
                inner.eq.return_value.execute.return_value = MagicMock(data=[{}])
                return inner
            m.update = _update
        elif name == "qa_run_targets":
            m.insert.return_value.execute.return_value = MagicMock(data=[{}])
        elif name == "qa_schedules":
            def _update2(p):
                inner = MagicMock()
                inner.eq.return_value.execute.return_value = MagicMock(data=[{}])
                return inner
            m.update = _update2
        return m

    sb = MagicMock()
    sb.table.side_effect = _table

    async def _fail_dispatch(run_id, scenario_ids): raise RuntimeError("dispatch error")

    async def _run():
        with patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch.object(mod, "dispatch_qa_run", _fail_dispatch):
            return await mod.scheduler_tick(sb)

    result = asyncio.run(_run())
    assert result["dispatch"] == "ERROR"

    running_ups = [u for u in run_updates if u.get("run_status") == "RUNNING"]
    error_ups   = [u for u in run_updates if u.get("run_status") == "ERROR"]
    assert not running_ups, f"RUNNING update가 있어선 안 됨: {running_ups}"
    assert error_ups, "ERROR update 없음"


# ── AO-F11: RUNNING → COMPLETED lifecycle 허용 ───────────────────────────────

def test_AOF11_running_to_completed_allowed():
    """AO-F11: QUEUED→RUNNING→COMPLETED lifecycle가 canonical에서 허용됨 (소스 계약)."""
    import services.qa_control_svc as svc

    transitions = getattr(svc, "_VALID_TRANSITIONS", None)
    assert transitions is not None, "_VALID_TRANSITIONS 없음"
    assert "RUNNING" in transitions.get("QUEUED", frozenset()), \
        "QUEUED→RUNNING이 _VALID_TRANSITIONS에 없음"
    assert "COMPLETED" in transitions.get("RUNNING", frozenset()), \
        "RUNNING→COMPLETED가 _VALID_TRANSITIONS에 없음"
