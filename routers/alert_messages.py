"""
알럿 메시지 관리 라우터 — v1.0.0
prefix: /alert-messages

API:
  GET    /alert-messages               목록 조회 (role 001 전용)
  GET    /alert-messages/codes         전체 코드:메시지 딕셔너리 (인증 불필요, 프론트 JS용)
  GET    /alert-messages/contexts      context 목록 (role 001 전용)
  POST   /alert-messages               신규 알럿 등록 (role 001 전용)
  PATCH  /alert-messages/{id}          수정 (role 001 전용)
  PATCH  /alert-messages/{id}/toggle   활성화 토글 (role 001 전용)
  DELETE /alert-messages/{id}          비활성화 처리 (role 001 전용)
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from db.supabase_client import get_supabase
from routers.auth import get_current_user

router = APIRouter(prefix="/alert-messages", tags=["알럿 메시지 관리"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────
# 모델
# ──────────────────────────────────────────────

class AlertCreate(BaseModel):
    alert_code: str
    platform:   str = "ALL"     # ALL / TADMIN / ADMIN
    category:   str = "INFO"    # ERROR / SUCCESS / INFO / CONFIRM / WARNING
    context:    str = "COMMON"
    message_ko: str
    message_en: Optional[str]       = None
    variables:  Optional[List[str]] = []
    example:    Optional[str]       = None
    is_active:  bool = True
    sort_order: int  = 0


class AlertPatch(BaseModel):
    message_ko: Optional[str]       = None
    message_en: Optional[str]       = None
    platform:   Optional[str]       = None
    category:   Optional[str]       = None
    context:    Optional[str]       = None
    variables:  Optional[List[str]] = None
    example:    Optional[str]       = None
    is_active:  Optional[bool]      = None
    sort_order: Optional[int]       = None


# ──────────────────────────────────────────────
# GET /alert-messages — 목록 조회 (role 001 전용)
# ──────────────────────────────────────────────

@router.get("")
def list_alerts(
    category:  Optional[str]  = Query(None),
    context:   Optional[str]  = Query(None),
    platform:  Optional[str]  = Query(None),
    is_active: Optional[bool] = Query(None),
    search:    Optional[str]  = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role_code") != "001":
        raise HTTPException(status_code=403, detail="관리자만 접근 가능합니다.")

    supabase = get_supabase()
    offset   = (page - 1) * size

    q = supabase.table("system_alert_messages").select("*", count="exact")
    if category:          q = q.eq("category", category)
    if context:           q = q.eq("context", context)
    if platform:          q = q.eq("platform", platform)
    if is_active is not None: q = q.eq("is_active", is_active)
    if search:            q = q.or_(f"alert_code.ilike.%{search}%,message_ko.ilike.%{search}%")

    q   = q.order("context").order("sort_order").order("alert_code")
    q   = q.range(offset, offset + size - 1)
    res = q.execute()

    return {
        "status": "success",
        "data": {
            "items": res.data or [],
            "total": res.count or 0,
            "page":  page,
            "size":  size,
        },
    }


# ──────────────────────────────────────────────
# GET /alert-messages/codes — 전체 코드:메시지 딕셔너리
# 인증 불필요 (프론트 JS에서 알럿 텍스트 동적 로드용)
# ──────────────────────────────────────────────

@router.get("/codes")
def list_alert_codes():
    """인증 불필요 — 프론트에서 alert_code → 메시지 텍스트 매핑 전체 조회."""
    supabase = get_supabase()
    res = supabase.table("system_alert_messages") \
        .select("alert_code, message_ko, message_en, variables, category") \
        .eq("is_active", True) \
        .execute()
    codes = {r["alert_code"]: r for r in (res.data or [])}
    return {"status": "success", "data": codes}


# ──────────────────────────────────────────────
# GET /alert-messages/contexts — context 목록
# ──────────────────────────────────────────────

@router.get("/contexts")
def list_contexts(current_user: dict = Depends(get_current_user)):
    if current_user.get("role_code") != "001":
        raise HTTPException(status_code=403, detail="관리자만 접근 가능합니다.")
    supabase  = get_supabase()
    res       = supabase.table("system_alert_messages").select("context").execute()
    contexts  = sorted(set(r["context"] for r in (res.data or []) if r.get("context")))
    return {"status": "success", "data": contexts}


# ──────────────────────────────────────────────
# POST /alert-messages — 신규 등록
# ──────────────────────────────────────────────

@router.post("")
def create_alert(
    body: AlertCreate,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role_code") != "001":
        raise HTTPException(status_code=403, detail="관리자만 접근 가능합니다.")

    supabase = get_supabase()

    # 중복 코드 검사
    dup = supabase.table("system_alert_messages") \
        .select("id").eq("alert_code", body.alert_code).execute()
    if dup.data:
        raise HTTPException(status_code=400, detail=f"이미 존재하는 alert_code: {body.alert_code}")

    now = _now()
    row = body.model_dump()
    row["created_at"] = now
    row["updated_at"] = now

    res = supabase.table("system_alert_messages").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="등록 실패")
    return {"status": "success", "data": res.data[0]}


# ──────────────────────────────────────────────
# PATCH /alert-messages/{id} — 수정
# ──────────────────────────────────────────────

@router.patch("/{alert_id}")
def update_alert(
    alert_id: str,
    body: AlertPatch,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role_code") != "001":
        raise HTTPException(status_code=403, detail="관리자만 접근 가능합니다.")

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")

    data["updated_at"] = _now()
    supabase = get_supabase()
    res = supabase.table("system_alert_messages").update(data).eq("id", alert_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="알럿을 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


# ──────────────────────────────────────────────
# PATCH /alert-messages/{id}/toggle — 활성화 토글
# ──────────────────────────────────────────────

@router.patch("/{alert_id}/toggle")
def toggle_alert(
    alert_id: str,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role_code") != "001":
        raise HTTPException(status_code=403, detail="관리자만 접근 가능합니다.")

    supabase = get_supabase()
    cur = supabase.table("system_alert_messages") \
        .select("is_active").eq("id", alert_id).limit(1).execute()
    if not cur.data:
        raise HTTPException(status_code=404, detail="알럿을 찾을 수 없습니다.")

    new_val = not cur.data[0]["is_active"]
    res = supabase.table("system_alert_messages").update({
        "is_active":  new_val,
        "updated_at": _now(),
    }).eq("id", alert_id).execute()
    return {"status": "success", "data": res.data[0] if res.data else {}}


# ──────────────────────────────────────────────
# DELETE /alert-messages/{id} — 비활성화 처리
# (물리 삭제 아님, is_active=False)
# ──────────────────────────────────────────────

@router.delete("/{alert_id}")
def delete_alert(
    alert_id: str,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role_code") != "001":
        raise HTTPException(status_code=403, detail="관리자만 접근 가능합니다.")

    supabase = get_supabase()
    res = supabase.table("system_alert_messages").update({
        "is_active":  False,
        "updated_at": _now(),
    }).eq("id", alert_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="알럿을 찾을 수 없습니다.")
    return {"status": "success", "message": "비활성화되었습니다."}
