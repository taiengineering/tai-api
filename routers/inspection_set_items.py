"""쿼리형 점검세트 항목 조회 — GET /inspection-set-items?inspection_set_id= (LEDGER §3).

경로형 GET /inspection-sets/{id}/items 는 #141 로 신설(작업자앱 inspect.html 대응).
safe 세트상세가 쿼리형(/inspection-set-items)을 부르는 경우를 위해, 동일 서비스·소유가드를
쿼리형으로도 노출한다. 로직은 경로형과 100% 동일(svc.get_set_items + _ensure_set_own) —
가법적이며, safe 가 경로형을 부르더라도 무해하다.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from routers.inspection_sets import _ensure_set_own, _call
from services import inspection_sets_svc as svc

router = APIRouter(prefix="/inspection-set-items", tags=["inspection_sets"])


@router.get("")
def list_inspection_set_items(
    inspection_set_id: Optional[str] = Query(None, description="점검세트 ID"),
    set_id: Optional[str] = Query(None, description="inspection_set_id 화면 별칭"),
    current: dict = Depends(get_current_user),
):
    """점검세트 항목 목록(쿼리형). 경로형 GET /inspection-sets/{id}/items 와 동일 결과."""
    sid = inspection_set_id or set_id
    if not sid:
        raise HTTPException(status_code=400, detail="inspection_set_id 파라미터가 필요합니다.")
    sb = get_supabase()
    _ensure_set_own(sb, sid, current)   # P13: 세트 소유확인(없거나 타사면 404)
    return _call(svc.get_set_items, sid)
