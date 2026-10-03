"""QA Scheduler Service — WO-QA-CONTROL-PHASE2E-001 / WO-QA-ADMIN-EXISTING-CONSOLE-AUTOSYNC-001 STEP B.

scheduler_tick():
  0. Bootstrap: next_run_at IS NULL인 enabled schedule에 초기 실행시각 부여 (실행 없음)
  1. enabled schedules where next_run_at <= now 조회
  2. 이미 QUEUED/RUNNING run이 있는 item 제외 (중복 방지)
  3. qa_run (SCHEDULE) + qa_run_targets 생성
  4. next_run_at 갱신 (기준: 기존 next_run_at, not now — cadence drift 방지)
  5. GitHub Actions dispatch

compute_next_run_at(): MINUTES / HOURLY / DAILY / WEEKLY 계산.
  DAILY:  from_dt + 1 day (from_dt = 기존 anchor 시각이므로 anchor 유지됨).
  WEEKLY: from_dt + 7 days (bootstrap에서 anchor/dow 반영됨 — 이후 주기는 7일 고정).

bootstrap_next_run_at(): MANUAL 제외 enabled+NULL schedule에 now 기준 첫 next_run_at 계산.
  DAILY/WEEKLY: timezone(Asia/Seoul) + anchor_time 기준.
"""
from __future__ import annotations

import asyncio
import logging
import zoneinfo
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from services.github_dispatch_svc import dispatch_qa_run
from services.time import now_kst

log = logging.getLogger("qa_scheduler")

_ACTIVE_STATUSES = frozenset({"QUEUED", "RUNNING"})
_SUPPORTED_FREQ = frozenset({"MINUTES", "HOURLY", "DAILY", "WEEKLY"})


def compute_next_run_at(
    frequency_type: str,
    frequency_value: Optional[int],
    from_dt: datetime,
) -> datetime:
    """from_dt 기준으로 다음 실행 시각 계산 (진행 중 schedule 갱신용).

    MINUTES/HOURLY: frequency_value 필수.
    DAILY:  frequency_value 무시. from_dt + 1 day (anchor 유지).
    WEEKLY: frequency_value 무시. from_dt + 7 days (동일 요일·시각 다음 주).
    """
    if frequency_type == "MINUTES":
        fv = max(1, int(frequency_value))
        return from_dt + timedelta(minutes=fv)
    if frequency_type == "HOURLY":
        fv = max(1, int(frequency_value))
        return from_dt + timedelta(hours=fv)
    if frequency_type == "DAILY":
        return from_dt + timedelta(days=1)
    if frequency_type == "WEEKLY":
        return from_dt + timedelta(days=7)
    raise ValueError(f"지원하지 않는 frequency_type: {frequency_type}")


def bootstrap_next_run_at(sched: Dict[str, Any], now: datetime) -> datetime:
    """NULL next_run_at인 enabled schedule에 now 기준 첫 실행시각 계산.

    MINUTES/HOURLY: now + interval.
    DAILY:  tz 기준 오늘 anchor_time(미도달) 또는 내일 anchor_time.
    WEEKLY: tz 기준 day_of_week+anchor_time 다음 발생일.
            day_of_week: 0=일(Sun), 1=월(Mon), …, 6=토(Sat).
    MANUAL: ValueError (caller가 제외해야 함).
    """
    ft = sched.get("frequency_type", "DAILY")
    tz_name = sched.get("timezone") or "Asia/Seoul"
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = zoneinfo.ZoneInfo("Asia/Seoul")

    if ft == "MINUTES":
        fv = max(1, int(sched.get("frequency_value") or 1))
        return now + timedelta(minutes=fv)

    if ft == "HOURLY":
        fv = max(1, int(sched.get("frequency_value") or 1))
        return now + timedelta(hours=fv)

    if ft in ("DAILY", "WEEKLY"):
        anchor_raw = (sched.get("anchor_time") or "08:00:00")[:5]  # "HH:MM"
        h = int(anchor_raw[:2])
        m = int(anchor_raw[3:5])
        now_local = now.astimezone(tz)

        if ft == "DAILY":
            candidate = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
            if candidate <= now_local:
                candidate += timedelta(days=1)
            return candidate.astimezone(timezone.utc)

        # WEEKLY — day_of_week: 0=Sun,1=Mon,…,6=Sat → Python weekday 0=Mon,…,6=Sun
        our_dow = int(sched.get("day_of_week") or 0)
        target_py_dow = (our_dow - 1) % 7
        today_py_dow = now_local.weekday()
        days_ahead = (target_py_dow - today_py_dow) % 7

        candidate = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
        if days_ahead == 0 and candidate <= now_local:
            days_ahead = 7
        if days_ahead > 0:
            candidate = (now_local + timedelta(days=days_ahead)).replace(
                hour=h, minute=m, second=0, microsecond=0
            )
        return candidate.astimezone(timezone.utc)

    raise ValueError(f"bootstrap 미지원 frequency_type: {ft}")


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


def _null_schedules(supabase) -> List[Dict[str, Any]]:
    """next_run_at IS NULL인 enabled schedule (MANUAL 제외). bootstrap 대상."""
    res = (
        supabase.table("qa_schedules")
        .select(
            "id, qa_item_id, frequency_type, frequency_value, "
            "anchor_time, day_of_week, timezone"
        )
        .eq("enabled", True)
        .is_("next_run_at", "null")
        .neq("frequency_type", "MANUAL")
        .execute()
    )
    return res.data or []


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


def _set_run_running(supabase, run_id: str) -> None:
    from services.time import serialize_external_utc
    now_iso = serialize_external_utc(now_kst())
    supabase.table("qa_runs").update({
        "run_status": "RUNNING",
        "started_at": now_iso,
        "updated_at": now_iso,
    }).eq("id", run_id).execute()


async def scheduler_tick(supabase) -> Dict[str, Any]:
    """Scheduler 한 틱 실행. 결과 summary 반환.

    0. Bootstrap: next_run_at IS NULL인 enabled schedule에 초기 실행시각 부여 (run 생성 없음).
    중복 방지: 이미 QUEUED/RUNNING인 item은 건너뜀.
    GitHub dispatch 실패 시 해당 run만 ERROR 처리 후 계속.
    """

    now = now_kst()
    now_iso = now.isoformat()

    # 0. Bootstrap: NULL next_run_at → 초기 실행시각 계산 후 DB 갱신 (이번 틱은 실행하지 않음)
    bootstrapped = 0
    for sched in _null_schedules(supabase):
        try:
            next_dt = bootstrap_next_run_at(sched, now)
            supabase.table("qa_schedules").update({
                "next_run_at": next_dt.isoformat(),
                "updated_at":  now_iso,
            }).eq("id", sched["id"]).execute()
            bootstrapped += 1
            log.info("[qa_scheduler] bootstrap sched=%s next=%s", sched["id"], next_dt.isoformat())
        except Exception as e:
            log.warning("[qa_scheduler] bootstrap failed sched=%s: %s", sched["id"], e)

    # 1. 실행 대기 schedule 조회
    schedules = _due_schedules(supabase, now_iso)
    if not schedules:
        return {"skipped": 0, "created": 0, "error": 0, "bootstrapped": bootstrapped, "items": []}

    # 2. 이미 active run에 포함된 item 제외
    busy_ids = _active_item_ids(supabase)

    eligible = [
        s for s in schedules
        if s.get("qa_items", {}).get("enabled", False)
        and s["qa_item_id"] not in busy_ids
    ]

    if not eligible:
        log.info("[qa_scheduler] tick: %d schedules due, all busy/disabled — skip", len(schedules))
        return {"skipped": len(schedules), "created": 0, "error": 0, "bootstrapped": bootstrapped, "items": []}

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
        return {"skipped": len(schedules) - len(eligible), "created": 0, "error": 1, "bootstrapped": bootstrapped, "items": []}

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
        return {"skipped": len(schedules) - len(eligible), "created": 0, "error": 1, "bootstrapped": bootstrapped, "items": []}

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

    # 6. GitHub Actions dispatch → QUEUED→RUNNING (manual path와 동일 lifecycle)
    # Scheduler는 conditional 권한을 자동 획득하지 않는다 — allow_conditional=False 명시.
    try:
        await dispatch_qa_run(run_id, scenario_ids, allow_conditional=False)
        _set_run_running(supabase, run_id)
    except Exception as exc:
        log.error("[qa_scheduler] dispatch failed run=%s: %s", run_id, exc)
        _set_run_error(supabase, run_id, str(exc))
        return {
            "skipped":     len(schedules) - len(eligible),
            "created":     1,
            "error":       1,
            "bootstrapped": bootstrapped,
            "items":       scenario_ids,
            "run_id":      run_id,
            "dispatch":    "ERROR",
        }

    log.info("[qa_scheduler] tick done: run=%s items=%d", run_id, len(eligible))
    return {
        "skipped":     len(schedules) - len(eligible),
        "created":     1,
        "error":       0,
        "bootstrapped": bootstrapped,
        "items":       scenario_ids,
        "run_id":      run_id,
        "dispatch":    "OK",
    }
