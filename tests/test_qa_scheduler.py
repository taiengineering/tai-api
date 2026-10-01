"""QA Scheduler tests — WO-QA-CONTROL-PHASE2E-001.

SC-01: enabled schedule 조회 → QUEUED 상태 run 생성
SC-02: next_run_at 미도달 → run 생성 없음
SC-03: next_run_at 도달 → run 생성
SC-04: frequency MINUTE 계산
SC-05: frequency HOUR 계산
SC-06: frequency DAY 계산
SC-07: 중복 QUEUED/RUNNING 방지
SC-08: disabled schedule skip

MR-01: enabled QA → MANUAL run 생성
MR-02: disabled QA → 422
MR-03: create_run trigger_type=MANUAL 고정
MR-04: create_run target 생성
"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from services.qa_scheduler_svc import compute_next_run_at, scheduler_tick


# ── helpers ───────────────────────────────────────────────────────────────────

def _dt(offset_minutes=0):
    """UTC 기준 현재 ± offset 분."""
    return (datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)).isoformat()


def _make_supabase(
    schedules=None,
    active_runs=None,
    active_targets=None,
    run_insert_id="run-abc",
    target_ok=True,
):
    """scheduler_tick에 필요한 Supabase mock 구성."""
    sb = MagicMock()

    # qa_runs (active check)
    runs_chain = MagicMock()
    runs_chain.execute.return_value = MagicMock(data=active_runs or [])
    sb.table.return_value.select.return_value.in_.return_value = runs_chain

    # qa_run_targets (active targets)
    targets_chain = MagicMock()
    targets_chain.execute.return_value = MagicMock(data=active_targets or [])

    # due schedules
    sched_chain = MagicMock()
    sched_chain.execute.return_value = MagicMock(data=schedules or [])

    # qa_runs insert
    run_insert_chain = MagicMock()
    run_insert_chain.execute.return_value = MagicMock(data=[{"id": run_insert_id}])

    # qa_run_targets insert
    if target_ok:
        target_insert_chain = MagicMock()
        target_insert_chain.execute.return_value = MagicMock(data=[{}])
    else:
        target_insert_chain = MagicMock()
        target_insert_chain.execute.side_effect = Exception("target insert fail")

    # qa_schedules update
    sched_update_chain = MagicMock()
    sched_update_chain.eq.return_value.execute.return_value = MagicMock(data=[{}])

    # qa_runs update (ERROR)
    run_update_chain = MagicMock()
    run_update_chain.eq.return_value.execute.return_value = MagicMock(data=[{}])

    # qa_runs delete (rollback)
    run_delete_chain = MagicMock()
    run_delete_chain.eq.return_value.execute.return_value = MagicMock(data=[{}])

    # Route table calls by name
    def _table(name):
        m = MagicMock()
        if name == "qa_runs":
            def _select(*a, **k):
                inner = MagicMock()
                inner.in_.return_value = runs_chain
                return inner
            m.select.side_effect = _select
            m.insert.return_value = run_insert_chain
            m.update.return_value = run_update_chain
            m.delete.return_value = run_delete_chain
        elif name == "qa_run_targets":
            m.select.return_value.in_.return_value = targets_chain
            m.insert.return_value = target_insert_chain
        elif name == "qa_schedules":
            def _select2(*a, **k):
                inner = MagicMock()
                inner.eq.return_value.lte.return_value = sched_chain
                return inner
            m.select.side_effect = _select2
            m.update.return_value = sched_update_chain
        return m

    sb.table.side_effect = _table
    return sb


def _sched(item_id, scenario_id, ft="DAY", fv=1, enabled_item=True, next_run_offset=-1):
    """schedule row fixture."""
    return {
        "id":             f"sched-{item_id}",
        "qa_item_id":     item_id,
        "frequency_type": ft,
        "frequency_value": fv,
        "next_run_at":    _dt(next_run_offset),
        "qa_items": {
            "id":          item_id,
            "scenario_id": scenario_id,
            "enabled":     enabled_item,
        },
    }


async def _tick_with_dispatch(sb, dispatch_ok=True):
    """scheduler_tick을 dispatch mock과 함께 실행."""
    async def _ok_dispatch(run_id, scenario_ids): pass
    async def _fail_dispatch(run_id, scenario_ids): raise RuntimeError("dispatch error")

    with patch("services.qa_scheduler_svc.scheduler_tick.__wrapped__", None):
        with patch(
            "services.qa_scheduler_svc.dispatch_qa_run" if hasattr(asyncio, "run") else "services.github_dispatch_svc.dispatch_qa_run",
            side_effect=_ok_dispatch if dispatch_ok else _fail_dispatch,
        ):
            # direct import patch
            import services.qa_scheduler_svc as mod
            orig = getattr(mod, "_due_schedules", None)
            orig_active = getattr(mod, "_active_item_ids", None)
            return await scheduler_tick(sb)


# ── SC-04/05/06: compute_next_run_at ─────────────────────────────────────────

def test_SC04_minute_calculation():
    base = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    result = compute_next_run_at("MINUTE", 10, base)
    assert result == datetime(2026, 10, 1, 9, 10, tzinfo=timezone.utc)


def test_SC05_hour_calculation():
    base = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    result = compute_next_run_at("HOUR", 2, base)
    assert result == datetime(2026, 10, 1, 11, 0, tzinfo=timezone.utc)


def test_SC06_day_calculation():
    base = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
    result = compute_next_run_at("DAY", 1, base)
    assert result == datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc)


def test_SC04b_minute_respects_value():
    base = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    assert compute_next_run_at("MINUTE", 30, base) == datetime(2026, 10, 1, 9, 30, tzinfo=timezone.utc)


def test_SC05b_hour_respects_value():
    base = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
    assert compute_next_run_at("HOUR", 6, base) == datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc)


def test_SC06b_day_multi():
    base = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
    assert compute_next_run_at("DAY", 7, base) == datetime(2026, 10, 8, 8, 0, tzinfo=timezone.utc)


def test_compute_next_run_at_unknown_type_raises():
    base = datetime(2026, 10, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="지원하지 않는"):
        compute_next_run_at("MONTH", 1, base)


# ── SC-01/02/03: scheduler_tick with _due_schedules mock ─────────────────────

def test_SC01_due_schedule_creates_run():
    """SC-01: enabled schedule → run 생성."""
    sched = _sched("item-1", "P0-001", next_run_offset=-5)
    sb = _make_supabase(schedules=[sched])

    created_run_id = None

    async def _dispatch(run_id, scenarios):
        nonlocal created_run_id
        created_run_id = run_id

    async def _run():
        import services.qa_scheduler_svc as mod
        with patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch("services.qa_scheduler_svc.dispatch_qa_run", _dispatch):
            return await scheduler_tick(sb)

    result = asyncio.run(_run())
    assert result["created"] == 1
    assert result["dispatch"] == "OK"
    assert "P0-001" in result["items"]


def test_SC02_no_due_schedules_no_run():
    """SC-02: next_run_at 미도달(empty list) → run 생성 없음."""
    sb = _make_supabase(schedules=[])

    async def _run():
        import services.qa_scheduler_svc as mod
        with patch.object(mod, "_due_schedules", return_value=[]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()):
            return await scheduler_tick(sb)

    result = asyncio.run(_run())
    assert result["created"] == 0


def test_SC03_due_schedule_creates_run_verify_trigger():
    """SC-03: next_run_at 도달 → run 생성 + trigger_type=SCHEDULE (소스 계약 검증)."""
    import inspect, services.qa_scheduler_svc as mod
    src = inspect.getsource(mod.scheduler_tick)
    # scheduler_tick 소스에 SCHEDULE trigger_type이 명시되어 있는지 확인
    assert '"SCHEDULE"' in src or "'SCHEDULE'" in src

    # 실행 레벨: due schedule → created=1
    sched = _sched("item-2", "P0-002", next_run_offset=-1)
    sb = _make_supabase(schedules=[sched])

    async def _dispatch(run_id, scenarios): pass

    async def _run():
        with patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch.object(mod, "dispatch_qa_run", _dispatch):
            return await scheduler_tick(sb)

    result = asyncio.run(_run())
    assert result["created"] == 1
    assert result["dispatch"] == "OK"


def test_SC07_duplicate_active_run_skipped():
    """SC-07: 이미 QUEUED/RUNNING인 item → run 생성 없음."""
    sched = _sched("item-3", "P0-003", next_run_offset=-5)
    sb = _make_supabase(schedules=[sched])

    async def _run():
        import services.qa_scheduler_svc as mod
        # item-3이 이미 active run에 있음
        with patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset({"item-3"})):
            return await scheduler_tick(sb)

    result = asyncio.run(_run())
    assert result["created"] == 0
    assert result["skipped"] == 1


def test_SC08_disabled_schedule_skipped():
    """SC-08: qa_item.enabled=False → run 생성 없음."""
    sched = _sched("item-4", "P0-004", enabled_item=False, next_run_offset=-5)
    sb = _make_supabase(schedules=[sched])

    async def _run():
        import services.qa_scheduler_svc as mod
        with patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()):
            return await scheduler_tick(sb)

    result = asyncio.run(_run())
    assert result["created"] == 0


# ── MR-01~04: Manual Run (create_run svc 단위) ────────────────────────────────

def _make_sb_for_create_run(items, target_ok=True):
    """create_run 전용 Supabase mock."""
    from unittest.mock import MagicMock
    sb = MagicMock()

    # items 조회
    items_chain = MagicMock()
    items_chain.execute.return_value = MagicMock(data=items)
    sb.table.return_value.select.return_value.in_.return_value = items_chain

    # run insert
    run_insert = MagicMock()
    run_insert.execute.return_value = MagicMock(data=[{"id": "run-manual-1"}])
    sb.table.return_value.insert.return_value = run_insert

    # target insert
    if target_ok:
        target_insert = MagicMock()
        target_insert.execute.return_value = MagicMock(data=[{}])
    else:
        target_insert = MagicMock()
        target_insert.execute.side_effect = Exception("fail")

    def _table(name):
        m = MagicMock()
        if name == "qa_items":
            m.select.return_value.in_.return_value = items_chain
        elif name == "qa_runs":
            m.insert.return_value = run_insert
            m.delete.return_value.eq.return_value.execute.return_value = MagicMock()
        elif name == "qa_run_targets":
            m.insert.return_value = target_insert if target_ok else MagicMock(
                **{"execute.side_effect": Exception("fail")}
            )
        return m

    sb.table.side_effect = _table
    return sb


def test_MR01_enabled_item_creates_run():
    """MR-01: enabled=true QA → MANUAL run 생성."""
    from services import qa_control_svc as svc
    sb = _make_sb_for_create_run([{"id": "item-1", "enabled": True}])
    result = svc.create_run(sb, "admin-user", ["item-1"])
    assert result["id"] == "run-manual-1"


def test_MR02_disabled_item_raises_422():
    """MR-02: enabled=false QA → 422."""
    from services import qa_control_svc as svc
    from fastapi import HTTPException
    sb = _make_sb_for_create_run([{"id": "item-1", "enabled": False}])
    with pytest.raises(HTTPException) as exc_info:
        svc.create_run(sb, "admin-user", ["item-1"])
    assert exc_info.value.status_code == 422


def test_MR03_trigger_type_manual():
    """MR-03: create_run trigger_type=MANUAL 고정."""
    from services import qa_control_svc as svc
    inserted = {}

    sb = MagicMock()
    sb.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(
        data=[{"id": "item-1", "enabled": True}]
    )

    def _insert(data):
        inserted.update(data if isinstance(data, dict) else {})
        m = MagicMock()
        m.execute.return_value = MagicMock(data=[{"id": "run-m"}])
        return m

    def _table(name):
        m = MagicMock()
        if name == "qa_items":
            m.select.return_value.in_.return_value.execute.return_value = MagicMock(
                data=[{"id": "item-1", "enabled": True}]
            )
        elif name == "qa_runs":
            m.insert = _insert
        elif name == "qa_run_targets":
            m.insert.return_value.execute.return_value = MagicMock(data=[{}])
        return m

    sb.table.side_effect = _table
    svc.create_run(sb, "admin-user", ["item-1"])
    assert inserted.get("trigger_type") == "MANUAL"
    assert inserted.get("run_status") == "QUEUED"


def test_MR04_targets_created():
    """MR-04: create_run → qa_run_targets 생성."""
    from services import qa_control_svc as svc
    target_rows: list = []

    def _table(name):
        m = MagicMock()
        if name == "qa_items":
            m.select.return_value.in_.return_value.execute.return_value = MagicMock(
                data=[{"id": "i1", "enabled": True}, {"id": "i2", "enabled": True}]
            )
        elif name == "qa_runs":
            m.insert.return_value.execute.return_value = MagicMock(data=[{"id": "run-r"}])
        elif name == "qa_run_targets":
            def _ins(rows):
                target_rows.extend(rows)
                mm = MagicMock()
                mm.execute.return_value = MagicMock(data=[{}])
                return mm
            m.insert = _ins
        return m

    sb = MagicMock()
    sb.table.side_effect = _table
    svc.create_run(sb, "admin", ["i1", "i2"])
    assert len(target_rows) == 2
    assert {r["qa_item_id"] for r in target_rows} == {"i1", "i2"}
    assert sorted(r["ordinal"] for r in target_rows) == [1, 2]


def test_MR04b_dispatch_connected():
    """MR-04b: POST /admin/qa/runs 라우터가 dispatch_qa_run을 호출한다."""
    dispatched: list = []

    async def _fake_dispatch(run_id, scenario_ids):
        dispatched.append({"run_id": run_id, "scenario_ids": scenario_ids})

    fake_run = {
        "id": "run-dispatch-test",
        "targets": [{"qa_item_id": "item-d1", "ordinal": 1}],
    }

    sb = MagicMock()
    sb.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(
        data=[{"id": "item-d1", "scenario_id": "P0-DISP-001"}]
    )

    async def _run():
        import routers.admin_qa as mod
        with patch("routers.admin_qa.get_supabase", return_value=sb), \
             patch("routers.admin_qa._require_admin"), \
             patch("routers.admin_qa.svc.create_run", return_value=fake_run), \
             patch("services.github_dispatch_svc.dispatch_qa_run", _fake_dispatch):
            body = MagicMock()
            body.qa_item_ids = ["item-d1"]
            current = {"id": "admin-user"}
            return await mod.create_run(body, current)

    result = asyncio.run(_run())
    assert result["dispatch"] == "OK"
    assert len(dispatched) == 1
    assert dispatched[0]["run_id"] == "run-dispatch-test"
    assert "P0-DISP-001" in dispatched[0]["scenario_ids"]
