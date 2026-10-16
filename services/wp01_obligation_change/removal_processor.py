"""services/wp01_obligation_change/removal_processor.py

WP01-D: 의무 제거 처리 (관리자 전용).

Scope A: 단일 회차 제외 — work_schedule.is_excluded = True
Scope B: 지정일 이후 반복 중단 — future work_schedules.active_yn = False
         + inspection_sets.is_active = False

제약:
- status=completed / in_progress 인 work_schedules 는 절대 건드리지 않음.
- 레코드 삭제 없음.
- DB 마이그레이션 없음(기존 컬럼만 사용).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# 절대 변경 금지 상태값
_PRESERVE_STATUS = {"completed", "in_progress"}


# ---------------------------------------------------------------------------
# Scope-independent: preview
# ---------------------------------------------------------------------------

def preview_removal_impact(
    supabase: Any,
    factory_id: str,
    inspection_set_id: str,
    application_date: Optional[str] = None,
) -> dict:
    """READ-ONLY: 제외 처리 전 영향 일정 미리보기.

    반환:
        total_future_schedules: int — 활성 예정 일정 총 건수
        schedules_to_cancel: int — application_date 이후로 취소 대상
        schedules_to_preserve: int — application_date 이전 또는 보존 대상
        has_child_linked: bool — work_assignments 연결된 일정 존재 여부
        child_linked_count: int
    """
    # 활성 + 미완료 일정 로드
    q = (
        supabase.table("work_schedules")
        .select("id, planned_date, status")
        .eq("factory_id", factory_id)
        .eq("inspection_set_id", inspection_set_id)
        .eq("active_yn", True)
    )
    res = q.execute()
    all_schedules: List[Dict] = res.data or []

    # completed / in_progress 제외
    eligible = [
        s for s in all_schedules
        if s.get("status") not in _PRESERVE_STATUS
    ]

    total_future = len(eligible)
    schedules_to_cancel = 0
    schedules_to_preserve = 0

    if application_date:
        for s in eligible:
            pd = s.get("planned_date") or ""
            if pd >= application_date:
                schedules_to_cancel += 1
            else:
                schedules_to_preserve += 1
    else:
        schedules_to_cancel = total_future

    # work_assignments 연결 확인 (전체 활성 일정 대상)
    child_linked_count = 0
    for s in all_schedules:
        asgn_res = (
            supabase.table("work_assignments")
            .select("id")
            .eq("schedule_id", s["id"])
            .limit(1)
            .execute()
        )
        if asgn_res.data:
            child_linked_count += 1

    return {
        "total_future_schedules": total_future,
        "schedules_to_cancel": schedules_to_cancel,
        "schedules_to_preserve": schedules_to_preserve,
        "has_child_linked": child_linked_count > 0,
        "child_linked_count": child_linked_count,
    }


# ---------------------------------------------------------------------------
# Scope A: 단일 회차 제외
# ---------------------------------------------------------------------------

def process_scope_a(
    supabase: Any,
    factory_id: str,
    work_schedule_id: str,
    excluded_reason: str,
) -> dict:
    """Scope A: 이번 회차 단건 제외.

    work_schedules.is_excluded = True, excluded_reason = excluded_reason
    조건: active_yn=True, status NOT IN _PRESERVE_STATUS

    반환:
        processed: 1 성공 / 0 스킵
        skipped_reason: str or None
    """
    # 현재 상태 확인
    res = (
        supabase.table("work_schedules")
        .select("id, status, active_yn, factory_id")
        .eq("id", work_schedule_id)
        .eq("factory_id", factory_id)
        .limit(1)
        .execute()
    )

    if not res.data:
        return {"processed": 0, "skipped_reason": "일정을 찾을 수 없습니다"}

    row = res.data[0]
    status = row.get("status", "")
    active_yn = row.get("active_yn", False)

    if status in _PRESERVE_STATUS:
        return {
            "processed": 0,
            "skipped_reason": f"status={status} 인 일정은 제외할 수 없습니다",
        }

    if not active_yn:
        return {"processed": 0, "skipped_reason": "이미 비활성 상태입니다"}

    # 업데이트
    supabase.table("work_schedules").update(
        {
            "is_excluded": True,
            "excluded_reason": excluded_reason,
        }
    ).eq("id", work_schedule_id).eq("factory_id", factory_id).eq("active_yn", True).execute()

    log.info(
        "[REMOVAL_SCOPE_A] schedule=%s factory=%s reason=%s",
        work_schedule_id,
        factory_id,
        excluded_reason,
    )

    return {"processed": 1, "skipped_reason": None}


# ---------------------------------------------------------------------------
# Scope B: 지정일 이후 반복 중단
# ---------------------------------------------------------------------------

def process_scope_b(
    supabase: Any,
    factory_id: str,
    inspection_set_id: str,
    application_date: str,
    reason: str,
) -> dict:
    """Scope B: application_date 이후 일정 취소 + inspection_sets.is_active=False.

    1. inspection_sets 존재 및 활성 확인
    2. planned_date >= application_date, active_yn=True,
       status NOT IN _PRESERVE_STATUS 인 일정에 active_yn=False 설정
    3. inspection_sets.is_active = False (향후 일정 생성 차단)
    4. reason 은 서버 로그에만 기록(DB 저장 없음)

    반환:
        inspection_set_id: str
        schedules_cancelled: int
        schedules_preserved_completed: int
        is_active_set_false: bool

    레코드 삭제 없음.
    status=completed/in_progress 는 절대 건드리지 않음.
    """
    if not application_date:
        raise ValueError("application_date 는 필수입니다")

    # 1. inspection_set 존재 및 활성 확인
    is_res = (
        supabase.table("inspection_sets")
        .select("id, is_active, source")
        .eq("id", inspection_set_id)
        .eq("factory_id", factory_id)
        .limit(1)
        .execute()
    )

    if not is_res.data:
        raise ValueError(f"inspection_set 을 찾을 수 없습니다: {inspection_set_id}")

    is_row = is_res.data[0]
    if is_row.get("source") != "LEGAL_ENGINE":
        raise ValueError("LEGAL_ENGINE source 가 아닌 inspection_set 은 Scope B 처리 불가")

    if not is_row.get("is_active", False):
        # 이미 비활성 — idempotent
        log.info(
            "[REMOVAL_SCOPE_B] inspection_set=%s already is_active=False (idempotent)",
            inspection_set_id,
        )
        return {
            "inspection_set_id": inspection_set_id,
            "schedules_cancelled": 0,
            "schedules_preserved_completed": 0,
            "is_active_set_false": False,
        }

    # 2. 대상 일정 로드
    sched_res = (
        supabase.table("work_schedules")
        .select("id, status")
        .eq("factory_id", factory_id)
        .eq("inspection_set_id", inspection_set_id)
        .eq("active_yn", True)
        .gte("planned_date", application_date)
        .execute()
    )

    all_future: List[Dict] = sched_res.data or []

    to_cancel = [s for s in all_future if s.get("status") not in _PRESERVE_STATUS]
    preserved_completed = [s for s in all_future if s.get("status") in _PRESERVE_STATUS]

    # 3. 취소 — 각 일정 개별 업데이트(idempotent)
    cancelled = 0
    for s in to_cancel:
        supabase.table("work_schedules").update(
            {"active_yn": False}
        ).eq("id", s["id"]).eq("factory_id", factory_id).eq("active_yn", True).execute()
        cancelled += 1

    # 4. inspection_sets.is_active = False
    supabase.table("inspection_sets").update(
        {"is_active": False}
    ).eq("id", inspection_set_id).eq("factory_id", factory_id).execute()

    log.info(
        "[REMOVAL_SCOPE_B] inspection_set=%s factory=%s application_date=%s "
        "cancelled=%d preserved=%d reason=%s",
        inspection_set_id,
        factory_id,
        application_date,
        cancelled,
        len(preserved_completed),
        reason,
    )

    return {
        "inspection_set_id": inspection_set_id,
        "schedules_cancelled": cancelled,
        "schedules_preserved_completed": len(preserved_completed),
        "is_active_set_false": True,
    }
