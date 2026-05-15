# routers/watch_engine_identity_api.py — Identity & Visibility API
"""
플랫폼 공통 Identity / Visibility / Audience 인터페이스.
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
    """역\ud560 \ubaa9\ub85d."""
    try:
        resp = _sb().table("identity_role_registry").select("*").eq("enabled", True).order("role_key").execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/context/{actor_id}")
def get_actor_context(actor_id: str, tenant_id: str = None):
    """\ud589\uc704\uc790 \ucee8\ud14d\uc2a4\ud2b8."""
    try:
        from watch_engine.identity import resolve_actor_context, resolve_governance_visibility
        sb = _sb()
        ctx = resolve_actor_context(sb, actor_id, tenant_id)
        vis = resolve_governance_visibility(ctx)
        return {"status": "success", "data": {"context": ctx, "visibility": vis}}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/visible-tenants")
def get_visible_tenants(actor_id: str = "founder"):
    """\ubcf4\uae30 \uac00\ub2a5 tenant."""
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
    """\ubcf4\uae30 \uac00\ub2a5 \uc778\uc2dc\ub358\ud2b8."""
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
    """\uc54c\ub9bc \ub300\uc0c1\uc790 \ud574\uc11d."""
    try:
        from watch_engine.identity import resolve_notification_audience
        audiences = resolve_notification_audience(_sb(), {"event_type": event_type, "severity": severity, "tenant_id": tenant_id})
        return {"status": "success", "data": audiences}
    except Exception as e:
        return {"status": "error", "message": str(e)}
