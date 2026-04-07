"""
work_schedules.py — v1.1.0

v1.1.0 (2026-04-07):
  [ADD] PATCH /work-schedules/batch-update   — 복수 건 일괄 업데이트
  [ADD] POST  /work-schedules/confirm/{factory_id} — 검토 확정

API:
  GET   /work-schedules                              전체 목록
  GET   /work-schedules/factory/{factory_id}         공장별 목록
  GET   /work-schedules/inspection-set/{id}          점검세트별 목록
  PATCH /work-schedules/batch-update                 일괄 업데이트  ← v1.1.0
  POST  /work-schedules/confirm/{factory_id}         검토 확정     ← v1.1.0
  GET   /work-schedules/{schedule_id}                단건 조회
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone

from db.supabase_client import get_supabase

router = APIRouter(prefix="/work-schedules", tags=["work_schedules"])

VERSION = "1.1.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Pydantic 모델 ─────────────────────────────────────────────

class ScheduleUpdateItem(BaseModel):
    id:               str
    is_excluded:      Optional[bool]  = None
    excluded_reason:  Optional[str]   = None
    custom_cycle:     Optional[str]   = None   # ex) 'MONTHLY', '3MONTH'
    assigned_user_id: Optional[str]   = None   # null 허용 → 배정 해제


class BatchUpdateBody(BaseModel):
    updates: List[ScheduleUpdateItem]


class ConfirmBody(BaseModel):
    reviewed_by: str   # user uuid


# ── 고정경로 먼저 선언 (/{schedule_id} 보다 앞에) ──────────────

@router.patch("/batch-update")
def batch_update_schedules(body: BatchUpdateBody):
    """
    v1.1.0: 복수 work_schedules 일괄 업데이트.

    - is_excluded / excluded_reason / custom_cycle 업데이트
    - assigned_user_id 있으면 work_assignments에도 반영
      · 기존 PENDING 배정 있으면 UPDATE, 없으면 INSERT
      · null 전달 시 기존 배정 취소(CANCELLED)
    """
    supabase = get_supabase()
    now      = _now()
    updated  = 0

    for item in body.updates:
        # work_schedules 업데이트할 필드만 추려냄
        payload: dict = {"updated_at": now}
        if item.is_excluded is not None:
            payload["is_excluded"] = item.is_excluded
        if item.excluded_reason is not None:
            payload["excluded_reason"] = item.excluded_reason
        if item.custom_cycle is not None:
            payload["custom_cycle"] = item.custom_cycle
        # assigned_user_id: 명시적으로 전달된 경우만 (None이 아닌 것 포함)
        assign_changed = "assigned_user_id" in item.__fields_set__
        if assign_changed:
            payload["assigned_user_id"] = item.assigned_user_id

        # work_schedules UPDATE
        res = supabase.table("work_schedules").update(payload).eq("id", item.id).execute()
        if res.data:
            updated += 1

        # work_assignments 처리
        if assign_changed:
            if item.assigned_user_id:
                # 기존 PENDING 배정 조회
                existing = supabase.table("work_assignments") \
                    .select("id") \
                    .eq("schedule_id", item.id) \
                    .eq("status_code", "PENDING") \
                    .limit(1).execute()

                if existing.data:
                    # 기존 배정 UPDATE
                    supabase.table("work_assignments").update({
                        "assigned_user_id": item.assigned_user_id,
                        "updated_at": now,
                    }).eq("id", existing.data[0]["id"]).execute()
                else:
                    # 신규 INSERT
                    supabase.table("work_assignments").insert({
                        "schedule_id":      item.id,
                        "assigned_user_id": item.assigned_user_id,
                        "scheduled_date":   datetime.now().date().isoformat(),
                        "status_code":      "PENDING",
                        "created_at":       now,
                    }).execute()
            else:
                # assigned_user_id = null → 기존 PENDING 배정 취소
                supabase.table("work_assignments").update({
                    "status_code": "CANCELLED",
                    "updated_at":  now,
                }).eq("schedule_id", item.id).eq("status_code", "PENDING").execute()

    return {"status": "success", "data": {"updated": updated}}


@router.post("/confirm/{factory_id}")
def confirm_schedules(factory_id: str, body: ConfirmBody):
    """
    v1.1.0: 검토 완료 후 스케줄 확정.

    1. factory_id의 is_excluded=FALSE 스케줄 전체 → reviewed_at / reviewed_by 업데이트
    2. custom_cycle 있는 건 → cycle_code = custom_cycle 로 반영
    3. is_excluded=TRUE 건 → status_code='EXCLUDED', is_active=FALSE
    4. 결과: { confirmed, excluded, created }
       (created는 향후 inspection_schedule 자동생성 예약 — 현재 0 반환)
    """
    supabase = get_supabase()
    now      = _now()

    # ── 1. is_excluded = FALSE: 확정 처리 ──────────────────────
    active_res = supabase.table("work_schedules") \
        .select("id, custom_cycle") \
        .eq("factory_id", factory_id) \
        .eq("is_excluded", False) \
        .eq("active_yn", True) \
        .execute()
    active_rows = active_res.data or []

    confirmed = 0
    for row in active_rows:
        update_payload: dict = {
            "reviewed_at": now,
            "reviewed_by": body.reviewed_by,
            "updated_at":  now,
        }
        # custom_cycle 있으면 cycle_code도 덮어쓰기
        if row.get("custom_cycle"):
            update_payload["cycle_code"] = row["custom_cycle"]

        supabase.table("work_schedules").update(update_payload).eq("id", row["id"]).execute()
        confirmed += 1

    # ── 2. is_excluded = TRUE: EXCLUDED 처리 ───────────────────
    excluded_res = supabase.table("work_schedules") \
        .select("id") \
        .eq("factory_id", factory_id) \
        .eq("is_excluded", True) \
        .execute()
    excluded_rows = excluded_res.data or []

    excluded = 0
    if excluded_rows:
        exc_ids = [r["id"] for r in excluded_rows]
        for i in range(0, len(exc_ids), 50):
            batch = exc_ids[i:i+50]
            supabase.table("work_schedules").update({
                "status_code": "EXCLUDED",
                "is_active":   False,
                "updated_at":  now,
            }).in_("id", batch).execute()
        excluded = len(excluded_rows)

    return {
        "status": "success",
        "data": {
            "confirmed": confirmed,
            "excluded":  excluded,
            "created":   0,   # 향후 inspection_schedule 자동생성 시 업데이트
        },
    }


# ── 기존 CRUD ─────────────────────────────────────────────────

@router.get("")
def get_work_schedules():
    supabase = get_supabase()
    result = (
        supabase.table("work_schedules")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


@router.get("/factory/{factory_id}")
def get_factory_work_schedules(factory_id: str):
    supabase = get_supabase()
    result = (
        supabase.table("work_schedules")
        .select("*")
        .eq("factory_id", factory_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


@router.get("/inspection-set/{inspection_set_id}")
def get_inspection_set_work_schedules(inspection_set_id: str):
    supabase = get_supabase()
    result = (
        supabase.table("work_schedules")
        .select("*")
        .eq("inspection_set_id", inspection_set_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


# /{schedule_id}는 반드시 모든 고정경로 뒤에 선언
@router.get("/{schedule_id}")
def get_work_schedule(schedule_id: str):
    supabase = get_supabase()
    result = (
        supabase.table("work_schedules")
        .select("*")
        .eq("id", schedule_id)
        .limit(1)
        .execute()
    )
    return result.data
