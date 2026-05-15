"""Identity Core Interface v2 — 기존 권한체계 연결.

기존 users.role_code → identity_role_mapping → Identity Core 표준 인터페이스.
기존 auth/token 구조 변경 없음. 인터페이스만 표준화.
"""

import logging
from typing import Optional

logger = logging.getLogger("watch_engine.identity")

# Cache: role_code → mapping (서버 시작 시 1회 로드)
_role_mapping_cache: dict = {}


def _load_role_mapping(sb) -> dict:
    """role_code → Identity Core 매핑 로드 (캐시)."""
    global _role_mapping_cache
    if _role_mapping_cache:
        return _role_mapping_cache
    try:
        resp = sb.table("identity_role_mapping") \
            .select("role_code,identity_role_key,actor_type,visibility_scope,governance_level,notification_level") \
            .execute()
        for r in (resp.data or []):
            _role_mapping_cache[r["role_code"]] = r
    except Exception as e:
        logger.warning("Failed to load role mapping: %s", e)
    return _role_mapping_cache


def resolve_actor_context(sb, actor_id: str, tenant_id: str = None) -> dict:
    """행위자 컨텍스트 해석 — 실제 users 테이블 연결."""
    ctx = {
        "actor_id": actor_id,
        "tenant_id": tenant_id,
        "role_key": "tenant_user",
        "role_code": None,
        "actor_type": "tenant_user",
        "visibility_scope": "self",
        "governance_level": "viewer",
        "notification_level": "own",
        "can_manage_alerts": False,
        "can_view_all_tenants": False,
        "factory_id": None,
        "company_id": None,
    }

    # 1. Platform admin shortcut (founder/admin/system)
    if actor_id in ("founder", "admin", "system"):
        try:
            role = sb.table("identity_role_registry") \
                .select("*").eq("role_key", "platform_admin").limit(1).execute()
            if role.data:
                r = role.data[0]
                ctx.update({
                    "role_key": r["role_key"],
                    "role_code": "001",
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

    # 2. Actual user lookup
    try:
        user = sb.table("users") \
            .select("id,role_code,factory_id,company_id,name,email") \
            .eq("id", actor_id).limit(1).execute()

        if user.data:
            u = user.data[0]
            role_code = u.get("role_code")
            ctx["role_code"] = role_code
            ctx["factory_id"] = u.get("factory_id")
            ctx["company_id"] = u.get("company_id")

            # Derive tenant_id from company_id or factory_id
            if not tenant_id:
                ctx["tenant_id"] = str(u.get("company_id") or u.get("factory_id") or "")

            # 3. Map role_code → Identity Core
            mapping = _load_role_mapping(sb)
            if role_code and role_code in mapping:
                m = mapping[role_code]
                ctx.update({
                    "role_key": m["identity_role_key"],
                    "actor_type": m["actor_type"],
                    "visibility_scope": m["visibility_scope"],
                    "governance_level": m["governance_level"],
                    "notification_level": m["notification_level"],
                })

            # 4. Derived permissions
            ctx["can_manage_alerts"] = ctx["governance_level"] == "admin"
            ctx["can_view_all_tenants"] = ctx["visibility_scope"] == "platform"

    except Exception as e:
        logger.warning("User lookup failed for %s: %s", actor_id, e)

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
            pass
        elif scope in ("tenant", "team"):
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
    """알림 대상자 해석 — routing registry 연동."""
    audiences = []
    severity = event.get("severity", "INFO")
    event_type = event.get("event_type", "")
    tenant_id = event.get("tenant_id")

    try:
        # 1. Routing registry 우선
        routes = sb.table("notification_routing_registry") \
            .select("route_key,audience_key,channel,escalation_level,template_key") \
            .eq("event_type", event_type).eq("enabled", True).execute()

        for r in (routes.data or []):
            audiences.append({
                "role_key": r["audience_key"],
                "channel": r["channel"],
                "escalation_level": r.get("escalation_level", "L1"),
                "template_key": r.get("template_key"),
                "reason": f"routing_{r['route_key']}",
                "tenant_id": tenant_id,
            })

        # 2. Fallback: identity_role_registry
        if not audiences:
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
    """거버넌스 가시성 기준."""
    scope = actor_ctx.get("visibility_scope", "self")
    gov = actor_ctx.get("governance_level", "viewer")
    return {
        "can_view_all_tenants": scope == "platform",
        "can_view_tenant_governance": scope in ("platform", "tenant"),
        "can_view_incidents": scope in ("platform", "tenant", "team", "self"),
        "can_manage_alerts": gov == "admin",
        "can_manage_playbooks": gov in ("admin", "operator"),
        "can_view_playbooks": scope in ("platform", "tenant"),
        "can_view_synthetic": scope == "platform",
        "can_view_recovery": gov in ("admin", "operator"),
    }


def get_menu_visibility(sb, actor_ctx: dict) -> dict:
    """메뉴 가시성 — 기존 role_menu_permissions 연동."""
    result = {"watch_engine": False, "message_templates": False,
              "notification_routing": False, "workflow_registry": False}

    scope = actor_ctx.get("visibility_scope", "self")
    gov = actor_ctx.get("governance_level", "viewer")

    # Platform admin: 전체
    if scope == "platform":
        return {k: True for k in result}

    # Operator: Watch Engine + Workflow
    if gov in ("admin", "operator"):
        result["watch_engine"] = True
        result["workflow_registry"] = True

    # Tenant admin: 알림 설정
    if actor_ctx.get("actor_type") == "tenant_admin":
        result["message_templates"] = True
        result["notification_routing"] = True

    return result
