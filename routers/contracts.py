# routers/contracts.py
from fastapi import APIRouter, HTTPException
from db.supabase_client import get_supabase

router = APIRouter(prefix="/contracts", tags=["contracts"])

@router.get("")
def get_contracts(company_id: str = None):
    supabase = get_supabase()
    query = supabase.table("contracts")\
        .select("*, companies(name)")\
        .eq("is_active", True)
    if company_id:
        query = query.eq("company_id", company_id)
    return query.order("created_at", desc=True).execute().data

@router.get("/{contract_id}")
def get_contract(contract_id: str):
    supabase = get_supabase()
    result = supabase.table("contracts")\
        .select("*, companies(name)")\
        .eq("id", contract_id)\
        .single()\
        .execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")
    return result.data

@router.post("")
def create_contract(body: dict):
    supabase = get_supabase()
    return supabase.table("contracts").insert(body).execute().data[0]

@router.patch("/{contract_id}")
def update_contract(contract_id: str, body: dict):
    supabase = get_supabase()
    return supabase.table("contracts").update(body).eq("id", contract_id).execute().data[0]

