"""QA Scheduler tests — WO-QA-CONTROL-PHASE2E-001 / WO-QA-ADMIN-EXISTING-CONSOLE-AUTOSYNC-001 STEP B.

SC-01: enabled schedule 조회 → QUEUED 상태 run 생성
SC-02: next_run_at 미도달 → run 생성 없음
SC-03: next_run_at 도달 → run 생성
SC-04: frequency MINUTES 계산
SC-05: frequency HOURLY 계산
SC-06: frequency DAILY 계산
SC-07: 중복 QUEUED/RUNNING 방지
SC-08: disabled schedule skip

B1-01: NULL next_run_at → bootstrap 실행, run 생성 없음
B1-02: MINUTES bootstrap = now + frequency_value minutes
B1-03: HOURLY bootstrap = now + frequency_value hours
B1-04: DAILY bootstrap anchor 미도달 → 오늘 anchor
B1-05: DAILY bootstrap anchor 지남 → 내일 anchor
B1-06: WEEKLY bootstrap → 다음 해당 요일 anchor

B2-01: compute_next_run_at WEEKLY = from_dt + 7 days
B2-02: WEEKLY tick due schedule → run 생성

SR-01: 기존 DAILY schedule cadence 보존 (compute_next_run_at 회귀)
SR-02: NULL bootstrap이 기존 non-NULL schedule 실행에 영향 없음

MR-01: enabled QA → MANUAL run 생성
MR-02: disabled QA → 422
MR-03: create_run trigger_type=MANUAL 고정
MR-04: create_run target 생성
"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

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


def _sched(item_id, scenario_id, ft="DAILY", fv=None, enabled_item=True, next_run_offset=-1):
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

def test_SC04_minutes_calculation():
    base = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    result = compute_next_run_at("MINUTES", 10, base)
    assert result == datetime(2026, 10, 1, 9, 10, tzinfo=timezone.utc)


def test_SC05_hourly_calculation():
    base = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    result = compute_next_run_at("HOURLY", 2, base)
    assert result == datetime(2026, 10, 1, 11, 0, tzinfo=timezone.utc)


def test_SC06_daily_calculation():
    base = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
    result = compute_next_run_at("DAILY", None, base)
    assert result == datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc)


def test_SC04b_minutes_respects_value():
    base = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    assert compute_next_run_at("MINUTES", 30, base) == datetime(2026, 10, 1, 9, 30, tzinfo=timezone.utc)


def test_SC05b_hourly_respects_value():
    base = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
    assert compute_next_run_at("HOURLY", 6, base) == datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc)


def test_SC06b_daily_anchor_preserved():
    """DAILY: anchor 시각(08:00)이 유지됨 — from_dt + 1day."""
    base = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
    result = compute_next_run_at("DAILY", None, base)
    assert result == datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc)
    assert result.hour == 8 and result.minute == 0


def test_compute_next_run_at_unknown_type_raises():
    base = datetime(2026, 10, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="지원하지 않는"):
        compute_next_run_at("MONTH", 1, base)


def test_compute_next_run_at_old_aliases_rejected():
    """MINUTE/HOUR/DAY (구 alias) 는 ValueError."""
    base = datetime(2026, 10, 1, tzinfo=timezone.utc)
    for old in ("MINUTE", "HOUR", "DAY"):
        with pytest.raises(ValueError, match="지원하지 않는"):
            compute_next_run_at(old, 1, base)


# ── SC-01/02/03: scheduler_tick with _due_schedules mock ─────────────────────

def test_SC01_due_schedule_creates_run():
    """SC-01: enabled schedule → run 생성."""
    sched = _sched("item-1", "P0-001", next_run_offset=-5)
    sb = _make_supabase(schedules=[sched])

    created_run_id = None

    async def _dispatch(run_id, scenarios, **kwargs):
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

    async def _dispatch(run_id, scenarios, **kwargs): pass

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


# ── SC-CRON: Cron guard (BC-2) ────────────────────────────────────────────────

def test_SC_CRON01_running_cron_blocks_scheduler():
    """BC-2: github-cron run이 RUNNING 중이면 해당 item이 eligible에서 제외됨."""
    sched = _sched("item-5", "P0-005", next_run_offset=-5)
    sb = _make_supabase(schedules=[sched])

    async def _run():
        import services.qa_scheduler_svc as mod
        with patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch.object(mod, "_recent_equivalent_run_exists", return_value=False), \
             patch.object(mod, "_cron_covered_item_ids", return_value=frozenset({"item-5"})):
            return await scheduler_tick(sb)

    result = asyncio.run(_run())
    assert result["created"] == 0  # all items cron-covered → eligible empty → no dispatch


def test_SC_CRON02_completed_cron_within_window_blocks_scheduler():
    """BC-2: github-cron run이 COMPLETED(3시간 내)이면 해당 item이 eligible에서 제외됨."""
    sched = _sched("item-6", "P0-006", next_run_offset=-5)
    sb = _make_supabase(schedules=[sched])

    async def _run():
        import services.qa_scheduler_svc as mod
        with patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch.object(mod, "_recent_equivalent_run_exists", return_value=False), \
             patch.object(mod, "_cron_covered_item_ids", return_value=frozenset({"item-6"})):
            return await scheduler_tick(sb)

    result = asyncio.run(_run())
    assert result["created"] == 0


def test_SC_CRON03_old_cron_outside_window_allows_scheduler():
    """BC-2: github-cron run이 3시간 초과 → cron guard 미발동, scheduler 정상 실행."""
    sched = _sched("item-7", "P0-007", next_run_offset=-5)
    sb = _make_supabase(schedules=[sched])

    async def _run():
        import services.qa_scheduler_svc as mod
        with patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch.object(mod, "_recent_equivalent_run_exists", return_value=False), \
             patch.object(mod, "_cron_covered_item_ids", return_value=frozenset()):
            with patch("services.qa_scheduler_svc.dispatch_qa_run", new=AsyncMock(return_value=None)):
                return await scheduler_tick(sb)

    result = asyncio.run(_run())
    assert result["created"] == 1
    assert result.get("dispatch") == "OK"


def test_SC_CRON04_partial_cron_coverage_excludes_only_covered_items():
    """BC-2: 51개 중 8개 cron-covered → 43개만 dispatcher 전달 (나머지 정상 실행)."""
    scheds = [_sched(f"item-{i}", f"P0-{i:03d}", next_run_offset=-5) for i in range(51)]
    cron_covered = frozenset(f"item-{i}" for i in range(8))

    async def _run():
        import services.qa_scheduler_svc as mod
        with patch.object(mod, "_due_schedules", return_value=scheds), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch.object(mod, "_recent_equivalent_run_exists", return_value=False), \
             patch.object(mod, "_cron_covered_item_ids", return_value=cron_covered):
            with patch("services.qa_scheduler_svc.dispatch_qa_run", new=AsyncMock(return_value=None)):
                return await scheduler_tick(_make_supabase(schedules=scheds))

    result = asyncio.run(_run())
    assert result["created"] == 1
    assert len(result["items"]) == 43, f"expected 43, got {len(result['items'])}"


def test_SC_CRON05_failed_cron_still_excludes_items():
    """BC-2: 06:00 cron이 FAIL이어도(run_status=COMPLETED) 해당 items는 08:00 제외됨.
    _cron_covered_item_ids는 run_status(RUNNING|COMPLETED) 기준이며 test outcome 무관."""
    sched = _sched("item-login-1", "P0-SAAS-001", next_run_offset=-5)
    sb = _make_supabase(schedules=[sched])

    async def _run():
        import services.qa_scheduler_svc as mod
        with patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch.object(mod, "_recent_equivalent_run_exists", return_value=False), \
             patch.object(mod, "_cron_covered_item_ids", return_value=frozenset({"item-login-1"})):
            with patch("services.qa_scheduler_svc.dispatch_qa_run", new=AsyncMock(return_value=None)):
                return await scheduler_tick(sb)

    result = asyncio.run(_run())
    assert result["created"] == 0  # FAIL cron run still excludes the item


def test_SC_CRON06_20h_after_window_cron_runs_normally():
    """BC-2: 20:00 정기 QA — cron guard window(180분) 밖이므로 정상 실행.
    06:00 cron 완료 14시간 후이므로 cron_covered_item_ids = frozenset() (empty)."""
    sched = _sched("item-p0-1", "P0-LOGIN-001", next_run_offset=-5)
    sb = _make_supabase(schedules=[sched])

    async def _run():
        import services.qa_scheduler_svc as mod
        with patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch.object(mod, "_recent_equivalent_run_exists", return_value=False), \
             patch.object(mod, "_cron_covered_item_ids", return_value=frozenset()):
            with patch("services.qa_scheduler_svc.dispatch_qa_run", new=AsyncMock(return_value=None)):
                return await scheduler_tick(sb)

    result = asyncio.run(_run())
    assert result["created"] == 1  # 20:00 cron dispatches normally


def test_SC_CRON07_cron_excluded_next_run_at_advanced():
    """R3-01: 08:00 scheduler가 cron-covered item을 제외할 때 next_run_at을 전진시킨다.
    전진하지 않으면 09:01+ (window 만료 후) 에 동일 item이 재Dispatch됨."""
    sched = _sched("item-cron-x", "P0-LOGIN-001", next_run_offset=-5)

    advanced_sched_ids: list = []

    class _Q:
        def __init__(self):
            self._next_run_at_pending = False

        def update(self, patch, **k):
            if "next_run_at" in patch:
                self._next_run_at_pending = True
            return self

        def eq(self, col, val):
            if self._next_run_at_pending and col == "id":
                advanced_sched_ids.append(val)
                self._next_run_at_pending = False
            return self

        def execute(self):
            return type("R", (), {"data": [{}]})()

        def select(self, *a, **k): return self
        def in_(self, *a, **k):    return self
        def lte(self, *a, **k):    return self
        def gte(self, *a, **k):    return self
        def is_(self, *a, **k):    return self
        def neq(self, *a, **k):    return self
        def insert(self, *a, **k): return self
        def delete(self, **k):     return self

    class _TrackSB:
        def table(self, _name):
            return _Q()

    async def _run():
        import services.qa_scheduler_svc as mod
        with patch.object(mod, "_null_schedules", return_value=[]), \
             patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch.object(mod, "_recent_equivalent_run_exists", return_value=False), \
             patch.object(mod, "_cron_covered_item_ids", return_value=frozenset({"item-cron-x"})):
            return await scheduler_tick(_TrackSB())

    result = asyncio.run(_run())
    assert result["created"] == 0
    assert "sched-item-cron-x" in advanced_sched_ids, (
        f"next_run_at must be advanced for cron-excluded sched-item-cron-x, got: {advanced_sched_ids}"
    )


def test_SC_CRON08a_next_run_at_written_value_is_future():
    """FG-01 / R3-01: cron-excluded item의 DB에 실제로 기록된 next_run_at 값이
    원래 next_run_at보다 20시간 이상 미래임을 검증 (DAILY advance = +24h)."""
    from datetime import datetime, timezone
    original_offset_min = -5
    sched = _sched("item-cron-x", "P0-LOGIN-001", next_run_offset=original_offset_min)
    original_next_run_at = datetime.fromisoformat(sched["next_run_at"])

    written_values: list = []

    class _Q:
        def __init__(self):
            self._patch = None

        def update(self, patch, **k):
            if "next_run_at" in patch:
                self._patch = patch["next_run_at"]
            return self

        def eq(self, col, val):
            if self._patch is not None and col == "id":
                written_values.append(self._patch)
                self._patch = None
            return self

        def execute(self):
            return type("R", (), {"data": [{}]})()

        def select(self, *a, **k): return self
        def in_(self, *a, **k):    return self
        def lte(self, *a, **k):    return self
        def gte(self, *a, **k):    return self
        def is_(self, *a, **k):    return self
        def neq(self, *a, **k):    return self
        def insert(self, *a, **k): return self
        def delete(self, **k):     return self

    class _TrackSB:
        def table(self, _name):
            return _Q()

    async def _run():
        import services.qa_scheduler_svc as mod
        with patch.object(mod, "_null_schedules", return_value=[]), \
             patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch.object(mod, "_recent_equivalent_run_exists", return_value=False), \
             patch.object(mod, "_cron_covered_item_ids", return_value=frozenset({"item-cron-x"})):
            return await scheduler_tick(_TrackSB())

    result = asyncio.run(_run())
    assert result["created"] == 0
    assert len(written_values) >= 1, "next_run_at must have been written to DB"
    written_dt = datetime.fromisoformat(written_values[0])
    min_expected = original_next_run_at + timedelta(hours=20)
    assert written_dt > min_expected, (
        f"written next_run_at {written_dt} must be > original+20h {min_expected}"
    )
    assert result.get("cron_advance_errors", 0) == 0


def test_SC_CRON08b_zero_row_update_reported_as_cron_advance_error():
    """FG-01: next_run_at UPDATE가 0건 반환(schedule 삭제됨)이면
    cron_advance_errors += 1로 기록되어야 한다."""
    sched = _sched("item-cron-del", "P0-LOGIN-001", next_run_offset=-5)

    class _ZeroRowQ:
        def update(self, *a, **k): return self
        def eq(self, *a, **k):     return self

        def execute(self):
            return type("R", (), {"data": []})()

        def select(self, *a, **k): return self
        def in_(self, *a, **k):    return self
        def lte(self, *a, **k):    return self
        def gte(self, *a, **k):    return self
        def is_(self, *a, **k):    return self
        def neq(self, *a, **k):    return self
        def insert(self, *a, **k): return self
        def delete(self, **k):     return self

    class _ZeroRowSB:
        def table(self, _name):
            return _ZeroRowQ()

    async def _run():
        import services.qa_scheduler_svc as mod
        with patch.object(mod, "_null_schedules", return_value=[]), \
             patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch.object(mod, "_recent_equivalent_run_exists", return_value=False), \
             patch.object(mod, "_cron_covered_item_ids", return_value=frozenset({"item-cron-del"})):
            return await scheduler_tick(_ZeroRowSB())

    result = asyncio.run(_run())
    assert result["created"] == 0
    assert result.get("cron_advance_errors") == 1, (
        f"expected cron_advance_errors=1 on 0-row UPDATE, got {result}"
    )


def test_SC_CRON08c_extended_guard_covers_post_180min_gap():
    """FG-01 / _CRON_GUARD_MINUTES=900: 180분 초과(예: 9h) 후 스케줄러 tick에서도
    cron-covered item이 중복 Dispatch되지 않는다.
    next_run_at UPDATE 실패 시 900분 guard가 방어막 역할을 하는지 검증."""
    # Simulate: now is 9h after cron start (well past old 180-min window)
    # _cron_covered_item_ids mock returns the item ID (guard still active per 900-min logic)
    sched = _sched("item-cron-c", "P0-LOGIN-001", next_run_offset=-5)

    async def _run():
        import services.qa_scheduler_svc as mod
        # Verify the constant is 900
        assert mod._CRON_GUARD_MINUTES == 900, (
            f"_CRON_GUARD_MINUTES must be 900 for FG-01 safety, got {mod._CRON_GUARD_MINUTES}"
        )
        with patch.object(mod, "_null_schedules", return_value=[]), \
             patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch.object(mod, "_recent_equivalent_run_exists", return_value=False), \
             patch.object(mod, "_cron_covered_item_ids", return_value=frozenset({"item-cron-c"})):
            return await scheduler_tick(_make_supabase())

    result = asyncio.run(_run())
    assert result["created"] == 0, (
        "item covered by 900-min cron guard must not be dispatched even after 180-min window"
    )


def test_SC_CRON09_mixed_51_items_8_excluded_next_run_at_advanced():
    """R3-01 + BC-2 통합: 51개 중 8건 cron-covered → 43건 dispatch, 8건 next_run_at 전진."""
    scheds = [_sched(f"item-{i}", f"P0-{i:03d}", next_run_offset=-5) for i in range(51)]
    cron_covered = frozenset(f"item-{i}" for i in range(8))

    advanced_sched_ids: list = []

    class _Q:
        def __init__(self):
            self._nrat_pending = False
            self._last_insert = None

        def update(self, patch, **k):
            if "next_run_at" in patch:
                self._nrat_pending = True
            return self

        def eq(self, col, val):
            if self._nrat_pending and col == "id":
                advanced_sched_ids.append(val)
                self._nrat_pending = False
            return self

        def execute(self):
            return type("R", (), {"data": [{"id": "run-mix"}]})()

        def insert(self, rows, **k):
            self._last_insert = rows
            return self

        def select(self, *a, **k): return self
        def in_(self, *a, **k):    return self
        def lte(self, *a, **k):    return self
        def gte(self, *a, **k):    return self
        def is_(self, *a, **k):    return self
        def neq(self, *a, **k):    return self
        def delete(self, **k):     return self

    class _MixSB:
        def table(self, _name):
            return _Q()

    async def _run():
        import services.qa_scheduler_svc as mod
        with patch.object(mod, "_null_schedules", return_value=[]), \
             patch.object(mod, "_due_schedules", return_value=scheds), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch.object(mod, "_recent_equivalent_run_exists", return_value=False), \
             patch.object(mod, "_cron_covered_item_ids", return_value=cron_covered):
            with patch("services.qa_scheduler_svc.dispatch_qa_run", new=AsyncMock(return_value=None)):
                return await scheduler_tick(_MixSB())

    result = asyncio.run(_run())
    assert result["created"] == 1
    assert len(result["items"]) == 43, f"expected 43 dispatched, got {len(result['items'])}"
    # next_run_at must have been advanced for each of the 8 cron-excluded items
    expected_excluded = {f"sched-item-{i}" for i in range(8)}
    assert expected_excluded.issubset(set(advanced_sched_ids)), (
        f"missing next_run_at advances. expected {sorted(expected_excluded)}, "
        f"got {sorted(advanced_sched_ids)}"
    )


def test_SC_CRON10_error_cron_run_blocks_scheduler():
    """R3-02: 06:00 cron이 ERROR로 끝나도 해당 item이 08:00 scheduler에서 제외됨.
    _CRON_GUARD_STATUSES = {"RUNNING", "COMPLETED", "ERROR"} 확인."""
    sched = _sched("item-err-1", "P0-LOGIN-001", next_run_offset=-5)
    sb = _make_supabase(schedules=[sched])

    async def _run():
        import services.qa_scheduler_svc as mod
        # Verify ERROR is in guard statuses
        assert "ERROR" in mod._CRON_GUARD_STATUSES, (
            f"ERROR must be in _CRON_GUARD_STATUSES, got {mod._CRON_GUARD_STATUSES}"
        )
        with patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch.object(mod, "_recent_equivalent_run_exists", return_value=False), \
             patch.object(mod, "_cron_covered_item_ids", return_value=frozenset({"item-err-1"})):
            return await scheduler_tick(sb)

    result = asyncio.run(_run())
    assert result["created"] == 0  # ERROR state cron excludes the item


def test_SC_CRON11_error_guard_next_run_at_advanced():
    """R3-02 + R3-01: ERROR 상태 cron으로 제외된 item의 next_run_at도 전진됨.
    08:00에 제외되고 next_run_at 전진 → 09:01에 재실행되지 않음."""
    sched = _sched("item-err-2", "P0-LOGIN-002", next_run_offset=-5)

    advanced_ids: list = []

    class _Q:
        def __init__(self):
            self._pending = False

        def update(self, patch, **k):
            if "next_run_at" in patch:
                self._pending = True
            return self

        def eq(self, col, val):
            if self._pending and col == "id":
                advanced_ids.append(val)
                self._pending = False
            return self

        def execute(self):
            return type("R", (), {"data": [{}]})()

        def select(self, *a, **k): return self
        def in_(self, *a, **k):    return self
        def lte(self, *a, **k):    return self
        def gte(self, *a, **k):    return self
        def is_(self, *a, **k):    return self
        def neq(self, *a, **k):    return self
        def insert(self, *a, **k): return self
        def delete(self, **k):     return self

    class _TrackSB:
        def table(self, _name):
            return _Q()

    async def _run():
        import services.qa_scheduler_svc as mod
        with patch.object(mod, "_null_schedules", return_value=[]), \
             patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch.object(mod, "_recent_equivalent_run_exists", return_value=False), \
             patch.object(mod, "_cron_covered_item_ids", return_value=frozenset({"item-err-2"})):
            return await scheduler_tick(_TrackSB())

    result = asyncio.run(_run())
    assert result["created"] == 0
    assert "sched-item-err-2" in advanced_ids, (
        f"next_run_at must advance for ERROR-excluded item, got: {advanced_ids}"
    )


def test_SC_CRON12_error_cron_outside_window_allows_scheduler():
    """R3-02: 06:00 cron이 ERROR로 끝난 후 180분 창 만료(09:01+) → 정상 dispatch.
    window 밖이면 _cron_covered_item_ids가 frozenset() 반환 → scheduler 정상 실행."""
    sched = _sched("item-err-3", "P0-LOGIN-003", next_run_offset=-5)
    sb = _make_supabase(schedules=[sched])

    async def _run():
        import services.qa_scheduler_svc as mod
        with patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch.object(mod, "_recent_equivalent_run_exists", return_value=False), \
             patch.object(mod, "_cron_covered_item_ids", return_value=frozenset()):
            with patch("services.qa_scheduler_svc.dispatch_qa_run", new=AsyncMock(return_value=None)):
                return await scheduler_tick(sb)

    result = asyncio.run(_run())
    assert result["created"] == 1  # window expired → normal dispatch
    assert result.get("dispatch") == "OK"


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

    async def _fake_dispatch(run_id, scenario_ids, **kwargs):
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


# ── B2-01/02: WEEKLY compute_next_run_at ─────────────────────────────────────

def test_B2_01_weekly_compute_adds_7_days():
    """B2-01: WEEKLY compute_next_run_at = from_dt + 7 days."""
    from services.qa_scheduler_svc import compute_next_run_at
    base = datetime(2026, 10, 5, 8, 0, tzinfo=timezone.utc)  # Monday
    result = compute_next_run_at("WEEKLY", None, base)
    assert result == datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)


def test_B2_01b_weekly_compute_preserves_time():
    """B2-01b: WEEKLY next run은 동일 시각 다음 주."""
    from services.qa_scheduler_svc import compute_next_run_at
    base = datetime(2026, 10, 3, 23, 0, tzinfo=timezone.utc)
    result = compute_next_run_at("WEEKLY", None, base)
    assert result == base + timedelta(days=7)


def test_B2_02_weekly_tick_creates_run():
    """B2-02: WEEKLY due schedule → run 생성."""
    sched = _sched("item-w1", "P1-W-001", ft="WEEKLY", fv=None, next_run_offset=-1)
    sb = _make_supabase(schedules=[sched])

    async def _dispatch(run_id, scenario_ids, **kwargs): pass

    async def _run():
        import services.qa_scheduler_svc as mod
        with patch.object(mod, "_due_schedules", return_value=[sched]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()), \
             patch.object(mod, "_null_schedules", return_value=[]), \
             patch.object(mod, "dispatch_qa_run", _dispatch):
            return await scheduler_tick(sb)

    result = asyncio.run(_run())
    assert result["created"] == 1
    assert "P1-W-001" in result["items"]


# ── B1-01~06: bootstrap_next_run_at ──────────────────────────────────────────

def test_B1_01_null_schedule_bootstrapped_no_run():
    """B1-01: NULL next_run_at → bootstrap 업데이트, run 미생성."""
    null_sched = {
        "id": "sched-null-1",
        "qa_item_id": "item-null-1",
        "frequency_type": "DAILY",
        "frequency_value": None,
        "anchor_time": "08:00:00",
        "day_of_week": None,
        "timezone": "Asia/Seoul",
    }
    # due_schedules 는 비어 있으므로 run 생성 없음
    sb = _make_supabase(schedules=[])
    updated_ids: list = []

    def _table(name):
        m = MagicMock()
        if name == "qa_schedules":
            def _update(data):
                inner = MagicMock()
                def _eq(col, val):
                    updated_ids.append(val)
                    mm = MagicMock()
                    mm.execute.return_value = MagicMock(data=[{}])
                    return mm
                inner.eq = _eq
                return inner
            m.update = _update

            def _select2(*a, **k):
                inner = MagicMock()
                inner.eq.return_value.lte.return_value = MagicMock(
                    execute=MagicMock(return_value=MagicMock(data=[]))
                )
                inner.eq.return_value.is_.return_value.neq.return_value = MagicMock(
                    execute=MagicMock(return_value=MagicMock(data=[null_sched]))
                )
                return inner
            m.select.side_effect = _select2
        elif name == "qa_runs":
            m.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
        elif name == "qa_run_targets":
            m.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
        return m

    sb.table.side_effect = _table

    async def _run():
        import services.qa_scheduler_svc as mod
        with patch.object(mod, "_null_schedules", return_value=[null_sched]), \
             patch.object(mod, "_due_schedules", return_value=[]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()):
            return await scheduler_tick(sb)

    result = asyncio.run(_run())
    assert result["created"] == 0
    assert result["bootstrapped"] == 1


def test_B1_02_minutes_bootstrap():
    """B1-02: MINUTES bootstrap = now + frequency_value minutes."""
    from services.qa_scheduler_svc import bootstrap_next_run_at
    now = datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc)
    sched = {"frequency_type": "MINUTES", "frequency_value": 30, "timezone": "Asia/Seoul"}
    result = bootstrap_next_run_at(sched, now)
    assert result == datetime(2026, 10, 3, 9, 30, tzinfo=timezone.utc)


def test_B1_03_hourly_bootstrap():
    """B1-03: HOURLY bootstrap = now + frequency_value hours."""
    from services.qa_scheduler_svc import bootstrap_next_run_at
    now = datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc)
    sched = {"frequency_type": "HOURLY", "frequency_value": 2, "timezone": "Asia/Seoul"}
    result = bootstrap_next_run_at(sched, now)
    assert result == datetime(2026, 10, 3, 11, 0, tzinfo=timezone.utc)


def test_B1_04_daily_bootstrap_anchor_future():
    """B1-04: DAILY bootstrap anchor 미도달 → 오늘 anchor (KST 08:00 = UTC 23:00 전날)."""
    from services.qa_scheduler_svc import bootstrap_next_run_at
    # KST 07:00 = UTC 22:00 (전날). anchor=08:00 KST → 아직 안 됨 → 오늘 anchor
    now_kst_07 = datetime(2026, 10, 3, 22, 0, tzinfo=timezone.utc)  # 10-04 07:00 KST
    sched = {
        "frequency_type": "DAILY",
        "frequency_value": None,
        "anchor_time": "08:00:00",
        "timezone": "Asia/Seoul",
    }
    result = bootstrap_next_run_at(sched, now_kst_07)
    # 10-04 08:00 KST = UTC 23:00 (10-03)
    assert result == datetime(2026, 10, 3, 23, 0, tzinfo=timezone.utc)


def test_B1_05_daily_bootstrap_anchor_past():
    """B1-05: DAILY bootstrap anchor 지남 → 내일 anchor."""
    from services.qa_scheduler_svc import bootstrap_next_run_at
    # KST 09:00 = UTC 00:00. anchor=08:00 KST → 이미 지남 → 내일
    now_kst_09 = datetime(2026, 10, 4, 0, 0, tzinfo=timezone.utc)  # 10-04 09:00 KST
    sched = {
        "frequency_type": "DAILY",
        "frequency_value": None,
        "anchor_time": "08:00:00",
        "timezone": "Asia/Seoul",
    }
    result = bootstrap_next_run_at(sched, now_kst_09)
    # 10-05 08:00 KST = UTC 10-04 23:00
    assert result == datetime(2026, 10, 4, 23, 0, tzinfo=timezone.utc)


def test_B1_06_weekly_bootstrap_next_occurrence():
    """B1-06: WEEKLY bootstrap → day_of_week(1=월) anchor 다음 발생일.

    기준: 2026-10-03 (토, 10:00 KST). 다음 월요일 = 2026-10-05.
    anchor=09:00 KST, day_of_week=1(월).
    """
    from services.qa_scheduler_svc import bootstrap_next_run_at
    import zoneinfo
    KST = zoneinfo.ZoneInfo("Asia/Seoul")
    # 2026-10-03 토요일 10:00 KST = UTC 01:00
    now = datetime(2026, 10, 3, 1, 0, tzinfo=timezone.utc)
    sched = {
        "frequency_type": "WEEKLY",
        "frequency_value": None,
        "anchor_time": "09:00:00",
        "day_of_week": 1,  # 월요일
        "timezone": "Asia/Seoul",
    }
    result = bootstrap_next_run_at(sched, now)
    # 2026-10-05 (월) 09:00 KST = UTC 00:00
    expected = datetime(2026, 10, 5, 0, 0, tzinfo=timezone.utc)
    assert result == expected


def test_B1_06b_weekly_bootstrap_same_day_anchor_future():
    """B1-06b: 오늘이 target 요일이고 anchor 아직 안 됨 → 오늘 anchor."""
    from services.qa_scheduler_svc import bootstrap_next_run_at
    # 2026-10-05 월요일 08:00 KST = UTC 10-04 23:00. anchor=09:00 KST → 아직 안 됨
    now = datetime(2026, 10, 4, 23, 0, tzinfo=timezone.utc)  # 10-05 08:00 KST
    sched = {
        "frequency_type": "WEEKLY",
        "frequency_value": None,
        "anchor_time": "09:00:00",
        "day_of_week": 1,  # 월요일
        "timezone": "Asia/Seoul",
    }
    result = bootstrap_next_run_at(sched, now)
    # 10-05 09:00 KST = UTC 00:00
    expected = datetime(2026, 10, 5, 0, 0, tzinfo=timezone.utc)
    assert result == expected


def test_B1_06c_weekly_bootstrap_same_day_anchor_past():
    """B1-06c: 오늘이 target 요일이고 anchor 지남 → 다음 주 동일 요일."""
    from services.qa_scheduler_svc import bootstrap_next_run_at
    # 2026-10-05 월요일 10:00 KST = UTC 01:00. anchor=09:00 KST → 이미 지남
    now = datetime(2026, 10, 5, 1, 0, tzinfo=timezone.utc)  # 10-05 10:00 KST
    sched = {
        "frequency_type": "WEEKLY",
        "frequency_value": None,
        "anchor_time": "09:00:00",
        "day_of_week": 1,  # 월요일
        "timezone": "Asia/Seoul",
    }
    result = bootstrap_next_run_at(sched, now)
    # 10-12 09:00 KST = UTC 00:00
    expected = datetime(2026, 10, 12, 0, 0, tzinfo=timezone.utc)
    assert result == expected


# ── SR-01/02: Schedule Regression ────────────────────────────────────────────

def test_SR01_daily_cadence_preserved():
    """SR-01: 기존 DAILY compute_next_run_at — anchor 보존 (회귀)."""
    base = datetime(2026, 10, 3, 23, 0, tzinfo=timezone.utc)  # 08:00 KST
    result = compute_next_run_at("DAILY", None, base)
    assert result == datetime(2026, 10, 4, 23, 0, tzinfo=timezone.utc)  # 익일 08:00 KST


def test_SR02_null_bootstrap_no_run_in_same_tick():
    """SR-02: NULL bootstrap은 해당 틱에서 run 생성 없음 (다음 틱부터 실행 가능)."""
    null_sched = {
        "id": "sched-sr-1",
        "qa_item_id": "item-sr-1",
        "frequency_type": "MINUTES",
        "frequency_value": 30,
        "anchor_time": None,
        "day_of_week": None,
        "timezone": "Asia/Seoul",
    }
    sb = _make_supabase(schedules=[])

    async def _run():
        import services.qa_scheduler_svc as mod
        with patch.object(mod, "_null_schedules", return_value=[null_sched]), \
             patch.object(mod, "_due_schedules", return_value=[]), \
             patch.object(mod, "_active_item_ids", return_value=frozenset()):
            return await scheduler_tick(sb)

    result = asyncio.run(_run())
    assert result["created"] == 0
    assert result["bootstrapped"] == 1
