"""Feed Query Service — Unified Notification Feed 조회.

notifications + runtime_notification_event + runtime_notification_audit
조합 조회. Materialized Feed 구축 금지 (Query composition만).
"""

import logging
from typing import Optional, List
from datetime import datetime, timezone

logger = logging.getLogger("notification_engine.feed_query")


def get_feed(
    user_id: Optional[str] = None,
    source_type: Optional[str] = None,
    unread_only: bool = False,
    severity: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Unified Feed 조회. notifications 테이블 기반."""
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()

        q = sb.table("notifications") \
            .select("*", count="exact") \
            .order("created_at", desc=True)

        if user_id:
            q = q.eq("user_id", user_id)
        if unread_only:
            q = q.eq("is_read", False)
        if severity:
            q = q.eq("priority", severity)
        if source_type:
            q = q.eq("trigger_group", source_type)

        resp = q.range(offset, offset + limit - 1).execute()

        items = []
        for row in (resp.data or []):
            items.append(_to_feed_item(row))

        return {
            "items": items,
            "total": resp.count or 0,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        logger.error("Feed query failed: %s", e)
        return {"items": [], "total": 0, "limit": limit, "offset": offset, "error": str(e)}


def get_unread_count(user_id: Optional[str] = None) -> int:
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        q = sb.table("notifications") \
            .select("id", count="exact") \
            .eq("is_read", False)
        if user_id:
            q = q.eq("user_id", user_id)
        resp = q.execute()
        return resp.count or 0
    except Exception:
        return -1


def mark_read(notification_id: str, read_by: Optional[str] = None) -> bool:
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        sb.table("notifications").update({
            "is_read": True,
            "read_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", notification_id).execute()
        return True
    except Exception as e:
        logger.error("Mark read failed: %s", e)
        return False


def mark_unread(notification_id: str) -> bool:
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        sb.table("notifications").update({
            "is_read": False,
            "read_at": None,
        }).eq("id", notification_id).execute()
        return True
    except Exception as e:
        logger.error("Mark unread failed: %s", e)
        return False


def get_feed_timeline(trace_id: str) -> Optional[dict]:
    """trace_id 기반 Feed + Runtime 통합 Timeline."""
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()

        ev = sb.table("runtime_notification_event") \
            .select("*").eq("trace_id", trace_id).limit(1).execute()
        event = ev.data[0] if ev.data else None

        qu = sb.table("runtime_notification_queue") \
            .select("*").eq("trace_id", trace_id).order("created_at").execute()
        queue_items = qu.data or []

        au = sb.table("runtime_notification_audit") \
            .select("*").eq("trace_id", trace_id).order("action_at").execute()
        audit_trail = au.data or []

        timeline = []
        if event:
            timeline.append({"step": "EVENT", "time": event.get("occurred_at") or event.get("created_at"),
                             "status": event.get("event_status"), "detail": event.get("event_type")})
        for qi in queue_items:
            timeline.append({"step": "QUEUE", "time": qi.get("created_at"),
                             "status": qi.get("delivery_status"), "detail": qi.get("delivery_channel")})
            if qi.get("delivered_at"):
                timeline.append({"step": "DELIVERED", "time": qi["delivered_at"],
                                 "status": "DELIVERED", "detail": qi.get("delivery_channel")})
        for a in audit_trail:
            timeline.append({"step": f"AUDIT_{a.get('action')}", "time": a.get("action_at"),
                             "status": a.get("delivery_status"), "detail": a.get("error_message") or a.get("action")})
        timeline.sort(key=lambda x: x.get("time") or "")

        return {"trace_id": trace_id, "event": event, "queue_items": queue_items,
                "audit_trail": audit_trail, "timeline": timeline}
    except Exception as e:
        logger.error("Feed timeline failed: %s", e)
        return None


def _to_feed_item(row: dict) -> dict:
    """notifications row → Feed Item Contract."""
    return {
        "notification_id": row.get("id"),
        "source_type": row.get("trigger_group") or "service_notice",
        "channel_key": row.get("channel") or "SITE",
        "title": row.get("title"),
        "body": row.get("body"),
        "severity": row.get("priority") or "INFO",
        "created_at": row.get("created_at"),
        "read_at": row.get("read_at"),
        "is_read": row.get("is_read", False),
        "trace_id": None,
        "source_reference_id": row.get("link_url"),
        "link_url": row.get("link_url"),
        "actor_id": str(row.get("user_id")) if row.get("user_id") else None,
        "tenant_id": str(row.get("company_id")) if row.get("company_id") else None,
        "trigger_code": row.get("trigger_code"),
    }
