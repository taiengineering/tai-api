from fastapi import APIRouter
from db.supabase_client import get_supabase

router = APIRouter(prefix="/equipment-assets", tags=["equipment_assets"])


# 설비 전체
@router.get("")
def get_assets():

    supabase = get_supabase()

    result = (
        supabase.table("equipment_assets")
        .select("*")
        .execute()
    )

    return result.data


# 특정 구역 설비
@router.get("/area/{area_id}")
def get_area_assets(area_id: str):

    supabase = get_supabase()

    result = (
        supabase.table("equipment_assets")
        .select("*")
        .eq("area_id", area_id)
        .execute()
    )

    return result.data


# 특정 설비
@router.get("/{asset_id}")
def get_asset(asset_id: str):

    supabase = get_supabase()

    result = (
        supabase.table("equipment_assets")
        .select("*")
        .eq("id", asset_id)
        .limit(1)
        .execute()
    )

    return result.data
