# routers/buildings.py
from fastapi import APIRouter, HTTPException
from db.supabase_client import get_supabase

router = APIRouter(prefix="/buildings", tags=["buildings"])

@router.get("")
def get_buildings(factory_id: str = None):
    supabase = get_supabase()
    query = supabase.table("buildings").select("*").eq("is_active", True)
    if factory_id:
        query = query.eq("factory_id", factory_id)
    return query.order("created_at", desc=True).execute().data

@router.get("/{building_id}")
def get_building(building_id: str):
    supabase = get_supabase()
    result = supabase.table("buildings").select("*").eq("id", building_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="건물을 찾을 수 없습니다")
    return result.data

@router.post("")
def create_building(body: dict):
    supabase = get_supabase()
    return supabase.table("buildings").insert(body).execute().data[0]

@router.patch("/{building_id}")
def update_building(building_id: str, body: dict):
    supabase = get_supabase()
    return supabase.table("buildings").update(body).eq("id", building_id).execute().data[0]

@router.delete("/{building_id}")
def delete_building(building_id: str):
    supabase = get_supabase()
    supabase.table("buildings").update({"is_active": False}).eq("id", building_id).execute()
    return {"message": "삭제됐습니다"}
