"""services/wp01_obligation_change/removal_processor.py

WP01-D: 의무 제거 처리 (관리자 전용).

Scope A: 단일 회차 제외
  - work_schedule.is_excluded=True, active_yn=False, status_code='EXCLUDED'
Scope B: 지정일 이후 반복 중단
  - work_schedules: planned_date >= application_date → active_yn=False
  - inspection_sets: scope_b_deactivation_date = application_date (P0-01)
                     is_active=False only if application_date <= today
  REQUIRES: scope_b_deactivation_date 컬럼
  (migration: 20261017000001_wp01d_inspection_sets_scope_b.sql)

제약:
- status_code=completed / in_progress 인 work_schedules 는 절대 변경 금지.
- 레코드 삭제 없음.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from services.inspection_sets_svc.law_engine import _child_linked
from services.status_vocab import normalize_ws_status_read

log = logging.getLogger(__name__)

# 정규화된 상태값 기준 — 절대 변경 금지
_PRESERVE_STATUS = {"completed", "in_progress"}


def _is_preserve(row: dict) -> bool:
    """work_schedules row 가 보호 대상 상태인지 확인 (status_code 정규화)."""
    normalized = normalize_ws_status_read(row.get("status_code"))
    return (normalized or "") in _PRESERVE_STATUS


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
        total_future_schedules: int — 활성·미완료 일정 총 건수
        schedules_to_cancel: int — application_date 이후로 취소 대상
        schedules_to_preserve: int — application_date 이전 또는 보존 대상
        has_child_linked: bool — work_assignments 연결된 일정 존재 여부
        child_linked_count: int
    """
    res = (
        supabase.table("work_schedules")
        .select("id, planned_date, status_code")
        .eq("factory_id", factory_id)
        .eq("inspection_set_id", inspection_set_id)
        .eq("active_yn", True)
        .execute()
    )
    all_schedules: List[Dict] = res.data or []

    eligible = [s for s in all_schedules if not _is_preserve(s)]

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

    # FIX-04: child_linked 는 취소 대상(eligible)에서만 산출 — 보존 이력은 이미 건드리지 않음
    child_linked_count = 0
    for s in eligible:
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

    work_schedules: is_excluded=True, excluded_reason, active_yn=False, status_code='EXCLUDED'
    기존 work_schedules 계약 (is_excluded=TRUE → status_code='EXCLUDED', active_yn=FALSE) 준수.
    조건: active_yn=True, status_code NOT IN _PRESERVE_STATUS

    반환:
        processed: 1 성공 / 0 스킵
        skipped_reason: str or None
    """
    res = (
        supabase.table("work_schedules")
        .select("id, status_code, active_yn, factory_id")
        .eq("id", work_schedule_id)
        .eq("factory_id", factory_id)
        .limit(1)
        .execute()
    )

    if not res.data:
        return {"processed": 0, "skipped_reason": "일정을 찾을 수 없습니다"}

    row = res.data[0]
    active_yn = row.get("active_yn", False)

    if _is_preserve(row):
        status_code = row.get("status_code", "")
        return {
            "processed": 0,
            "skipped_reason": f"status_code={status_code} 인 일정은 제외할 수 없습니다",
        }

    if not active_yn:
        return {"processed": 0, "skipped_reason": "이미 비활성 상태입니다"}

    # P0-04: 연결된 배정·점검 이력 확인 (child_linked 가드)
    if _child_linked(supabase, row["id"], factory_id):
        return {"processed": 0, "skipped_reason": "연결된 배정·점검 이력이 있습니다"}

    # FIX-01: UPDATE 결과 확인 — race condition 대응 (active_yn 사전 검사 후 변경 가능성)
    update_res = supabase.table("work_schedules").update(
        {
            "is_excluded": True,
            "excluded_reason": excluded_reason,
            "active_yn": False,
            "status_code": "EXCLUDED",
        }
    ).eq("id", work_schedule_id).eq("factory_id", factory_id).eq("active_yn", True).execute()

    if not update_res.data:
        return {"processed": 0, "skipped_reason": "업데이트 대상 없음 (이미 처리된 일정)"}

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
    """Scope B: 지정일 이후 반복 중단.

    1. inspection_set 유효성 확인 (LEGAL_ENGINE, is_active=True)
    2. work_schedules: planned_date >= application_date, NOT preserve → active_yn=False
    3. inspection_sets:
       - scope_b_deactivation_date = application_date (영속 기록)
       - scope_b_reason = reason
       - is_active=False ONLY IF application_date <= today
         (미래 날짜: 스케줄러가 scope_b_deactivation_date 를 조회해 차단)
    반환:
        inspection_set_id, schedules_cancelled, schedules_preserved_completed,
        is_active_set_false, scope_b_deactivation_date
    멱등: is_active=False 이고 scope_b_deactivation_date 이미 설정 → 0건 반환.
    """
    if not application_date:
        raise ValueError("application_date 는 필수입니다")

    # 1. inspection_set 검증
    is_res = (
        supabase.table("inspection_sets")
        .select("id, is_active, source, scope_b_deactivation_date")
        .eq("id", inspection_set_id)
        .eq("factory_id", factory_id)
        .limit(1)
        .execute()
    )

    if not is_res.data:
        raise ValueError(
            f"inspection_set 을 찾을 수 없습니다: id={inspection_set_id}"
        )

    iset = is_res.data[0]

    if iset.get("source") != "LEGAL_ENGINE":
        raise ValueError(
            "Scope B 는 LEGAL_ENGINE 출처의 의무 세트만 처리 가능합니다"
        )

    # 멱등: 이미 처리 완료
    if not iset.get("is_active") and iset.get("scope_b_deactivation_date"):
        return {
            "inspection_set_id": inspection_set_id,
            "schedules_cancelled": 0,
            "schedules_preserved_completed": 0,
            "is_active_set_false": False,
            "scope_b_deactivation_date": iset.get("scope_b_deactivation_date"),
        }

    # P0-06: application_date 파싱 엄격화 — 쿼리 전 검증
    try:
        app_dt = date.fromisoformat(str(application_date))
    except ValueError:
        raise ValueError(
            f"application_date 형식이 잘못되었습니다: {application_date!r} (YYYY-MM-DD 필요)"
        )

    # FIX-03: 과거 소급 취소 차단 — application_date 가 과거라도 오늘 이전 미완료 일정 보존
    effective_from = max(app_dt, date.today())

    # 2. 대상 일정 로드 (effective_from 기준: 오늘 이후만)
    sched_res = (
        supabase.table("work_schedules")
        .select("id, status_code")
        .eq("factory_id", factory_id)
        .eq("inspection_set_id", inspection_set_id)
        .eq("active_yn", True)
        .gte("planned_date", str(effective_from))
        .execute()
    )

    all_future: List[Dict] = sched_res.data or []
    to_cancel = [s for s in all_future if not _is_preserve(s)]
    preserved_completed = [s for s in all_future if _is_preserve(s)]

    # 3. 취소 (idempotent) — P0-04: child_linked 확인 + 실제 UPDATE 성공 건수 집계
    cancelled = 0
    child_linked_count = 0
    for s in to_cancel:
        if _child_linked(supabase, s["id"], factory_id):
            child_linked_count += 1
            continue
        res = supabase.table("work_schedules").update(
            {"active_yn": False}
        ).eq("id", s["id"]).eq("factory_id", factory_id).eq("active_yn", True).execute()
        if res.data:  # 실제 변경된 행이 있는 경우만 카운트
            cancelled += 1

    # 4. inspection_sets: scope_b_deactivation_date 설정 + 조건부 is_active
    today = date.today()

    is_active_false = app_dt <= today
    update_payload: Dict[str, Any] = {
        "scope_b_deactivation_date": str(app_dt),
        "scope_b_reason": reason,
    }
    if is_active_false:
        update_payload["is_active"] = False

    supabase.table("inspection_sets").update(update_payload).eq(
        "id", inspection_set_id
    ).eq("factory_id", factory_id).execute()

    log.info(
        "[REMOVAL_SCOPE_B] inspection_set=%s factory=%s application_date=%s "
        "cancelled=%d preserved=%d is_active_set_false=%s reason=%s",
        inspection_set_id,
        factory_id,
        application_date,
        cancelled,
        len(preserved_completed),
        is_active_false,
        reason,
    )

    return {
        "inspection_set_id": inspection_set_id,
        "schedules_cancelled": cancelled,
        "schedules_preserved_completed": len(preserved_completed),
        "child_linked_count": child_linked_count,
        "is_active_set_false": is_active_false,
        "scope_b_deactivation_date": str(app_dt),
    }
