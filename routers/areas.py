# routers/areas.py
from fastapi import APIRouter, HTTPException
from db.supabase_client import get_supabase

router = APIRouter(prefix="/areas", tags=["areas"])

@router.get("")
def get_areas(factory_id: str = None, building_id: str = None):
    supabase = get_supabase()
    query = supabase.table("areas").select("*").eq("is_active", True)
    if factory_id:
        query = query.eq("factory_id", factory_id)
    if building_id:
        query = query.eq("building_id", building_id)
    return query.order("created_at", desc=True).execute().data

@router.get("/{area_id}")
def get_area(area_id: str):
    supabase = get_supabase()
    result = supabase.table("areas").select("*").eq("id", area_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="구역을 찾을 수 없습니다")
    return result.data

@router.post("")
def create_area(body: dict):
    supabase = get_supabase()
    return supabase.table("areas").insert(body).execute().data[0]

@router.patch("/{area_id}")
def update_area(area_id: str, body: dict):
    supabase = get_supabase()
    return supabase.table("areas").update(body).eq("id", area_id).execute().data[0]

@router.delete("/{area_id}")
def delete_area(area_id: str):
    supabase = get_supabase()
    supabase.table("areas").update({"is_active": False}).eq("id", area_id).execute()
    return {"message": "삭제됐습니다"}
