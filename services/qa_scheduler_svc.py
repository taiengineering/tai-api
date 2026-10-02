"""QA Scheduler Service — WO-QA-CONTROL-PHASE2E-001.

scheduler_tick():
  1. enabled schedules where next_run_at <= now 조회
  2. 이미 QUEUED/RUNNING run이 있는 item 제외 (중복 방지)
  3. qa_run (SCHEDULE) + qa_run_targets 생성
  4. next_run_at 갱신 (기준: 기존 next_run_at, not now — cadence drift 방지)
  5. GitHub Actions dispatch

compute_next_run_at(): MINUTES / HOURLY / DAILY 계산.
  DAILY: from_dt + 1 day (from_dt = 기존 anchor 시각이므로 anchor 유지됨).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from services.github_dispatch_svc import dispatch_qa_run
from services.time import now_kst

log = logging.getLogger("qa_scheduler")

_ACTIVE_STATUSES = frozenset({"QUEUED", "RUNNING"})
_SUPPORTED_FREQ = frozenset({"MINUTES", "HOURLY", "DAILY"})


def compute_next_run_at(
    frequency_type: str,
    frequency_value: Optional[int],
    from_dt: datetime,
) -> datetime:
    """from_dt 기준으로 다음 실행 시각 계산.

    MINUTES/HOURLY: frequency_value 필수.
    DAILY: frequency_value 무시 (DB constraint: NULL). from_dt + 1 day.
    """
    if frequency_type == "MINUTES":
        fv = max(1, int(frequency_value))
        return from_dt + timedelta(minutes=fv)
    if frequency_type == "HOURLY":
        fv = max(1, int(frequency_value))
        return from_dt + timedelta(hours=fv)
    if frequency_type == "DAILY":
        return from_dt + timedelta(days=1)
    raise ValueError(f"지원하지 않는 frequency_type: {frequency_type}")


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _active_item_ids(supabase) -> frozenset:
    """현재 QUEUED/RUNNING run에 포함된 qa_item_id 집합 반환."""
    runs_res = (
        supabase.table("qa_runs")
        .select("id")
        .in_("run_status", list(_ACTIVE_STATUSES))
        .execute()
    )
    active_run_ids = [r["id"] for r in (runs_res.data or [])]
    if not active_run_ids:
        return frozenset()

    targets_res = (
        supabase.table("qa_run_targets")
        .select("qa_item_id")
        .in_("run_id", active_run_ids)
        .execute()
    )
    return frozenset(r["qa_item_id"] for r in (targets_res.data or []))


def _due_schedules(supabase, now_iso: str) -> List[Dict[str, Any]]:
    """next_run_at <= now인 enabled schedule + item 조회."""
    res = (
        supabase.table("qa_schedules")
        .select(
            "id, qa_item_id, frequency_type, frequency_value, next_run_at, "
            "qa_items!inner(id, scenario_id, enabled)"
        )
        .eq("enabled", True)
        .lte("next_run_at", now_iso)
        .execute()
    )
    return res.data or []


def _set_run_error(supabase, run_id: str, error: str) -> None:
    from services.time import serialize_external_utc
    now_iso = serialize_external_utc(now_kst())
    supabase.table("qa_runs").update({
        "run_status":    "ERROR",
        "error_summary": error[:500],
        "finished_at":   now_iso,
        "updated_at":    now_iso,
    }).eq("id", run_id).execute()


async def scheduler_tick(supabase) -> Dict[str, Any]:
    """Scheduler 한 틱 실행. 결과 summary 반환.

    중복 방지: 이미 QUEUED/RUNNING인 item은 건너뜀.
    GitHub dispatch 실패 시 해당 run만 ERROR 처리 후 계속.
    """

    now = now_kst()
    now_iso = now.isoformat()

    # 1. 실행 대기 schedule 조회
    schedules = _due_schedules(supabase, now_iso)
    if not schedules:
        return {"skipped": 0, "created": 0, "error": 0, "items": []}

    # 2. 이미 active run에 포함된 item 제외
    busy_ids = _active_item_ids(supabase)

    eligible = [
        s for s in schedules
        if s.get("qa_items", {}).get("enabled", False)
        and s["qa_item_id"] not in busy_ids
    ]

    if not eligible:
        log.info("[qa_scheduler] tick: %d schedules due, all busy/disabled — skip", len(schedules))
        return {"skipped": len(schedules), "created": 0, "error": 0, "items": []}

    # 3. qa_run 생성 (enabled items만, 하나의 run으로 묶음)
    qa_item_ids  = [s["qa_item_id"] for s in eligible]
    scenario_ids = [s["qa_items"]["scenario_id"] for s in eligible]

    run_row = {
        "trigger_type": "SCHEDULE",
        "run_status":   "QUEUED",
        "requested_by": "scheduler",
        "requested_at": now_iso,
        "created_at":   now_iso,
        "updated_at":   now_iso,
    }
    run_res = supabase.table("qa_runs").insert(run_row).execute()
    if not run_res.data:
        log.error("[qa_scheduler] qa_run insert failed")
        return {"skipped": len(schedules) - len(eligible), "created": 0, "error": 1, "items": []}

    run_id = run_res.data[0]["id"]

    # 4. qa_run_targets 생성
    target_rows = [
        {"run_id": run_id, "qa_item_id": qid, "ordinal": idx + 1, "created_at": now_iso}
        for idx, qid in enumerate(qa_item_ids)
    ]
    try:
        supabase.table("qa_run_targets").insert(target_rows).execute()
    except Exception as e:
        log.error("[qa_scheduler] target insert failed run=%s: %s", run_id, e)
        supabase.table("qa_runs").delete().eq("id", run_id).execute()
        return {"skipped": len(schedules) - len(eligible), "created": 0, "error": 1, "items": []}

    # 5. next_run_at 갱신 — 기준: sched["next_run_at"] (not now), cadence drift 방지
    for sched in eligible:
        ft = sched.get("frequency_type", "DAILY")
        fv = sched.get("frequency_value")
        try:
            if ft in _SUPPORTED_FREQ:
                base_dt = _parse_dt(sched.get("next_run_at")) or now
                next_dt = compute_next_run_at(ft, fv, base_dt)
                supabase.table("qa_schedules").update({
                    "next_run_at":       next_dt.isoformat(),
                    "last_scheduled_at": now_iso,
                    "updated_at":        now_iso,
                }).eq("id", sched["id"]).execute()
        except Exception as e:
            log.warning("[qa_scheduler] next_run_at update failed sched=%s: %s", sched["id"], e)

    # 6. GitHub Actions dispatch
    try:
        await dispatch_qa_run(run_id, scenario_ids)
    except Exception as exc:
        log.error("[qa_scheduler] dispatch failed run=%s: %s", run_id, exc)
        _set_run_error(supabase, run_id, str(exc))
        return {
            "skipped": len(schedules) - len(eligible),
            "created": 1,
            "error":   1,
            "items":   scenario_ids,
            "run_id":  run_id,
            "dispatch": "ERROR",
        }

    log.info("[qa_scheduler] tick done: run=%s items=%d", run_id, len(eligible))
    return {
        "skipped":  len(schedules) - len(eligible),
        "created":  1,
        "error":    0,
        "items":    scenario_ids,
        "run_id":   run_id,
        "dispatch": "OK",
    }
