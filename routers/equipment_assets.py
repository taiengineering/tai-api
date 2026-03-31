from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from db.supabase_client import get_supabase

router = APIRouter(prefix="/equipment-assets", tags=["equipment_assets"])


# ── 모델 ──────────────────────────────────────
class EquipmentAssetCreate(BaseModel):
    factory_id:           str
    asset_name:           str
    equipment_type_code:  Optional[str] = None   # system_codes.equipment_type
    equipment_category:   Optional[str] = None   # 자유입력 카테고리명
    asset_code:           Optional[str] = None
    description:          Optional[str] = None
    quantity:             Optional[int] = 1
    capacity_value:       Optional[float] = None
    capacity_unit:        Optional[str] = None
    manufacturer:         Optional[str] = None
    install_year:         Optional[int] = None
    manufacture_year:     Optional[int] = None
    location_detail:      Optional[str] = None
    is_legal_target:      Optional[bool] = True
    is_operating:         Optional[bool] = True
    equipment_model_id:   Optional[str] = None   # engine_equipment model FK
    area_id:              Optional[str] = None
    ksic_code:            Optional[str] = None


class EquipmentAssetUpdate(BaseModel):
    asset_name:           Optional[str] = None
    equipment_type_code:  Optional[str] = None
    equipment_category:   Optional[str] = None
    asset_code:           Optional[str] = None
    description:          Optional[str] = None
    quantity:             Optional[int] = None
    capacity_value:       Optional[float] = None
    capacity_unit:        Optional[str] = None
    manufacturer:         Optional[str] = None
    install_year:         Optional[int] = None
    location_detail:      Optional[str] = None
    is_legal_target:      Optional[bool] = None
    is_operating:         Optional[bool] = None
    equipment_model_id:   Optional[str] = None
    last_inspection_date: Optional[str] = None
    next_inspection_date: Optional[str] = None


# ── 목록 조회 ─────────────────────────────────
@router.get("")
def get_assets(
    factory_id:           Optional[str] = Query(None),
    area_id:              Optional[str] = Query(None),
    equipment_type_code:  Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    query = supabase.table("equipment_assets").select(
        "id, factory_id, area_id, asset_name, asset_code, "
        "equipment_type_code, equipment_category, "
        "quantity, capacity_value, capacity_unit, "
        "install_year, manufacturer, equipment_model_id, "
        "last_inspection_date, next_inspection_date, "
        "is_legal_target, is_operating, description, "
        "location_detail, created_at",
        count="exact"
    )
    if factory_id:
        query = query.eq("factory_id", factory_id)
    if area_id:
        query = query.eq("area_id", area_id)
    if equipment_type_code:
        query = query.eq("equipment_type_code", equipment_type_code)

    offset = (page - 1) * size
    res = query.order("created_at", desc=True)\
               .range(offset, offset + size - 1).execute()

    return {
        "status": "success",
        "data": {
            "items": res.data,
            "total": res.count or 0,
            "page":  page,
            "size":  size,
        }
    }


# ── 단건 조회 ─────────────────────────────────
@router.get("/area/{area_id}")
def get_area_assets(area_id: str):
    supabase = get_supabase()
    result = supabase.table("equipment_assets")\
        .select("*").eq("area_id", area_id).execute()
    return {"status": "success", "data": result.data}


@router.get("/{asset_id}")
def get_asset(asset_id: str):
    supabase = get_supabase()
    result = supabase.table("equipment_assets")\
        .select("*").eq("id", asset_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다")
    return {"status": "success", "data": result.data}


# ── 설비 등록 (수동 포함) ──────────────────────
@router.post("")
def create_asset(body: EquipmentAssetCreate):
    supabase = get_supabase()

    if not body.asset_name.strip():
        raise HTTPException(status_code=422, detail="asset_name은 필수입니다.")

    # company_id 자동 조회
    fac = supabase.table("factories").select("company_id")\
        .eq("id", body.factory_id).single().execute()
    company_id = (fac.data or {}).get("company_id")

    insert_data = {
        "factory_id":          body.factory_id,
        "asset_name":          body.asset_name.strip(),
        "asset_code":          body.asset_code,
        "equipment_type_code": body.equipment_type_code,
        "equipment_category":  body.equipment_category,
        "description":         body.description,
        "quantity":            body.quantity or 1,
        "capacity_value":      body.capacity_value,
        "capacity_unit":       body.capacity_unit,
        "manufacturer":        body.manufacturer,
        "install_year":        body.install_year,
        "manufacture_year":    body.manufacture_year,
        "location_detail":     body.location_detail,
        "is_legal_target":     body.is_legal_target if body.is_legal_target is not None else True,
        "is_operating":        body.is_operating if body.is_operating is not None else True,
        "equipment_model_id":  body.equipment_model_id,
        "area_id":             body.area_id,
        "ksic_code":           body.ksic_code,
    }
    # None 필드 제거
    insert_data = {k: v for k, v in insert_data.items() if v is not None}

    res = supabase.table("equipment_assets").insert(insert_data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="설비 등록 실패")

    return {
        "status":  "success",
        "message": f"설비 '{body.asset_name}' 등록 완료",
        "data":    res.data[0],
    }


# ── 설비 수정 ──────────────────────────────────
@router.patch("/{asset_id}")
def update_asset(asset_id: str, body: EquipmentAssetUpdate):
    supabase = get_supabase()
    update_data = {k: v for k, v in body.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=422, detail="수정할 내용이 없습니다.")

    res = supabase.table("equipment_assets").update(update_data)\
        .eq("id", asset_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다.")

    return {"status": "success", "message": "수정 완료", "data": res.data[0]}


# ── 설비 삭제 (soft) ───────────────────────────
@router.delete("/{asset_id}")
def delete_asset(asset_id: str):
    supabase = get_supabase()
    # is_operating=False로 비활성화 (실제 삭제 대신 soft)
    res = supabase.table("equipment_assets").update({"is_operating": False})\
        .eq("id", asset_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다.")
    return {"status": "success", "message": "설비가 비활성화됐습니다."}
