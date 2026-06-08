# routers/watch_engine_identity_api.py — Identity & Visibility API v2
"""
플랫폼 공통 Identity / Visibility / Audience / Menu 인터페이스.
v2: 기존 role_code 매핑 + menu visibility 추가.
"""

import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/watch-engine/identity", tags=["아이덴티티"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


@router.get("/roles")
def get_roles():
    """역할 목록 (Identity Core)."""
    try:
        resp = _sb().table("identity_role_registry").select("*").eq("enabled", True).order("role_key").execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/role-mapping")
def get_role_mapping():
    """기존 role_code → Identity Core 매핑."""
    try:
        resp = _sb().table("identity_role_mapping") \
            .select("role_code,role_name,identity_role_key,actor_type,visibility_scope,governance_level,notification_level,scope_type") \
            .order("role_code").execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/context/{actor_id}")
def get_actor_context(actor_id: str, tenant_id: str = None):
    """행위자 컨텍스트 (실제 users 테이블 연결)."""
    try:
        from watch_engine.identity import resolve_actor_context, resolve_governance_visibility, get_menu_visibility
        sb = _sb()
        ctx = resolve_actor_context(sb, actor_id, tenant_id)
        vis = resolve_governance_visibility(ctx)
        menu = get_menu_visibility(sb, ctx)
        return {"status": "success", "data": {"context": ctx, "visibility": vis, "menu": menu}}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/visible-tenants")
def get_visible_tenants(actor_id: str = "founder"):
    """보기 가능 tenant."""
    try:
        from watch_engine.identity import resolve_actor_context, get_visible_tenants
        sb = _sb()
        ctx = resolve_actor_context(sb, actor_id)
        tenants = get_visible_tenants(sb, ctx)
        return {"status": "success", "data": {"actor_id": actor_id, "visible_tenants": tenants}}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/visible-incidents")
def get_visible_incidents_api(actor_id: str = "founder", tenant_id: str = None, limit: int = 20):
    """보기 가능 인시던트."""
    try:
        from watch_engine.identity import resolve_actor_context, get_visible_incidents
        sb = _sb()
        ctx = resolve_actor_context(sb, actor_id, tenant_id)
        incidents = get_visible_incidents(sb, ctx, limit=limit)
        return {"status": "success", "data": {"actor_id": actor_id, "scope": ctx.get("visibility_scope"), "incidents": incidents, "total": len(incidents)}}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/audience")
def get_notification_audience(event_type: str = "sla_critical", severity: str = "CRITICAL", tenant_id: str = "tai"):
    """알림 대상자 해석 (routing registry 연동)."""
    try:
        from watch_engine.identity import resolve_notification_audience
        audiences = resolve_notification_audience(_sb(), {"event_type": event_type, "severity": severity, "tenant_id": tenant_id})
        return {"status": "success", "data": audiences}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/menu-visibility")
def get_menu_visibility_api(actor_id: str = "founder", tenant_id: str = None):
    """메뉴 가시성."""
    try:
        from watch_engine.identity import resolve_actor_context, get_menu_visibility
        sb = _sb()
        ctx = resolve_actor_context(sb, actor_id, tenant_id)
        menu = get_menu_visibility(sb, ctx)
        return {"status": "success", "data": {"actor_id": actor_id, "role_key": ctx.get("role_key"), "menu": menu}}
    except Exception as e:
        return {"status": "error", "message": str(e)}
