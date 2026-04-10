"""
routers/price_policy.py — v1.0.0
prefix: /price-policy

엔드포인트:
  GET  /price-policy                    전체 목록 (category/sector 필터)
  PATCH /price-policy/{id}              가격·라벨·설명 수정
  GET  /price-policy/summary            요약 (어드민 대시보드용)
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from db.supabase_client import get_supabase

router = APIRouter(prefix="/price-policy", tags=["가격정책"])


class PricePolicyUpdate(BaseModel):
    label:         Optional[str] = None
    price:         Optional[int] = None
    price_display: Optional[str] = None
    description:   Optional[str] = None
    is_active:     Optional[bool] = None
    sort_order:    Optional[int] = None


@router.get("")
def list_price_policy(
    category: Optional[str] = Query(None, description="diagnosis | saas"),
    sector:   Optional[str] = Query(None, description="construction | facility | industrial"),
):
    sb = get_supabase()
    q = sb.table("price_policy").select("*")
    if category:
        q = q.eq("category", category)
    if sector:
        q = q.eq("sector", sector)
    res = q.order("category").order("sector").order("sort_order").execute()
    return {"status": "success", "data": res.data}


@router.patch("/{policy_id}")
def update_price_policy(policy_id: int, body: PricePolicyUpdate):
    sb = get_supabase()

    old = sb.table("price_policy").select("*").eq("id", policy_id).single().execute()
    if not old.data:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다")

    update_data = {k: v for k, v in body.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="변경할 항목이 없습니다")

    update_data["updated_at"] = datetime.now().isoformat()
    res = sb.table("price_policy").update(update_data).eq("id", policy_id).execute()
    return {"status": "success", "data": res.data[0] if res.data else None}


@router.get("/summary")
def get_summary():
    """어드민 대시보드용 — 섹터×카테고리별 최신 가격 요약"""
    sb = get_supabase()
    res = sb.table("price_policy").select("*").eq("is_active", True).order("category").order("sector").order("sort_order").execute()
    return {"status": "success", "data": res.data}
