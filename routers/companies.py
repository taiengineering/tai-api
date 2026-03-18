# routers/companies.py
from fastapi import APIRouter, HTTPException
from db.supabase_client import get_supabase

router = APIRouter(prefix="/companies", tags=["companies"])

@router.get("")
def get_companies():
    supabase = get_supabase()
    return supabase.table("companies").select("*").eq("is_active", True).order("created_at", desc=True).execute().data

@router.get("/{company_id}")
def get_company(company_id: str):
    supabase = get_supabase()
    result = supabase.table("companies").select("*").eq("id", company_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다")
    return result.data

@router.post("")
def create_company(body: dict):
    supabase = get_supabase()
    return supabase.table("companies").insert(body).execute().data[0]

@router.patch("/{company_id}")
def update_company(company_id: str, body: dict):
    supabase = get_supabase()
    return supabase.table("companies").update(body).eq("id", company_id).execute().data[0]

@router.delete("/{company_id}")
def delete_company(company_id: str):
    supabase = get_supabase()
    supabase.table("companies").update({"is_active": False}).eq("id", company_id).execute()
    return {"message": "삭제됐습니다"}
