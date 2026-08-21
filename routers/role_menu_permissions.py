"""역할×메뉴 권한 매트릭스 — manager-permission 정본.

menu_code = vue3 nav route slug. 근로자(014)는 앱 전용이라 매트릭스에서 제외.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user

router = APIRouter(tags=["role-menu-permissions"])

ADMIN_ROLE_CODES = {"001", "002", "010", "011"}


def require_perm_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role_code") not in ADMIN_ROLE_CODES:
        raise HTTPException(status_code=403, detail="권한이 없습니다.")
    return current_user


class PermPatchBody(BaseModel):
    role_code: str
    menu_code: str
    can_list: bool = False
    can_create: bool = False
    can_update: bool = False
    can_delete: bool = False
    can_export: bool = False


class PermBulkBody(BaseModel):
    items: List[PermPatchBody]


def _perm_row(body: PermPatchBody) -> dict:
    return {
        "role_code": body.role_code,
        "menu_code": body.menu_code,
        "can_list": body.can_list,
        "can_create": body.can_create,
        "can_update": body.can_update,
        "can_delete": body.can_delete,
        "can_export": body.can_export,
    }


@router.get("/users/roles")
def list_roles(
    site: Optional[str] = Query(None),
    _current_user: dict = Depends(require_perm_admin),
):
    supabase = get_supabase()
    res = (
        supabase.table("roles")
        .select("role_code, role_name")
        .eq("is_active", True)
        .neq("role_code", "014")
        .order("role_code")
        .execute()
    )
    return {"status": "success", "data": {"items": res.data or []}}


@router.get("/role-menu-permissions")
def list_permissions(
    site: Optional[str] = Query(None),
    _current_user: dict = Depends(require_perm_admin),
):
    supabase = get_supabase()
    res = (
        supabase.table("role_menu_permissions")
        .select("role_code, menu_code, can_list, can_create, can_update, can_delete, can_export")
        .limit(2000)
        .execute()
    )
    return {"status": "success", "data": {"items": res.data or []}}


@router.patch("/role-menu-permissions")
def patch_permission(
    body: PermPatchBody,
    _current_user: dict = Depends(require_perm_admin),
):
    supabase = get_supabase()
    try:
        res = (
            supabase.table("role_menu_permissions")
            .upsert(_perm_row(body), on_conflict="role_code,menu_code")
            .execute()
        )
    except Exception:
        existing = (
            supabase.table("role_menu_permissions")
            .select("id")
            .eq("role_code", body.role_code)
            .eq("menu_code", body.menu_code)
            .limit(1)
            .execute()
        )
        if existing.data:
            res = (
                supabase.table("role_menu_permissions")
                .update(_perm_row(body))
                .eq("id", existing.data[0]["id"])
                .execute()
            )
        else:
            res = supabase.table("role_menu_permissions").insert(_perm_row(body)).execute()
    return {"status": "success", "data": (res.data[0] if res.data else _perm_row(body))}


@router.put("/role-menu-permissions/bulk")
def bulk_permissions(
    body: PermBulkBody,
    _current_user: dict = Depends(require_perm_admin),
):
    supabase = get_supabase()
    rows = [_perm_row(item) for item in body.items]
    if not rows:
        return {"status": "success", "data": {"items": [], "updated": 0}}
    try:
        res = (
            supabase.table("role_menu_permissions")
            .upsert(rows, on_conflict="role_code,menu_code")
            .execute()
        )
        return {"status": "success", "data": {"items": res.data or [], "updated": len(rows)}}
    except Exception:
        updated = 0
        for item in body.items:
            try:
                supabase.table("role_menu_permissions").upsert(
                    _perm_row(item), on_conflict="role_code,menu_code"
                ).execute()
                updated += 1
            except Exception:
                existing = (
                    supabase.table("role_menu_permissions")
                    .select("id")
                    .eq("role_code", item.role_code)
                    .eq("menu_code", item.menu_code)
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    supabase.table("role_menu_permissions").update(_perm_row(item)).eq(
                        "id", existing.data[0]["id"]
                    ).execute()
                else:
                    supabase.table("role_menu_permissions").insert(_perm_row(item)).execute()
                updated += 1
        return {"status": "success", "data": {"items": [], "updated": updated}}
