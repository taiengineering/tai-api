from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from db.supabase_client import get_supabase

router = APIRouter(prefix="/equipment-assets", tags=["equipment_assets"])


@router.get("")
def get_assets(
    factory_id: Optional[str] = Query(None, description="시설 ID"),
    area_id: Optional[str] = Query(None, description="구역 ID"),
    equipment_type_code: Optional[str] = Query(None, description="설비유형 코드"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    query = supabase.table("equipment_assets").select(
        "id, factory_id, area_id, asset_name, equipment_type_code, "
        "quantity, install_year, last_inspection_date, next_inspection_date, "
        "manufacturer, model_name, serial_number, status_code, is_active, "
        "created_at, updated_at",
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
            "page": page,
            "size": size,
        }
    }


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
