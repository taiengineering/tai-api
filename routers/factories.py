# routers/factories.py
from fastapi import APIRouter, HTTPException
from db.supabase_client import get_supabase

router = APIRouter(prefix="/factories", tags=["factories"])

@router.get("")
def get_factories(company_id: str = None):
    supabase = get_supabase()
    query = supabase.table("factories").select("*, companies(name)").eq("is_active", True)
    if company_id:
        query = query.eq("company_id", company_id)
    return query.order("created_at", desc=True).execute().data

@router.get("/{factory_id}")
def get_factory(factory_id: str):
    supabase = get_supabase()
    result = supabase.table("factories")\
        .select("*, companies(name)")\
        .eq("id", factory_id)\
        .single()\
        .execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="사업장을 찾을 수 없습니다")
    return result.data

@router.post("")
def create_factory(body: dict):
    supabase = get_supabase()
    return supabase.table("factories").insert(body).execute().data[0]

@router.patch("/{factory_id}")
def update_factory(factory_id: str, body: dict):
    supabase = get_supabase()
    return supabase.table("factories").update(body).eq("id", factory_id).execute().data[0]

@router.delete("/{factory_id}")
def delete_factory(factory_id: str):
    supabase = get_supabase()
    supabase.table("factories").update({"is_active": False}).eq("id", factory_id).execute()
    return {"message": "삭제됐습니다"}

# 사업장 조건값 관리 (법령 판단용)
@router.get("/{factory_id}/conditions")
def get_factory_conditions(factory_id: str):
    supabase = get_supabase()
    return supabase.table("facility_condition")\
        .select("*")\
        .eq("factory_id", factory_id)\
        .execute().data

@router.post("/{factory_id}/conditions")
def upsert_factory_conditions(factory_id: str, body: list):
    """조건값 일괄 저장 (법령 판단용)"""
    supabase = get_supabase()
    # 기존 조건 삭제 후 재삽입
    supabase.table("facility_condition").delete().eq("factory_id", factory_id).execute()
    for condition in body:
        condition["factory_id"] = factory_id
    return supabase.table("facility_condition").insert(body).execute().data
