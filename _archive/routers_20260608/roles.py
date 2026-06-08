# routers/roles.py — v2.0.0 (Capability Wrapper Migration)
# Wrapper: transport only. Capability: auth/core + auth/adapters.
from fastapi import APIRouter, HTTPException
from db.supabase_client import get_supabase

router = APIRouter(prefix="/roles", tags=["roles"])

# === Adapter layer (DB operations) ===

def _adapter_list_roles(supabase):
    return supabase.table("roles").select("*").eq("is_active", True).order("role_code").execute().data

def _adapter_get_role(supabase, role_id: str):
    result = supabase.table("roles").select("*").eq("id", role_id).single().execute()
    return result.data

def _adapter_create_role(supabase, body: dict):
    return supabase.table("roles").insert(body).execute().data[0]

def _adapter_update_role(supabase, role_id: str, body: dict):
    return supabase.table("roles").update(body).eq("id", role_id).execute().data[0]

def _adapter_get_role_code(supabase, role_id: str):
    role = supabase.table("roles").select("role_code").eq("id", role_id).single().execute()
    return role.data["role_code"] if role.data else None

def _adapter_get_permissions(supabase, role_code: str):
    return supabase.table("role_permissions").select("*, permissions(*)").eq("role_code", role_code).execute().data

def _adapter_get_menus(supabase, role_code: str):
    return supabase.table("role_menu_permissions").select("*, menus(*)").eq("role_code", role_code).execute().data

# === Wrapper layer (transport only) ===

@router.get("")
def get_roles():
    return _adapter_list_roles(get_supabase())

@router.get("/{role_id}")
def get_role(role_id: str):
    data = _adapter_get_role(get_supabase(), role_id)
    if not data:
        raise HTTPException(status_code=404, detail="역할을 찾을 수 없습니다")
    return data

@router.post("")
def create_role(body: dict):
    return _adapter_create_role(get_supabase(), body)

@router.patch("/{role_id}")
def update_role(role_id: str, body: dict):
    return _adapter_update_role(get_supabase(), role_id, body)

@router.get("/{role_id}/permissions")
def get_role_permissions(role_id: str):
    supabase = get_supabase()
    role_code = _adapter_get_role_code(supabase, role_id)
    if not role_code:
        raise HTTPException(status_code=404, detail="역할을 찾을 수 없습니다")
    return _adapter_get_permissions(supabase, role_code)

@router.get("/{role_id}/menus")
def get_role_menus(role_id: str):
    supabase = get_supabase()
    role_code = _adapter_get_role_code(supabase, role_id)
    if not role_code:
        raise HTTPException(status_code=404, detail="역할을 찾을 수 없습니다")
    return _adapter_get_menus(supabase, role_code)
