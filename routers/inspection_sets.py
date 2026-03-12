from fastapi import APIRouter
from db.supabase_client import get_supabase

router = APIRouter(prefix="/inspection-sets", tags=["inspection_sets"])


# 점검세트 전체 목록
@router.get("")
def get_inspection_sets():
    supabase = get_supabase()

    result = (
        supabase.table("inspection_sets")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )

    return result.data


# 특정 회사의 점검세트
@router.get("/company/{company_id}")
def get_company_inspection_sets(company_id: str):
    supabase = get_supabase()

    result = (
        supabase.table("inspection_sets")
        .select("*")
        .eq("company_id", company_id)
        .order("created_at", desc=True)
        .execute()
    )

    return result.data


# 특정 공장의 점검세트
@router.get("/factory/{factory_id}")
def get_factory_inspection_sets(factory_id: str):
    supabase = get_supabase()

    result = (
        supabase.table("inspection_sets")
        .select("*")
        .eq("factory_id", factory_id)
        .order("created_at", desc=True)
        .execute()
    )

    return result.data


# 특정 설비세트의 점검세트
@router.get("/equipment-set/{equipment_set_id}")
def get_equipment_set_inspection_sets(equipment_set_id: str):
    supabase = get_supabase()

    result = (
        supabase.table("inspection_sets")
        .select("*")
        .eq("equipment_set_id", equipment_set_id)
        .order("created_at", desc=True)
        .execute()
    )

    return result.data


# 특정 점검세트 1건
@router.get("/{inspection_set_id}")
def get_inspection_set(inspection_set_id: str):
    supabase = get_supabase()

    result = (
        supabase.table("inspection_sets")
        .select("*")
        .eq("id", inspection_set_id)
        .limit(1)
        .execute()
    )

    return result.data
