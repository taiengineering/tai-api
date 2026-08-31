"""
routers/connection_commission.py — v1.0.0
prefix: /connection-commission

엔드포인트:
  GET   /connection-commission                    전체 목록 (service_type 필터)
  PATCH /connection-commission/{id}               수수료 수정
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from db.supabase_client import get_supabase
from services.time import now_kst, serialize_business_datetime

router = APIRouter(prefix="/connection-commission", tags=["연결수수료"])


class CommissionUpdate(BaseModel):
    grade_label:       Optional[str]   = None
    amount_from:       Optional[int]   = None
    amount_to:         Optional[int]   = None
    commission_type:   Optional[str]   = None
    commission_value:  Optional[float] = None
    commission_note:   Optional[str]   = None
    includes_contract: Optional[bool]  = None
    includes_escrow:   Optional[bool]  = None
    is_confirmed:      Optional[bool]  = None
    description:       Optional[str]   = None


@router.get("")
def list_commissions(
    service_type: Optional[str] = Query(None, description="appointment | repair"),
):
    sb = get_supabase()
    q = sb.table("connection_commission").select("*")
    if service_type:
        q = q.eq("service_type", service_type)
    res = q.order("service_type").order("sort_order").execute()
    return {"status": "success", "data": res.data}


@router.patch("/{commission_id}")
def update_commission(commission_id: int, body: CommissionUpdate):
    sb = get_supabase()

    old = sb.table("connection_commission").select("*").eq("id", commission_id).single().execute()
    if not old.data:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다")

    update_data = {k: v for k, v in body.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="변경할 항목이 없습니다")

    update_data["updated_at"] = serialize_business_datetime(now_kst())
    res = sb.table("connection_commission").update(update_data).eq("id", commission_id).execute()
    return {"status": "success", "data": res.data[0] if res.data else None}
