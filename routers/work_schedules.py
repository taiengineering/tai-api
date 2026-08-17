"""
work_schedules.py — v1.2.4

v1.2.4 (2026-08-17, LEDGER ㉙):
  [ADD] GET /work-schedules 에 obligation_type · planned_date_from · planned_date_to 필터.
        점검 캘린더/작업일정 화면이 보내던 계획일 범위·의무구분 필터가 서버에 선언되지
        않아 무시되던 것 해소. planned_date · obligation_type 은 실제 컬럼(실측 확인).

v1.2.3 (2026-08-17, LEDGER ㉑·㉘·㉝):
  [ADD] PATCH /work-schedules/{schedule_id} — 단건 갱신(담당자 배정·상태 등).
  [ADD] POST  /work-schedules/bulk-assign   — 선택 일정 일괄 담당자 배정.
        대시보드 [담당자 배정]·점검 캘린더 [완료처리]·작업일정 [담당자 배정] 공통 경로.
        화면 별칭 assignee_id → assigned_user_id 흡수. work_assignments 동기화 재사용.

v1.2.2 (2026-08-17):
  [FIX] GET /work-schedules/{schedule_id} — 비-uuid 경로(/summary 등) 404 처리(22P02 500 방지).
v1.2.1 (2026-05-26): GET size 상한 100→500.
v1.2.0 (2026-04-13): GET 필터(is_assigned 등).
v1.1.0 (2026-04-07): PATCH /batch-update, POST /confirm/{factory_id}.

API:
  GET   /work-schedules                              전체 목록 (필터 지원)
  GET   /work-schedules/factory/{factory_id}         공장별 목록
  GET   /work-schedules/inspection-set/{id}          점검세트별 목록
  PATCH /work-schedules/batch-update                 일괄 업데이트
  POST  /work-schedules/bulk-assign                  일괄 담당자 배정  ← v1.2.3
  POST  /work-schedules/confirm/{factory_id}         검토 확정
  GET   /work-schedules/{schedule_id}                단건 조회
  PATCH /work-schedules/{schedule_id}                단건 갱신        ← v1.2.3
"""
import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone

from db.supabase_client import get_supabase

router = APIRouter(prefix="/work-schedules", tags=["work_schedules"])

VERSION = "1.2.4"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _apply_one_update(supabase, schedule_id: str, fields: dict, now: str) -> bool:
    """단일 work_schedules 행 갱신 + assigned_user_id 변경 시 work_assignments 동기화.

    fields 에 'assigned_user_id' 키가 있으면(None 포함) 배정 변경으로 본다(batch-update 와 동일).
    지원 필드: is_excluded · excluded_reason · custom_cycle · status_code · resolved_at · assigned_user_id.
    """
    payload: dict = {"updated_at": now}
    for k in ("is_excluded", "excluded_reason", "custom_cycle", "status_code", "resolved_at"):
        if fields.get(k) is not None:
            payload[k] = fields[k]
    assign_changed = "assigned_user_id" in fields
    if assign_changed:
        payload["assigned_user_id"] = fields["assigned_user_id"]

    res = supabase.table("work_schedules").update(payload).eq("id", schedule_id).execute()
    updated = bool(res.data)

    if assign_changed:
        auid = fields["assigned_user_id"]
        if auid:
            existing = supabase.table("work_assignments").select("id") \
                .eq("schedule_id", schedule_id).eq("status_code", "PENDING").limit(1).execute()
            if existing.data:
                supabase.table("work_assignments").update({
                    "assigned_user_id": auid, "updated_at": now,
                }).eq("id", existing.data[0]["id"]).execute()
            else:
                supabase.table("work_assignments").insert({
                    "schedule_id": schedule_id, "assigned_user_id": auid,
                    "scheduled_date": datetime.now().date().isoformat(),
                    "status_code": "PENDING", "created_at": now,
                }).execute()
        else:
            supabase.table("work_assignments").update({
                "status_code": "CANCELLED", "updated_at": now,
            }).eq("schedule_id", schedule_id).eq("status_code", "PENDING").execute()
    return updated


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


class SchedulePatchBody(BaseModel):
    assigned_user_id: Optional[str]  = None
    assignee_id:      Optional[str]  = None   # 화면 별칭 → assigned_user_id
    status_code:      Optional[str]  = None
    status:           Optional[str]  = None   # 화면 별칭 → status_code
    is_excluded:      Optional[bool] = None
    excluded_reason:  Optional[str]  = None
    custom_cycle:     Optional[str]  = None
    resolved_at:      Optional[str]  = None


class BulkAssignBody(BaseModel):
    ids:              List[str]
    assigned_user_id: Optional[str] = None
    assignee_id:      Optional[str] = None   # 화면 별칭


# ── 고정경로 먼저 선언 (/{schedule_id} 보다 앞에) ──────────────

@router.patch("/batch-update")
def batch_update_schedules(body: BatchUpdateBody):
    """
    v1.1.0: 복수 work_schedules 일괄 업데이트.
    - is_excluded / excluded_reason / custom_cycle 업데이트
    - assigned_user_id 있으면 work_assignments에도 반영(PENDING UPDATE/INSERT, null→CANCELLED)
    """
    supabase = get_supabase()
    now      = _now()
    updated  = 0

    for item in body.updates:
        fields: dict = {}
        if item.is_excluded is not None:
            fields["is_excluded"] = item.is_excluded
        if item.excluded_reason is not None:
            fields["excluded_reason"] = item.excluded_reason
        if item.custom_cycle is not None:
            fields["custom_cycle"] = item.custom_cycle
        if "assigned_user_id" in item.__fields_set__:
            fields["assigned_user_id"] = item.assigned_user_id
        if _apply_one_update(supabase, item.id, fields, now):
            updated += 1

    return {"status": "success", "data": {"updated": updated}}


@router.post("/bulk-assign")
def bulk_assign_schedules(body: BulkAssignBody):
    """v1.2.3: 선택 일정 일괄 담당자 배정(작업일정 §33). ids[] + assignee_id/assigned_user_id."""
    supabase = get_supabase()
    now = _now()
    auid = body.assigned_user_id if body.assigned_user_id is not None else body.assignee_id
    updated = 0
    for sid in body.ids:
        if not _is_uuid(sid):
            continue
        if _apply_one_update(supabase, sid, {"assigned_user_id": auid}, now):
            updated += 1
    return {"status": "success", "data": {"updated": updated}}


@router.post("/confirm/{factory_id}")
def confirm_schedules(factory_id: str, body: ConfirmBody):
    """
    v1.1.0: 검토 완료 후 스케줄 확정.
    1. is_excluded=FALSE → reviewed_at/reviewed_by, custom_cycle→cycle_code
    2. is_excluded=TRUE → status_code='EXCLUDED', is_active=FALSE
    """
    supabase = get_supabase()
    now      = _now()

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
        if row.get("custom_cycle"):
            update_payload["cycle_code"] = row["custom_cycle"]
        supabase.table("work_schedules").update(update_payload).eq("id", row["id"]).execute()
        confirmed += 1

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
        "data": {"confirmed": confirmed, "excluded": excluded, "created": 0},
    }


# ── 기존 CRUD ─────────────────────────────────────────────────

@router.get("")
def get_work_schedules(
    company_id:        Optional[str]  = Query(None, description="회사 ID 필터"),
    factory_id:        Optional[str]  = Query(None, description="시설 ID 필터"),
    status_code:       Optional[str]  = Query(None, description="상태코드 필터"),
    source_type:       Optional[str]  = Query(None, description="소스 타입 필터 (MANUAL/LAW_ENGINE)"),
    obligation_type:   Optional[str]  = Query(None, description="의무 구분 필터 (v1.2.4)"),
    is_assigned:       Optional[bool] = Query(None, description="배정 여부 필터. false=미배정, true=배정완료"),
    planned_date_from: Optional[str]  = Query(None, description="계획일 시작 YYYY-MM-DD (v1.2.4)"),
    planned_date_to:   Optional[str]  = Query(None, description="계획일 종료 YYYY-MM-DD (v1.2.4)"),
    page:              int            = Query(1, ge=1, description="페이지 번호"),
    size:              int            = Query(20, ge=1, le=500, description="페이지 크기"),
):
    """v1.2.4: 업무 일정 목록 조회. is_assigned·obligation_type·planned_date 범위 필터, size 상한 500."""
    supabase = get_supabase()
    q = supabase.table("work_schedules").select("*", count="exact")

    if company_id:      q = q.eq("company_id",      company_id)
    if factory_id:      q = q.eq("factory_id",      factory_id)
    if status_code:     q = q.eq("status_code",     status_code)
    if source_type:     q = q.eq("source_type",     source_type)
    if obligation_type: q = q.eq("obligation_type", obligation_type)

    if is_assigned is False:
        q = q.is_("assigned_user_id", "null")
    elif is_assigned is True:
        q = q.not_.is_("assigned_user_id", "null")

    # v1.2.4 (LEDGER ㉙): 화면이 보내던 계획일 범위 필터를 실제 적용
    if planned_date_from: q = q.gte("planned_date", planned_date_from)
    if planned_date_to:   q = q.lte("planned_date", planned_date_to)

    offset = (page - 1) * size
    result = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()

    total = result.count or 0
    return {
        "status": "success",
        "data": {
            "items":       result.data or [],
            "total":       total,
            "page":        page,
            "size":        size,
            "total_pages": (total + size - 1) // size if total else 0,
        },
    }


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
    # v1.2.2: 비-uuid 경로(/summary 등)가 catch-all 에 잡혀 500(22P02) 나던 것 방지.
    if not _is_uuid(schedule_id):
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다")
    supabase = get_supabase()
    result = (
        supabase.table("work_schedules")
        .select("*")
        .eq("id", schedule_id)
        .limit(1)
        .execute()
    )
    return result.data


@router.patch("/{schedule_id}")
def patch_work_schedule(schedule_id: str, body: SchedulePatchBody):
    """v1.2.3: 단건 갱신 — 담당자 배정(assignee_id/assigned_user_id)·상태(status_code) 등.

    대시보드 [담당자 배정](㉑)·점검 캘린더 [완료처리](㉘)·작업일정 [담당자 배정](㉝) 공통 경로.
    [주의] 완료처리의 "다음 회차 자동 생성"은 별도 기능이며 여기서 하지 않는다(상태만 저장).
    """
    if not _is_uuid(schedule_id):
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다")
    supabase = get_supabase()
    now = _now()

    fields: dict = {}
    if "assigned_user_id" in body.__fields_set__:
        fields["assigned_user_id"] = body.assigned_user_id
    elif "assignee_id" in body.__fields_set__:
        fields["assigned_user_id"] = body.assignee_id
    if body.status_code is not None:
        fields["status_code"] = body.status_code
    elif body.status is not None:
        fields["status_code"] = body.status
    for k in ("is_excluded", "excluded_reason", "custom_cycle", "resolved_at"):
        v = getattr(body, k)
        if v is not None:
            fields[k] = v

    if not fields:
        raise HTTPException(status_code=400, detail="변경할 필드가 없습니다")

    updated = _apply_one_update(supabase, schedule_id, fields, now)
    if not updated:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다")

    row = supabase.table("work_schedules").select("*").eq("id", schedule_id).limit(1).execute()
    return {"status": "success", "data": (row.data[0] if row.data else None)}
