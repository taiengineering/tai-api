# routers/teams.py
from fastapi import APIRouter, HTTPException
from db.supabase_client import get_supabase

router = APIRouter(prefix="/teams", tags=["teams"])

@router.get("")
def get_teams(factory_id: str = None):
    supabase = get_supabase()
    query = supabase.table("teams").select("*").eq("is_active", True)
    if factory_id:
        query = query.eq("factory_id", factory_id)
    return query.order("created_at", desc=True).execute().data

@router.get("/{team_id}")
def get_team(team_id: str):
    supabase = get_supabase()
    result = supabase.table("teams").select("*").eq("id", team_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="팀을 찾을 수 없습니다")
    return result.data

@router.post("")
def create_team(body: dict):
    supabase = get_supabase()
    return supabase.table("teams").insert(body).execute().data[0]

@router.patch("/{team_id}")
def update_team(team_id: str, body: dict):
    supabase = get_supabase()
    return supabase.table("teams").update(body).eq("id", team_id).execute().data[0]

@router.delete("/{team_id}")
def delete_team(team_id: str):
    supabase = get_supabase()
    supabase.table("teams").update({"is_active": False}).eq("id", team_id).execute()
    return {"message": "삭제됐습니다"}

