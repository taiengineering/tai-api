from fastapi import APIRouter
from db.supabase_client import get_supabase

router = APIRouter(prefix="/areas", tags=["areas"])


# 구역 전체
@router.get("")
def get_areas():

    supabase = get_supabase()

    result = (
        supabase.table("areas")
        .select("*")
        .execute()
    )

    return result.data


# 특정 공장의 구역
@router.get("/factory/{factory_id}")
def get_factory_areas(factory_id: str):

    supabase = get_supabase()

    result = (
        supabase.table("areas")
        .select("*")
        .eq("factory_id", factory_id)
        .execute()
    )

    return result.data


# 특정 구역
@router.get("/{area_id}")
def get_area(area_id: str):

    supabase = get_supabase()

    result = (
        supabase.table("areas")
        .select("*")
        .eq("id", area_id)
        .limit(1)
        .execute()
    )

    return result.data
