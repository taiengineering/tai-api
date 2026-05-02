"""
routers/product_pricing.py — v1.0.0
prefix: /products/pricing

공개 API (인증 불필요):
  GET  /products/pricing          전체 요금제 목록
  GET  /products/pricing/{code}   특정 요금제 상세

어드민 API:
  PATCH /products/pricing/{id}    요금제 수정 (가격·기능·활성화)
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from db.supabase_client import get_supabase

router = APIRouter(prefix="/products/pricing", tags=["요금제"])


class FeatureItem(BaseModel):
    text: str
    included: bool = True


class PricingUpdate(BaseModel):
    plan_name:     Optional[str]          = None
    plan_name_en:  Optional[str]          = None
    description:   Optional[str]          = None
    price_monthly: Optional[int]          = None
    price_display: Optional[str]          = None
    is_active:     Optional[bool]         = None
    is_featured:   Optional[bool]         = None
    sort_order:    Optional[int]          = None
    badge_text:    Optional[str]          = None
    cta_text:      Optional[str]          = None
    features:      Optional[List[FeatureItem]] = None


# ── 공개 목록 (taieng.co.kr, pricing.html 에서 사용) ─────
@router.get("")
def list_pricing():
    sb = get_supabase()
    res = sb.table("product_pricing") \
        .select("*") \
        .eq("is_active", True) \
        .order("sort_order") \
        .execute()
    return {"status": "success", "data": res.data}


@router.get("/{plan_code}")
def get_pricing(plan_code: str):
    sb = get_supabase()
    res = sb.table("product_pricing") \
        .select("*") \
        .ilike("plan_code", plan_code) \
        .single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="요금제를 찾을 수 없습니다")
    return {"status": "success", "data": res.data}


# ── 어드민 수정 ──────────────────────────────────────────────
@router.patch("/{plan_id}")
def update_pricing(plan_id: int, body: PricingUpdate):
    sb = get_supabase()

    old = sb.table("product_pricing").select("*").eq("id", plan_id).single().execute()
    if not old.data:
        raise HTTPException(status_code=404, detail="요금제를 찾을 수 없습니다")

    update_data = {k: v for k, v in body.dict().items() if v is not None}
    if body.features is not None:
        update_data["features"] = [f.dict() for f in body.features]
    if not update_data:
        raise HTTPException(status_code=400, detail="변경할 항목이 없습니다")

    update_data["updated_at"] = datetime.now().isoformat()

    res = sb.table("product_pricing").update(update_data).eq("id", plan_id).execute()
    return {"status": "success", "data": res.data[0] if res.data else None}


# ── 어드민 전체 목록 (비활성 포함) ──────────────────────────
@router.get("/admin/all")
def list_pricing_all():
    sb = get_supabase()
    res = sb.table("product_pricing").select("*").order("sort_order").execute()
    return {"status": "success", "data": res.data}
