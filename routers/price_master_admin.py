# routers/price_master_admin.py — 통합 가격 테이블(price_master) 관리 API
# v1.0.0 (2026-06-05): price-setting 페이지용 CRUD.
#   price_master(가격 본체) + price_service_feature(노출 서비스 항목) 관리.
#   가격 카드(public_pricing)가 참조하는 단일 SSOT를 이 API로 입력/수정/생성한다.
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db.supabase_client import get_supabase

router = APIRouter(prefix="/price-master", tags=["가격 통합관리"])


# ── 모델 ──────────────────────────────────────────────────────

class PriceMasterUpsert(BaseModel):
    service_type: Optional[str] = None      # DIAGNOSIS / SAAS / ...
    sector: Optional[str] = None            # BUILDING / INDUSTRY / CONSTRUCTION / COMMON
    tier_code: Optional[str] = None
    criteria_type: Optional[str] = None     # FLOOR_AREA / WORKER_COUNT / CONTRACT_AMOUNT / FLAT
    criteria_min: Optional[float] = None
    criteria_max: Optional[float] = None
    amount: Optional[int] = None
    vat_included: Optional[bool] = None
    vat_rate: Optional[float] = None
    billing_unit: Optional[str] = None      # ONCE / MONTHLY / ANNUAL
    display_name: Optional[str] = None
    sub_label: Optional[str] = None
    icon: Optional[str] = None
    is_recommended: Optional[bool] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class FeatureUpsert(BaseModel):
    feature_text: str
    feature_type: Optional[str] = "INCLUDE"
    icon: Optional[str] = None
    sort_order: Optional[int] = 0
    is_active: Optional[bool] = True


# ── price_master CRUD ────────────────────────────────────────

@router.get("")
def list_prices(service_type: str = None, sector: str = None, is_active: bool = None):
    sb = get_supabase()
    q = sb.table("price_master").select("*")
    if service_type:
        q = q.eq("service_type", service_type.upper())
    if sector:
        q = q.eq("sector", sector.upper())
    if is_active is not None:
        q = q.eq("is_active", is_active)
    rows = q.order("service_type").order("sort_order").execute().data or []

    ids = [r["id"] for r in rows]
    feat_map: dict = {}
    if ids:
        feats = (
            sb.table("price_service_feature").select("*")
            .in_("price_id", ids).order("sort_order").execute().data or []
        )
        for f in feats:
            feat_map.setdefault(f["price_id"], []).append(f)
    for r in rows:
        r["features"] = feat_map.get(r["id"], [])
    return {"status": "success", "data": rows}


@router.get("/{price_id}")
def get_price(price_id: str):
    sb = get_supabase()
    res = sb.table("price_master").select("*").eq("id", price_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="가격 항목을 찾을 수 없습니다")
    feats = (
        sb.table("price_service_feature").select("*")
        .eq("price_id", price_id).order("sort_order").execute().data or []
    )
    data = res.data
    data["features"] = feats
    return {"status": "success", "data": data}


@router.post("")
def create_price(body: PriceMasterUpsert):
    """신규 가격 항목 생성."""
    sb = get_supabase()
    row = {k: v for k, v in body.dict().items() if v is not None}
    for req in ("service_type", "tier_code"):
        if not row.get(req):
            raise HTTPException(status_code=400, detail=f"{req}는 필수입니다")
    row["service_type"] = row["service_type"].upper()
    if row.get("sector"):
        row["sector"] = row["sector"].upper()
    res = sb.table("price_master").insert(row).execute()
    return {"status": "success", "data": res.data[0] if res.data else None}


@router.patch("/{price_id}")
def update_price(price_id: str, body: PriceMasterUpsert):
    sb = get_supabase()
    old = sb.table("price_master").select("*").eq("id", price_id).single().execute()
    if not old.data:
        raise HTTPException(status_code=404, detail="가격 항목을 찾을 수 없습니다")
    update = {k: v for k, v in body.dict().items() if v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="변경할 항목이 없습니다")
    if update.get("service_type"):
        update["service_type"] = update["service_type"].upper()
    if update.get("sector"):
        update["sector"] = update["sector"].upper()
    update["updated_at"] = datetime.now().isoformat()
    res = sb.table("price_master").update(update).eq("id", price_id).execute()
    return {"status": "success", "data": res.data[0] if res.data else None}


@router.delete("/{price_id}")
def deactivate_price(price_id: str):
    """비활성화(soft). 물리 삭제 안 함."""
    sb = get_supabase()
    res = (
        sb.table("price_master")
        .update({"is_active": False, "updated_at": datetime.now().isoformat()})
        .eq("id", price_id).execute()
    )
    return {"status": "success", "data": res.data[0] if res.data else None}


# ── feature CRUD ─────────────────────────────────────────────

@router.put("/{price_id}/features")
def replace_features(price_id: str, items: List[FeatureUpsert]):
    """해당 가격의 노출 서비스 항목 전체 교체."""
    sb = get_supabase()
    owner = sb.table("price_master").select("id").eq("id", price_id).single().execute()
    if not owner.data:
        raise HTTPException(status_code=404, detail="가격 항목을 찾을 수 없습니다")
    sb.table("price_service_feature").delete().eq("price_id", price_id).execute()
    rows = []
    for i, it in enumerate(items):
        rows.append({
            "price_id": price_id,
            "feature_text": it.feature_text,
            "feature_type": it.feature_type or "INCLUDE",
            "icon": it.icon,
            "sort_order": it.sort_order if it.sort_order is not None else i,
            "is_active": it.is_active if it.is_active is not None else True,
        })
    data = []
    if rows:
        data = sb.table("price_service_feature").insert(rows).execute().data or []
    return {"status": "success", "data": data, "count": len(data)}
