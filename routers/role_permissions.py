"""플랫폼 권한 매트릭스 — role × PLATFORM_OPS permission 보유여부.

site=admin. 001 전권은 잠금(편집 불가). 031–033만 PATCH/PUT.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user

router = APIRouter(tags=["role-permissions"])

PLATFORM_ROLES = ("001", "031", "032", "033")
EDITABLE_ROLES = {"031", "032", "033"}
GROUP = "PLATFORM_OPS"


def require_platform_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role_code") != "001":
        raise HTTPException(status_code=403, detail="최고관리자만 플랫폼 권한을 관리할 수 있습니다.")
    return current_user


class GrantPatchBody(BaseModel):
    role_code: str
    permission_code: str
    granted: bool


class GrantBulkBody(BaseModel):
    items: List[GrantPatchBody]


def _assert_editable(role_code: str) -> None:
    if role_code == "001":
        raise HTTPException(status_code=403, detail="최고관리자 권한은 변경할 수 없습니다.")
    if role_code not in EDITABLE_ROLES:
        raise HTTPException(status_code=400, detail="플랫폼 서브롤(031–033)만 편집할 수 있습니다.")


@router.get("/users/platform-roles")
def list_platform_roles(
    site: Optional[str] = Query(None),
    _current_user: dict = Depends(require_platform_admin),
):
    supabase = get_supabase()
    res = (
        supabase.table("roles")
        .select("role_code, role_name")
        .in_("role_code", list(PLATFORM_ROLES))
        .order("role_code")
        .execute()
    )
    items = []
    for r in res.data or []:
        code = r.get("role_code")
        items.append({
            "role_code": code,
            "role_name": r.get("role_name"),
            "locked": code == "001",
        })
    return {"status": "success", "data": {"items": items}}


@router.get("/role-permissions")
def list_role_permissions(
    group: str = Query(GROUP),
    site: Optional[str] = Query(None),
    _current_user: dict = Depends(require_platform_admin),
):
    supabase = get_supabase()
    perms = (
        supabase.table("permissions")
        .select("permission_code, permission_name, group_code")
        .eq("group_code", group)
        .order("permission_code")
        .execute()
    )
    perm_rows = perms.data or []
    codes = [p["permission_code"] for p in perm_rows]
    grants = (
        supabase.table("role_permissions")
        .select("role_code, permission_code")
        .in_("role_code", list(PLATFORM_ROLES))
        .limit(2000)
        .execute()
    )
    granted = {
        (g.get("role_code"), g.get("permission_code"))
        for g in (grants.data or [])
        if g.get("permission_code") in codes
    }
    items = []
    for role in PLATFORM_ROLES:
        for code in codes:
            items.append({
                "role_code": role,
                "permission_code": code,
                "granted": (role, code) in granted,
            })
    return {
        "status": "success",
        "data": {
            "group": group,
            "permissions": perm_rows,
            "items": items,
        },
    }


def _set_grant(supabase, role_code: str, permission_code: str, granted: bool) -> None:
    existing = (
        supabase.table("role_permissions")
        .select("id")
        .eq("role_code", role_code)
        .eq("permission_code", permission_code)
        .limit(1)
        .execute()
    )
    if granted:
        if existing.data:
            return
        supabase.table("role_permissions").insert({
            "role_code": role_code,
            "permission_code": permission_code,
        }).execute()
        return
    if existing.data:
        supabase.table("role_permissions").delete().eq("id", existing.data[0]["id"]).execute()


@router.patch("/role-permissions")
def patch_role_permission(
    body: GrantPatchBody,
    _current_user: dict = Depends(require_platform_admin),
):
    _assert_editable(body.role_code)
    supabase = get_supabase()
    perm = (
        supabase.table("permissions")
        .select("permission_code, group_code")
        .eq("permission_code", body.permission_code)
        .eq("group_code", GROUP)
        .limit(1)
        .execute()
    )
    if not perm.data:
        raise HTTPException(status_code=400, detail="PLATFORM_OPS 권한이 아닙니다.")
    _set_grant(supabase, body.role_code, body.permission_code, body.granted)
    return {
        "status": "success",
        "data": {
            "role_code": body.role_code,
            "permission_code": body.permission_code,
            "granted": body.granted,
        },
    }


@router.put("/role-permissions/bulk")
def bulk_role_permissions(
    body: GrantBulkBody,
    _current_user: dict = Depends(require_platform_admin),
):
    supabase = get_supabase()
    updated = 0
    for item in body.items:
        _assert_editable(item.role_code)
        perm = (
            supabase.table("permissions")
            .select("permission_code")
            .eq("permission_code", item.permission_code)
            .eq("group_code", GROUP)
            .limit(1)
            .execute()
        )
        if not perm.data:
            continue
        _set_grant(supabase, item.role_code, item.permission_code, item.granted)
        updated += 1
    return {"status": "success", "data": {"updated": updated}}
