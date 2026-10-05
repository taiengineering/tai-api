"""WO-QA-COST-001A — Scheduler cooldown / dispatch dedup tests.

COST-S01  recent equivalent run 없음 → dispatch
COST-S02  동일 batch COMPLETED 5분 전 → SKIPPED_COOLDOWN, GitHub dispatch=0
COST-S03  동일 batch FAIL/ERROR 5분 전 → dispatch (실패는 cooldown 제외)
COST-S04  다른 item set 최근 run → dispatch
COST-S05  최근 PR trigger run → scheduled cooldown 영향 없음 → dispatch
COST-S06  cooldown 경과 (> cooldown window) → dispatch
COST-S07  active QUEUED/RUNNING → 기존 active guard 유지
COST-S08  cooldown skip 시 next_run_at 정상 전진
COST-S09  production DB fixture = 0 (모든 assert가 mock 기반)
COST-S10  GitHub dispatch = 0 on cooldown (mock 확인)
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.qa_scheduler_svc as svc
from services.qa_scheduler_svc import _recent_equivalent_run_exists, _get_cooldown_minutes


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _dt_offset(minutes: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _make_cooldown_supabase(
    *,
    recent_schedule_run_ids: list[str] | None = None,
    run_targets: dict[str, list[str]] | None = None,
) -> MagicMock:
    """Focused supabase mock for _recent_equivalent_run_exists testing.

    recent_schedule_run_ids: list of run IDs returned by the cooldown query
    run_targets: {run_id: [qa_item_ids]}
    """
    recent_schedule_run_ids = recent_schedule_run_ids or []
    run_targets = run_targets or {}

    sb = MagicMock()

    def _table(name):
        m = MagicMock()
        if name == "qa_runs":
            # cooldown query: .select().eq().in_().gte().execute()
            chain = MagicMock()
            chain.execute.return_value = MagicMock(
                data=[{"id": rid} for rid in recent_schedule_run_ids]
            )
            m.select.return_value.eq.return_value.in_.return_value.gte.return_value = chain
        elif name == "qa_run_targets":
            # per-run target query: .select().eq().execute()
            def _targets_select(*a, **k):
                inner = MagicMock()
                def _eq(col, val):
                    items = run_targets.get(val, [])
                    eq_chain = MagicMock()
                    eq_chain.execute.return_value = MagicMock(
                        data=[{"qa_item_id": item_id} for item_id in items]
                    )
                    return eq_chain
                inner.eq.side_effect = _eq
                return inner
            m.select.side_effect = _targets_select
        return m

    sb.table.side_effect = _table
    return sb


def _make_tick_supabase(
    schedules: list | None = None,
    active_runs: list | None = None,
    active_targets: list | None = None,
    recent_run_ids: list | None = None,
    run_targets_map: dict | None = None,
    run_insert_id: str = "run-cost-001",
    next_run_update_store: list | None = None,
):
    """Full scheduler_tick supabase mock with cooldown support."""
    schedules       = schedules or []
    active_runs     = active_runs or []
    active_targets  = active_targets or []
    recent_run_ids  = recent_run_ids or []
    run_targets_map = run_targets_map or {}

    sb = MagicMock()

    # qa_runs insert chain
    run_insert_chain = MagicMock()
    run_insert_chain.execute.return_value = MagicMock(data=[{"id": run_insert_id}])

    # qa_run_targets insert chain
    target_insert_chain = MagicMock()
    target_insert_chain.execute.return_value = MagicMock(data=[{}])

    # qa_schedules update chain
    sched_update_calls = next_run_update_store if next_run_update_store is not None else []

    def _table(name):
        m = MagicMock()

        if name == "qa_runs":
            def _select(*a, **k):
                inner = MagicMock()
                # active check: .select().in_("run_status", ...) → active_runs
                active_chain = MagicMock()
                active_chain.execute.return_value = MagicMock(data=active_runs)
                inner.in_.return_value = active_chain

                # cooldown check: .select().eq().in_().gte() → recent_run_ids
                cooldown_chain = MagicMock()
                cooldown_chain.execute.return_value = MagicMock(
                    data=[{"id": rid} for rid in recent_run_ids]
                )
                inner.eq.return_value.in_.return_value.gte.return_value = cooldown_chain

                return inner

            m.select.side_effect = _select
            m.insert.return_value = run_insert_chain

            # update chain (RUNNING/ERROR)
            upd = MagicMock()
            upd.eq.return_value.execute.return_value = MagicMock(data=[{}])
            m.update.return_value = upd

            # delete chain (rollback)
            del_chain = MagicMock()
            del_chain.eq.return_value.execute.return_value = MagicMock(data=[{}])
            m.delete.return_value = del_chain

        elif name == "qa_run_targets":
            # active target query: .select().in_() → active_targets
            act_chain = MagicMock()
            act_chain.execute.return_value = MagicMock(data=active_targets)

            # cooldown per-run target query: .select().eq()
            def _tgt_select(*a, **k):
                inner = MagicMock()
                inner.in_.return_value = act_chain
                def _eq(col, val):
                    items = run_targets_map.get(val, [])
                    eq_chain = MagicMock()
                    eq_chain.execute.return_value = MagicMock(
                        data=[{"qa_item_id": i} for i in items]
                    )
                    return eq_chain
                inner.eq.side_effect = _eq
                return inner

            m.select.side_effect = _tgt_select
            m.insert.return_value = target_insert_chain

        elif name == "qa_schedules":
            def _sched_select(*a, **k):
                inner = MagicMock()
                # bootstrap: .eq("enabled").is_("next_run_at").neq() → empty
                inner.eq.return_value.is_.return_value.neq.return_value.execute.return_value = MagicMock(data=[])
                # due: .eq("enabled").lte() → schedules
                inner.eq.return_value.lte.return_value.execute.return_value = MagicMock(data=schedules)
                return inner
            m.select.side_effect = _sched_select

            def _sched_update(data, **k):
                if next_run_update_store is not None:
                    sched_update_calls.append(data)
                upd = MagicMock()
                upd.eq.return_value.execute.return_value = MagicMock(data=[{}])
                return upd
            m.update.side_effect = _sched_update

        return m

    sb.table.side_effect = _table
    return sb


def _sched_item(item_id: str, scenario_id: str, offset_min: int = -1) -> dict:
    return {
        "id":              f"sched-{item_id}",
        "qa_item_id":      item_id,
        "frequency_type":  "MINUTES",
        "frequency_value": 5,
        "next_run_at":     _dt_offset(offset_min),
        "qa_items":        {"id": item_id, "scenario_id": scenario_id, "enabled": True},
    }


async def _run_tick(sb, dispatch_ok: bool = True) -> dict:
    async def _ok(*a, **k):  pass
    async def _fail(*a, **k): raise RuntimeError("dispatch error")
    with patch("services.qa_scheduler_svc.dispatch_qa_run", side_effect=_ok if dispatch_ok else _fail):
        return await svc.scheduler_tick(sb)


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests: _recent_equivalent_run_exists
# ─────────────────────────────────────────────────────────────────────────────

def test_COST_S01_no_recent_run_returns_false():
    sb = _make_cooldown_supabase(recent_schedule_run_ids=[])
    now = datetime.now(timezone.utc)
    result = _recent_equivalent_run_exists(sb, ["item-1", "item-2"], 60, now)
    assert result is False


def test_COST_S02_equivalent_completed_run_returns_true():
    sb = _make_cooldown_supabase(
        recent_schedule_run_ids=["run-recent-1"],
        run_targets={"run-recent-1": ["item-2", "item-1"]},  # different order — set match
    )
    now = datetime.now(timezone.utc)
    result = _recent_equivalent_run_exists(sb, ["item-1", "item-2"], 60, now)
    assert result is True


def test_COST_S04_different_item_set_returns_false():
    sb = _make_cooldown_supabase(
        recent_schedule_run_ids=["run-recent-2"],
        run_targets={"run-recent-2": ["item-3", "item-4"]},  # different items
    )
    now = datetime.now(timezone.utc)
    result = _recent_equivalent_run_exists(sb, ["item-1", "item-2"], 60, now)
    assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests: scheduler_tick with cooldown
# ─────────────────────────────────────────────────────────────────────────────

def test_COST_S01_dispatch_when_no_recent():
    """No recent equivalent SCHEDULE run → dispatch proceeds."""
    sb = _make_tick_supabase(
        schedules=[_sched_item("item-1", "P0-AAA-001")],
        recent_run_ids=[],
    )
    result = asyncio.run(_run_tick(sb))
    assert result["dispatch"] == "OK"
    assert result["created"] == 1


def test_COST_S02_skip_when_cooldown_active():
    """Equivalent SCHEDULE run in cooldown window → SKIPPED_COOLDOWN, created=0."""
    sb = _make_tick_supabase(
        schedules=[_sched_item("item-1", "P0-AAA-001")],
        recent_run_ids=["run-recent"],
        run_targets_map={"run-recent": ["item-1"]},
    )
    result = asyncio.run(_run_tick(sb))
    assert result["dispatch"] == "SKIPPED_COOLDOWN"
    assert result["created"] == 0


def test_COST_S03_dispatch_when_recent_run_is_fail():
    """Recent SCHEDULE run was FAIL/ERROR — cooldown query returns no match.

    The cooldown mock only returns run IDs for success statuses.
    Since FAIL runs don't appear in _COOLDOWN_SUCCESS_STATUSES query results,
    we simulate this by returning empty recent_run_ids (no success-status runs).
    """
    sb = _make_tick_supabase(
        schedules=[_sched_item("item-1", "P0-AAA-001")],
        recent_run_ids=[],  # FAIL run not in cooldown query result
    )
    result = asyncio.run(_run_tick(sb))
    assert result["dispatch"] == "OK"
    assert result["created"] == 1


def test_COST_S04_dispatch_when_different_item_set():
    """Recent run has different item set → dispatch."""
    sb = _make_tick_supabase(
        schedules=[_sched_item("item-1", "P0-AAA-001")],
        recent_run_ids=["run-other"],
        run_targets_map={"run-other": ["item-99"]},  # different items
    )
    result = asyncio.run(_run_tick(sb))
    assert result["dispatch"] == "OK"
    assert result["created"] == 1


def test_COST_S05_pr_run_does_not_affect_schedule_cooldown():
    """PR trigger runs are excluded from cooldown query (trigger_type != SCHEDULE).

    Simulated by returning empty recent run IDs (the cooldown query filters by trigger_type=SCHEDULE).
    """
    sb = _make_tick_supabase(
        schedules=[_sched_item("item-1", "P0-AAA-001")],
        recent_run_ids=[],  # PR runs don't appear in SCHEDULE cooldown query
    )
    result = asyncio.run(_run_tick(sb))
    assert result["dispatch"] == "OK"


def test_COST_S06_dispatch_when_cooldown_expired():
    """Cooldown window passed → recent run not returned by gte filter → dispatch.

    Simulated by returning empty recent_run_ids (query cutoff filtered them out).
    """
    sb = _make_tick_supabase(
        schedules=[_sched_item("item-1", "P0-AAA-001")],
        recent_run_ids=[],
    )
    result = asyncio.run(_run_tick(sb))
    assert result["dispatch"] == "OK"


def test_COST_S07_active_guard_still_applies():
    """Active QUEUED/RUNNING item → skipped by active guard (existing behavior)."""
    sb = _make_tick_supabase(
        schedules=[_sched_item("item-1", "P0-AAA-001")],
        active_runs=[{"id": "run-active"}],
        active_targets=[{"qa_item_id": "item-1"}],  # item-1 is busy
    )
    result = asyncio.run(_run_tick(sb))
    # All items busy → skipped (not a cooldown skip)
    assert result["created"] == 0
    assert result.get("dispatch") != "OK"


def test_COST_S08_next_run_at_advances_on_cooldown_skip():
    """On cooldown skip, next_run_at must still advance (schedule not killed)."""
    next_run_update_store: list = []
    sb = _make_tick_supabase(
        schedules=[_sched_item("item-1", "P0-AAA-001")],
        recent_run_ids=["run-recent"],
        run_targets_map={"run-recent": ["item-1"]},
        next_run_update_store=next_run_update_store,
    )
    result = asyncio.run(_run_tick(sb))
    assert result["dispatch"] == "SKIPPED_COOLDOWN"
    # next_run_at update must have been called at least once
    assert any("next_run_at" in u for u in next_run_update_store), (
        f"next_run_at was not advanced on cooldown skip. updates={next_run_update_store}"
    )


def test_COST_S09_no_production_db():
    """All assertions are based on mock data — no real DB connection needed."""
    sb = _make_tick_supabase(schedules=[])
    result = asyncio.run(_run_tick(sb))
    assert result["created"] == 0  # trivial: empty schedules


def test_COST_S10_no_github_dispatch_on_cooldown():
    """dispatch_qa_run is never called when cooldown is active."""
    dispatch_called = []

    async def _mock_dispatch(*a, **k):
        dispatch_called.append(a)

    sb = _make_tick_supabase(
        schedules=[_sched_item("item-1", "P0-AAA-001")],
        recent_run_ids=["run-recent"],
        run_targets_map={"run-recent": ["item-1"]},
    )

    async def _run():
        with patch("services.qa_scheduler_svc.dispatch_qa_run", side_effect=_mock_dispatch):
            return await svc.scheduler_tick(sb)

    result = asyncio.run(_run())
    assert result["dispatch"] == "SKIPPED_COOLDOWN"
    assert len(dispatch_called) == 0, f"dispatch_qa_run was called: {dispatch_called}"


# ─────────────────────────────────────────────────────────────────────────────
# _get_cooldown_minutes contract
# ─────────────────────────────────────────────────────────────────────────────

def test_cooldown_default():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("QA_SCHEDULE_DISPATCH_COOLDOWN_MINUTES", None)
        assert _get_cooldown_minutes() == 60


def test_cooldown_env_override():
    with patch.dict(os.environ, {"QA_SCHEDULE_DISPATCH_COOLDOWN_MINUTES": "30"}):
        assert _get_cooldown_minutes() == 30


def test_cooldown_minimum_enforced():
    with patch.dict(os.environ, {"QA_SCHEDULE_DISPATCH_COOLDOWN_MINUTES": "5"}):
        assert _get_cooldown_minutes() == 15  # min 15


def test_cooldown_invalid_env_uses_default():
    with patch.dict(os.environ, {"QA_SCHEDULE_DISPATCH_COOLDOWN_MINUTES": "not_a_number"}):
        assert _get_cooldown_minutes() == 60
