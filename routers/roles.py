# routers/roles.py
from fastapi import APIRouter, HTTPException
from db.supabase_client import get_supabase

router = APIRouter(prefix="/roles", tags=["roles"])

@router.get("")
def get_roles():
    supabase = get_supabase()
    return supabase.table("roles").select("*").eq("is_active", True).order("role_code").execute().data

@router.get("/{role_id}")
def get_role(role_id: str):
    supabase = get_supabase()
    result = supabase.table("roles").select("*").eq("id", role_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="역할을 찾을 수 없습니다")
    return result.data

@router.post("")
def create_role(body: dict):
    supabase = get_supabase()
    return supabase.table("roles").insert(body).execute().data[0]

@router.patch("/{role_id}")
def update_role(role_id: str, body: dict):
    supabase = get_supabase()
    return supabase.table("roles").update(body).eq("id", role_id).execute().data[0]

# 역할별 권한 조회
@router.get("/{role_id}/permissions")
def get_role_permissions(role_id: str):
    supabase = get_supabase()
    role = supabase.table("roles").select("role_code").eq("id", role_id).single().execute()
    if not role.data:
        raise HTTPException(status_code=404, detail="역할을 찾을 수 없습니다")
    role_code = role.data["role_code"]
    return supabase.table("role_permissions")\
        .select("*, permissions(*)")\
        .eq("role_code", role_code)\
        .execute().data

# 역할별 메뉴 권한 조회
@router.get("/{role_id}/menus")
def get_role_menus(role_id: str):
    supabase = get_supabase()
    role = supabase.table("roles").select("role_code").eq("id", role_id).single().execute()
    if not role.data:
        raise HTTPException(status_code=404, detail="역할을 찾을 수 없습니다")
    role_code = role.data["role_code"]
    return supabase.table("role_menu_permissions")\
        .select("*, menus(*)")\
        .eq("role_code", role_code)\
        .execute().data

