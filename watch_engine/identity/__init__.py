"""Identity Core Interface — 플랫폼 공통 권한 언어.

Actor Context / Permission / Visibility / Audience Resolution.
IAM 플랫폼이 아님. 공통 인터페이스만 제공.
"""

import logging
from typing import Optional

logger = logging.getLogger("watch_engine.identity")


def resolve_actor_context(sb, actor_id: str, tenant_id: str = None) -> dict:
    """행위자 컨텍스트 해석."""
    ctx = {
        "actor_id": actor_id,
        "tenant_id": tenant_id,
        "role_key": "tenant_user",
        "actor_type": "tenant_user",
        "visibility_scope": "self",
        "governance_level": "viewer",
        "notification_level": "own",
        "can_manage_alerts": False,
        "can_view_all_tenants": False,
    }

    # Platform admin check (founder)
    if actor_id in ("founder", "admin", "system"):
        try:
            role = sb.table("identity_role_registry") \
                .select("*").eq("role_key", "platform_admin").limit(1).execute()
            if role.data:
                r = role.data[0]
                ctx.update({
                    "role_key": r["role_key"],
                    "actor_type": r["actor_type"],
                    "visibility_scope": r["visibility_scope"],
                    "governance_level": r["governance_level"],
                    "notification_level": r["notification_level"],
                    "can_manage_alerts": r.get("can_manage_alerts", False),
                    "can_view_all_tenants": r.get("can_view_all_tenants", False),
                })
        except Exception:
            pass
        return ctx

    # Tenant-level resolution
    if tenant_id:
        ctx["role_key"] = "tenant_user"
        ctx["visibility_scope"] = "tenant" if _is_tenant_admin(sb, actor_id, tenant_id) else "self"

    return ctx


def get_visible_tenants(sb, actor_ctx: dict) -> list[str]:
    """보기 가능한 tenant 목록."""
    if actor_ctx.get("can_view_all_tenants") or actor_ctx.get("visibility_scope") == "platform":
        try:
            resp = sb.table("tenant_operational_registry").select("tenant_id").execute()
            return [r["tenant_id"] for r in (resp.data or [])]
        except Exception:
            return []

    tid = actor_ctx.get("tenant_id")
    return [tid] if tid else []


def get_visible_incidents(sb, actor_ctx: dict, limit: int = 50) -> list[dict]:
    """보기 가능한 인시던트."""
    try:
        q = sb.table("engine_integrity_event") \
            .select("id,flow_key,event_type,severity,tenant_id,description,created_at,resolved") \
            .not_.is_("trace_id", "null") \
            .order("created_at", desc=True).limit(limit)

        scope = actor_ctx.get("visibility_scope", "self")
        if scope == "platform":
            pass  # No filter
        elif scope == "tenant":
            tid = actor_ctx.get("tenant_id")
            if tid:
                q = q.eq("tenant_id", tid)
        else:
            q = q.eq("tenant_id", actor_ctx.get("tenant_id", "__none__"))

        resp = q.execute()
        return resp.data or []
    except Exception as e:
        logger.error("get_visible_incidents: %s", e)
        return []


def resolve_notification_audience(sb, event: dict) -> list[dict]:
    """\uc54c\ub9bc \ub300\uc0c1\uc790 \ud574\uc11d."""
    audiences = []
    severity = event.get("severity", "INFO")
    tenant_id = event.get("tenant_id")

    try:
        roles = sb.table("identity_role_registry") \
            .select("role_key,actor_type,notification_level") \
            .eq("enabled", True).execute()

        for r in (roles.data or []):
            level = r.get("notification_level", "none")
            if level == "all":
                audiences.append({"role_key": r["role_key"], "reason": "all_notifications"})
            elif level == "critical" and severity == "CRITICAL":
                audiences.append({"role_key": r["role_key"], "reason": "critical_only"})
            elif level == "own" and r.get("actor_type") in ("tenant_admin", "tenant_user"):
                audiences.append({"role_key": r["role_key"], "reason": "own_tenant", "tenant_id": tenant_id})
    except Exception as e:
        logger.error("resolve_notification_audience: %s", e)

    return audiences


def resolve_governance_visibility(actor_ctx: dict) -> dict:
    """거\ubc84\ub10c\uc2a4 \uac00\uc2dc\uc131 \uae30\uc900."""
    scope = actor_ctx.get("visibility_scope", "self")
    return {
        "can_view_all_tenants": scope == "platform",
        "can_view_tenant_governance": scope in ("platform", "tenant"),
        "can_view_incidents": scope in ("platform", "tenant", "self"),
        "can_manage_alerts": actor_ctx.get("can_manage_alerts", False),
        "can_view_playbooks": scope in ("platform", "tenant"),
        "can_view_synthetic": scope == "platform",
    }


def _is_tenant_admin(sb, actor_id: str, tenant_id: str) -> bool:
    """Stub: tenant admin \uc5ec\ubd80."""
    # TODO: \uc2e4\uc81c \uc0ac\uc6a9\uc790 \ud14c\uc774\ube14 \uc5f0\ub3d9
    return False
