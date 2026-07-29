"""관리자 감사로그 조회 (admin_ops_audit_logs).

Goal: G-ms5pdquz-9e76e5 (P3-4)
- 운영 처리 이력(NOTIFY_SEND, AUTOMATION_FIRE/APPROVE, 환불/크레딧/증빙 등)을 어드민에서 조회.
- 그동안 audit_svc가 기록만 하고 조회 API가 없어 어드민에서 처리 이력 추적 불가였던 갭 해소.
- 읽기 전용. Bearer 필수. 페이지네이션 + 필터(action/entity_type/entity_id/기간).
"""
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from db.supabase_client import get_supabase

router = APIRouter(prefix="/admin/audit-logs", tags=["관리 - 감사로그"])


def _require_bearer(authorization: Optional[str]) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")


@router.get("")
def list_audit_logs(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=200),
    action: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    _require_bearer(authorization)
    supabase = get_supabase()
    q = supabase.table("admin_ops_audit_logs").select("*", count="exact")
    if action:
        q = q.eq("action", action.strip())
    if entity_type:
        q = q.eq("entity_type", entity_type.strip())
    if entity_id:
        q = q.eq("entity_id", entity_id.strip())
    if from_date:
        q = q.gte("created_at", f"{from_date.strip()}T00:00:00+00:00")
    if to_date:
        q = q.lt("created_at", f"{to_date.strip()}T23:59:59.999999+00:00")

    offset = (page - 1) * size
    try:
        res = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"조회 실패: {e!s}") from e
    total = res.count or 0
    return {
        "status": "success",
        "data": {
            "items": res.data or [],
            "total": total,
            "page": page,
            "size": size,
            "total_pages": (total + size - 1) // size if total else 0,
        },
    }


@router.get("/actions")
def list_audit_actions(authorization: Optional[str] = Header(None)):
    """필터용 distinct action 목록(최근 1000건 기준 간이 집계)."""
    _require_bearer(authorization)
    supabase = get_supabase()
    res = (
        supabase.table("admin_ops_audit_logs")
        .select("action").order("created_at", desc=True).limit(1000).execute()
    )
    actions = sorted({r["action"] for r in (res.data or []) if r.get("action")})
    return {"status": "success", "data": actions}
