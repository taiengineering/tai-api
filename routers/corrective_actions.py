"""
이창 보고서 조치사항(Corrective Actions) 관리 라우터 — v1.0.0

corrective_actions 테이블 사용

API:
  GET    /corrective-actions                 목록 조회 (factory_id/status/severity 필터)
  POST   /corrective-actions                 등록
  PATCH  /corrective-actions/{id}            수정 (status, action_result, completed_at)
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from db.supabase_client import get_supabase

router = APIRouter(prefix="/corrective-actions", tags=["이창보고서"])

VERSION = "1.0.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Pydantic 모델 ─────────────────────────────────────────────

class CorrectiveActionCreate(BaseModel):
    factory_id:   Optional[str] = None
    company_id:   Optional[str] = None
    description:  str
    location:     Optional[str] = None
    asset_name:   Optional[str] = None
    severity:     Optional[str] = "MEDIUM"   # HIGH / MEDIUM / LOW
    assignee_id:  Optional[str] = None
    due_date:     Optional[str] = None       # YYYY-MM-DD
    action_plan:  Optional[str] = None
    status:       Optional[str] = "OPEN"     # OPEN / IN_PROGRESS / COMPLETED / CANCELLED
    created_by:   Optional[str] = None


class CorrectiveActionUpdate(BaseModel):
    status:         Optional[str] = None
    action_result:  Optional[str] = None
    action_plan:    Optional[str] = None
    assignee_id:    Optional[str] = None
    due_date:       Optional[str] = None
    severity:       Optional[str] = None
    location:       Optional[str] = None
    asset_name:     Optional[str] = None
    completed_at:   Optional[str] = None     # ISO datetime (status=COMPLETED 시 자동세팅 가능)


# ── GET /corrective-actions ──────────────────────────────

@router.get("")
def list_corrective_actions(
    factory_id:  Optional[str] = Query(None),
    company_id:  Optional[str] = Query(None),
    status:      Optional[str] = Query(None),
    severity:    Optional[str] = Query(None),
    assignee_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(200, ge=1, le=500),
):
    """
    이창 보고서 목록 조회.
    필터: factory_id, company_id, status (OPEN/IN_PROGRESS/COMPLETED/CANCELLED),
            severity (HIGH/MEDIUM/LOW), assignee_id
    """
    supabase = get_supabase()
    q = supabase.table("corrective_actions").select("*", count="exact")

    if factory_id:  q = q.eq("factory_id",  factory_id)
    if company_id:  q = q.eq("company_id",  company_id)
    if status:      q = q.eq("status",       status)
    if severity:    q = q.eq("severity",     severity)
    if assignee_id: q = q.eq("assignee_id",  assignee_id)

    offset = (page - 1) * size
    res    = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    total  = res.count or 0

    return {
        "status": "success",
        "data": {
            "items":       res.data or [],
            "total":       total,
            "page":        page,
            "size":        size,
            "total_pages": (total + size - 1) // size if total else 0,
        },
    }


# ── POST /corrective-actions ──────────────────────────────

@router.post("")
def create_corrective_action(body: CorrectiveActionCreate):
    """이창 발행 등록."""
    supabase = get_supabase()
    now = _now()

    row = {
        "factory_id":  body.factory_id,
        "company_id":  body.company_id,
        "description": body.description,
        "location":    body.location,
        "asset_name":  body.asset_name,
        "severity":    body.severity or "MEDIUM",
        "assignee_id": body.assignee_id,
        "due_date":    body.due_date,
        "action_plan": body.action_plan,
        "status":      body.status or "OPEN",
        "created_by":  body.created_by,
        "created_at":  now,
        "updated_at":  now,
    }

    res = supabase.table("corrective_actions").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="이창 발행 등록 실패")

    return {
        "status":  "success",
        "message": "이창이 등록되었습니다.",
        "data":    res.data[0],
    }


# ── PATCH /corrective-actions/{id} ───────────────────────

@router.patch("/{action_id}")
def update_corrective_action(action_id: str, body: CorrectiveActionUpdate):
    """
    이창 수정.
    - status=COMPLETED 시 completed_at 자동 세팅
    - 수정할 필드만 업데이트 (None 값 스킵)
    """
    supabase = get_supabase()
    now = _now()

    # 존재 확인
    chk = supabase.table("corrective_actions").select("id").eq("id", action_id).limit(1).execute()
    if not chk.data:
        raise HTTPException(status_code=404, detail="이창을 찾을 수 없습니다.")

    payload: dict = {"updated_at": now}

    if body.status is not None:
        payload["status"] = body.status
        # COMPLETED 시 completed_at 자동 세팅 (body에 직접 입력 없으면)
        if body.status == "COMPLETED" and body.completed_at is None:
            payload["completed_at"] = now

    if body.action_result is not None: payload["action_result"] = body.action_result
    if body.action_plan   is not None: payload["action_plan"]   = body.action_plan
    if body.assignee_id   is not None: payload["assignee_id"]   = body.assignee_id
    if body.due_date      is not None: payload["due_date"]      = body.due_date
    if body.severity      is not None: payload["severity"]      = body.severity
    if body.location      is not None: payload["location"]      = body.location
    if body.asset_name    is not None: payload["asset_name"]    = body.asset_name
    if body.completed_at  is not None: payload["completed_at"]  = body.completed_at

    res = supabase.table("corrective_actions").update(payload).eq("id", action_id).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="수정 실패")

    return {
        "status":  "success",
        "message": "이창이 수정되었습니다.",
        "data":    res.data[0],
    }
