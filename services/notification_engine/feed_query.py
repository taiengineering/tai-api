"""Feed Query v2.0 — trace_id 연결 강화."""

import logging
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger("notification_engine.feed_query")


def get_feed(
    user_id: Optional[str] = None,
    source_type: Optional[str] = None,
    unread_only: bool = False,
    severity: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    apply_preference: bool = True,
) -> dict:
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        q = sb.table("notifications").select("*", count="exact").order("created_at", desc=True)
        if user_id:
            q = q.eq("user_id", user_id)
        if unread_only:
            q = q.eq("is_read", False)
        if severity:
            q = q.eq("priority", severity)
        if source_type:
            q = q.eq("trigger_group", source_type)
        resp = q.range(offset, offset + limit - 1).execute()

        muted_sources = set()
        if apply_preference and user_id:
            try:
                from services.notification_engine.preference_service import get_muted_sources
                muted_sources = set(get_muted_sources(user_id))
            except Exception:
                pass

        items = []
        for row in (resp.data or []):
            item = _to_feed_item(row)
            if muted_sources and item.get("source_type") in muted_sources:
                continue
            items.append(item)

        return {"items": items, "total": resp.count or 0, "limit": limit, "offset": offset}
    except Exception as e:
        return {"items": [], "total": 0, "limit": limit, "offset": offset, "error": str(e)}


def get_unread_count(user_id: Optional[str] = None) -> int:
    try:
        from db.supabase_client import get_supabase
        q = get_supabase().table("notifications").select("id", count="exact").eq("is_read", False)
        if user_id:
            q = q.eq("user_id", user_id)
        return q.execute().count or 0
    except Exception:
        return -1


def mark_read(notification_id: str, read_by: Optional[str] = None) -> bool:
    try:
        from db.supabase_client import get_supabase
        get_supabase().table("notifications").update({
            "is_read": True, "read_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", notification_id).execute()
        return True
    except Exception:
        return False


def mark_unread(notification_id: str) -> bool:
    try:
        from db.supabase_client import get_supabase
        get_supabase().table("notifications").update({"is_read": False, "read_at": None}).eq("id", notification_id).execute()
        return True
    except Exception:
        return False


def get_feed_timeline(trace_id: str) -> dict | None:
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        ev = sb.table("runtime_notification_event").select("*").eq("trace_id", trace_id).limit(1).execute()
        event = ev.data[0] if ev.data else None
        qu = sb.table("runtime_notification_queue").select("*").eq("trace_id", trace_id).order("created_at").execute()
        au = sb.table("runtime_notification_audit").select("*").eq("trace_id", trace_id).order("action_at").execute()
        pa = sb.table("runtime_notification_policy_audit").select("*").eq("trace_id", trace_id).order("created_at").execute()
        # Feed items via trace_id
        fi = sb.table("notifications").select("*").eq("trace_id", trace_id).order("created_at").execute()

        timeline = []
        if event:
            timeline.append({"step": "EVENT", "time": event.get("occurred_at") or event.get("created_at"),
                             "status": event.get("event_status"), "detail": event.get("event_type")})
        for qi in (qu.data or []):
            timeline.append({"step": "QUEUE", "time": qi.get("created_at"),
                             "status": qi.get("delivery_status"), "detail": qi.get("delivery_channel")})
            if qi.get("delivered_at"):
                timeline.append({"step": "DELIVERED", "time": qi["delivered_at"],
                                 "status": "DELIVERED", "detail": qi.get("delivery_channel")})
        for a in (au.data or []):
            timeline.append({"step": f"AUDIT_{a.get('action')}", "time": a.get("action_at"),
                             "status": a.get("delivery_status"), "detail": a.get("action")})
        for p in (pa.data or []):
            timeline.append({"step": f"POLICY_{p.get('policy_type')}", "time": p.get("created_at"),
                             "status": p.get("policy_result"), "detail": p.get("reason")})
        for f in (fi.data or []):
            timeline.append({"step": "FEED_CREATED", "time": f.get("created_at"),
                             "status": "READ" if f.get("is_read") else "UNREAD", "detail": f.get("trigger_code")})
        timeline.sort(key=lambda x: x.get("time") or "")

        return {"trace_id": trace_id, "event": event, "queue_items": qu.data or [],
                "audit_trail": au.data or [], "policy_audit": pa.data or [],
                "feed_items": fi.data or [], "timeline": timeline}
    except Exception as e:
        return None


def _to_feed_item(row: dict) -> dict:
    return {
        "notification_id": row.get("id"),
        "source_type": row.get("trigger_group") or "service_notice",
        "channel_key": row.get("channel") or "SITE",
        "title": row.get("title"), "body": row.get("body"),
        "severity": row.get("priority") or "INFO",
        "created_at": row.get("created_at"), "read_at": row.get("read_at"),
        "is_read": row.get("is_read", False),
        "trace_id": row.get("trace_id"),
        "source_reference_id": row.get("link_url"), "link_url": row.get("link_url"),
        "actor_id": str(row.get("user_id")) if row.get("user_id") else None,
        "tenant_id": str(row.get("company_id")) if row.get("company_id") else None,
        "trigger_code": row.get("trigger_code"),
    }
