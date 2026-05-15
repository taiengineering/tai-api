"""Alert Timeline — workflow_id 기반 Alert 이력."""

import logging
from typing import Optional

logger = logging.getLogger("workflow_alert.timeline")


def get_alert_timeline(workflow_id: str) -> Optional[dict]:
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()

        resp = sb.table("workflow_alert_event") \
            .select("*").eq("workflow_id", workflow_id) \
            .order("created_at").execute()

        alerts = resp.data or []
        open_count = sum(1 for a in alerts if not a.get("resolved"))
        acked_count = sum(1 for a in alerts if a.get("acknowledged"))

        return {
            "workflow_id": workflow_id,
            "total_alerts": len(alerts),
            "open_alerts": open_count,
            "acknowledged": acked_count,
            "alerts": alerts,
        }
    except Exception as e:
        logger.error("Alert timeline failed: %s — %s", workflow_id, e)
        return None
