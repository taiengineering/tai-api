from fastapi import APIRouter
from db.supabase_client import get_supabase

router = APIRouter(prefix="/factories", tags=["factories"])


# 공장 전체 목록
@router.get("")
def get_factories():

    supabase = get_supabase()

    result = (
        supabase.table("factories")
        .select("*")
        .execute()
    )

    return result.data


# 특정 회사의 공장 조회
@router.get("/company/{company_id}")
def get_company_factories(company_id: str):

    supabase = get_supabase()

    result = (
        supabase.table("factories")
        .select("*")
        .eq("company_id", company_id)
        .execute()
    )

    return result.data


# 특정 공장 조회
@router.get("/{factory_id}")
def get_factory(factory_id: str):

    supabase = get_supabase()

    result = (
        supabase.table("factories")
        .select("*")
        .eq("id", factory_id)
        .limit(1)
        .execute()
    )

    return result.data
