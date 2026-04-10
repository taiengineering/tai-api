"""
TAI Agent 대행 서비스 라우터 — v1.0.0

엔드포인트:
  GET  /agent-service           전체 목록 (sector 필터 가능)
  GET  /agent-service/{id}      단건 조회
  PATCH /agent-service/{id}     단가/활성화 수정

DB 테이블: agent_service
  sector: construction | industrial | facility
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from pydantic import BaseModel
from utils.supabase_client import get_supabase
import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix="/agent-service", tags=["TAI Agent 대행"])


class AgentServicePatch(BaseModel):
    base_price:  Optional[int]  = None   # None = 협의
    price_unit:  Optional[str]  = None
    description: Optional[str]  = None
    is_active:   Optional[bool] = None
    sort_order:  Optional[int]  = None


@router.get("")
def list_agent_service(
    sector: Optional[str] = Query(None, description="construction | industrial | facility"),
):
    """TAI Agent 대행 서비스 목록. sector 파라미터로 필터링 가능."""
    sb = get_supabase()
    q = sb.table("agent_service").select("*").eq("is_active", True).order("sector").order("sort_order")
    if sector:
        q = q.eq("sector", sector)
    res = q.execute()
    data = res.data or []

    # sector별 그룹핑
    grouped = {}
    for row in data:
        s = row["sector"]
        if s not in grouped:
            grouped[s] = []
        grouped[s].append(row)

    return {
        "status": "success",
        "total":  len(data),
        "data":   data,
        "grouped": grouped,
    }


@router.get("/{service_id}")
def get_agent_service(service_id: int):
    sb  = get_supabase()
    res = sb.table("agent_service").select("*").eq("id", service_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="서비스를 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.patch("/{service_id}")
def patch_agent_service(service_id: int, body: AgentServicePatch):
    """단가·활성화·설명 수정."""
    sb      = get_supabase()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")

    res = sb.table("agent_service").update(updates).eq("id", service_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="서비스를 찾을 수 없습니다.")
    log.info(f"[AGENT_SERVICE] PATCH id={service_id} updates={updates}")
    return {"status": "success", "data": res.data[0]}
