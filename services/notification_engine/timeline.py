"""Trace Timeline — trace_id 기반 E2E 흐름 추적.

event → queue → audit → DLQ 전체 흐름을 시간순으로 반환.
"""

import logging
from typing import Optional

logger = logging.getLogger("notification_engine.timeline")


def get_timeline(trace_id: str) -> Optional[dict]:
    """trace_id로 전체 Notification 흐름 추적.

    Returns:
        {
            "trace_id": str,
            "event": dict|None,
            "queue_items": list,
            "audit_trail": list,
            "deadletters": list,
            "timeline": list,  # 시간순 정렬된 전체 흐름
        }
    """
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()

        # 1. Event
        ev_resp = sb.table("runtime_notification_event") \
            .select("*").eq("trace_id", trace_id).limit(1).execute()
        event = ev_resp.data[0] if ev_resp.data else None

        # 2. Queue items
        q_resp = sb.table("runtime_notification_queue") \
            .select("*").eq("trace_id", trace_id) \
            .order("created_at").execute()
        queue_items = q_resp.data or []

        # 3. Audit trail
        a_resp = sb.table("runtime_notification_audit") \
            .select("*").eq("trace_id", trace_id) \
            .order("action_at").execute()
        audit_trail = a_resp.data or []

        # 4. Dead letters
        dl_resp = sb.table("runtime_notification_deadletter") \
            .select("*").eq("trace_id", trace_id) \
            .order("created_at").execute()
        deadletters = dl_resp.data or []

        # 5. Timeline 구성 (시간순)
        timeline = []

        if event:
            timeline.append({
                "step": "EVENT",
                "time": event.get("occurred_at") or event.get("created_at"),
                "status": event.get("event_status"),
                "detail": f"{event.get('event_type')} from {event.get('source_engine')}",
            })

        for qi in queue_items:
            timeline.append({
                "step": "QUEUE",
                "time": qi.get("created_at"),
                "status": qi.get("delivery_status"),
                "detail": f"channel={qi.get('delivery_channel')} retry={qi.get('retry_count', 0)}",
            })
            if qi.get("delivered_at"):
                timeline.append({
                    "step": "DELIVERED",
                    "time": qi["delivered_at"],
                    "status": "DELIVERED",
                    "detail": f"via {qi.get('delivery_channel')}",
                })

        for a in audit_trail:
            timeline.append({
                "step": f"AUDIT_{a.get('action', 'UNKNOWN')}",
                "time": a.get("action_at"),
                "status": a.get("delivery_status"),
                "detail": a.get("error_message") or a.get("action"),
            })

        for dl in deadletters:
            timeline.append({
                "step": "DEADLETTER",
                "time": dl.get("created_at"),
                "status": "DEADLETTER",
                "detail": dl.get("failure_reason", "")[:100],
            })

        # 시간순 정렬
        timeline.sort(key=lambda x: x.get("time") or "")

        return {
            "trace_id": trace_id,
            "event": event,
            "queue_items": queue_items,
            "audit_trail": audit_trail,
            "deadletters": deadletters,
            "timeline": timeline,
        }

    except Exception as e:
        logger.error("Timeline lookup failed for %s: %s", trace_id, e)
        return None
