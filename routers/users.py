# routers/users.py
from fastapi import APIRouter, HTTPException
from db.supabase_client import get_supabase

router = APIRouter(prefix="/users", tags=["users"])

@router.get("")
def get_users(
    company_id: str = None,
    factory_id: str = None,
    team_id: str = None,
    role_code: str = None
):
    supabase = get_supabase()
    query = supabase.table("users")\
        .select("*, roles(role_name, role_code), teams(team_name)")\
        .eq("is_active", True)
    if company_id:
        query = query.eq("company_id", company_id)
    if factory_id:
        query = query.eq("factory_id", factory_id)
    if team_id:
        query = query.eq("team_id", team_id)
    if role_code:
        query = query.eq("role_code", role_code)
    return query.order("created_at", desc=True).execute().data

@router.get("/{user_id}")
def get_user(user_id: str):
    supabase = get_supabase()
    result = supabase.table("users")\
        .select("*, roles(role_name, role_code), teams(team_name), factories(name)")\
        .eq("id", user_id)\
        .single()\
        .execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    return result.data

@router.post("")
def create_user(body: dict):
    supabase = get_supabase()
    return supabase.table("users").insert(body).execute().data[0]

@router.patch("/{user_id}")
def update_user(user_id: str, body: dict):
    supabase = get_supabase()
    return supabase.table("users").update(body).eq("id", user_id).execute().data[0]

@router.delete("/{user_id}")
def delete_user(user_id: str):
    supabase = get_supabase()
    supabase.table("users").update({
        "is_active": False,
        "status_code": "DELETED"
    }).eq("id", user_id).execute()
    return {"message": "삭제됐습니다"}

@router.patch("/{user_id}/notification")
def update_notification(user_id: str, body: dict):
    """알림 설정 업데이트"""
    supabase = get_supabase()
    allowed_fields = ["allow_push", "allow_sms", "allow_email", "allow_kakao"]
    update_data = {k: v for k, v in body.items() if k in allowed_fields}
    return supabase.table("users").update(update_data).eq("id", user_id).execute().data[0]

