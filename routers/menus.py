"""메뉴 카탈로그 — safe 사이드바·권한매트릭스 정본.

menu_code = vue3 route slug = role_menu_permissions.menu_code.
"""
from fastapi import APIRouter, Depends

from db.supabase_client import get_supabase
from routers.auth import get_current_user

router = APIRouter(tags=["menus"])


@router.get("/menus")
def list_menus(_current_user: dict = Depends(get_current_user)):
    supabase = get_supabase()
    res = (
        supabase.table("menu_catalog")
        .select("menu_code, title, group_code, group_title, sort_order, sectors")
        .eq("is_active", True)
        .order("sort_order")
        .execute()
    )
    return {"status": "success", "data": {"items": res.data or []}}
