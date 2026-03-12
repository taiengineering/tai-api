from fastapi import APIRouter
from db.supabase_client import get_supabase

router = APIRouter(prefix="/buildings", tags=["buildings"])


# 건물 전체 목록
@router.get("")
def get_buildings():
    supabase = get_supabase()

    result = (
        supabase.table("buildings")
        .select("*")
        .execute()
    )

    return result.data


# 특정 공장의 건물 목록
@router.get("/factory/{factory_id}")
def get_factory_buildings(factory_id: str):
    supabase = get_supabase()

    result = (
        supabase.table("buildings")
        .select("*")
        .eq("factory_id", factory_id)
        .execute()
    )

    return result.data


# 특정 건물 1건
@router.get("/{building_id}")
def get_building(building_id: str):
    supabase = get_supabase()

    result = (
        supabase.table("buildings")
        .select("*")
        .eq("id", building_id)
        .limit(1)
        .execute()
    )

    return result.data
