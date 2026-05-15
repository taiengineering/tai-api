"""Alert Lifecycle — ACK / Resolve."""

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("workflow_alert.lifecycle")


def ack_alert(alert_id: str, acked_by: Optional[str] = None) -> dict:
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        sb.table("workflow_alert_event").update({
            "acknowledged": True,
            "acknowledged_at": datetime.now(timezone.utc).isoformat(),
            "acknowledged_by": acked_by,
        }).eq("id", alert_id).execute()
        return {"status": "success", "alert_id": alert_id, "action": "ACK"}
    except Exception as e:
        logger.error("ACK failed: %s — %s", alert_id, e)
        return {"status": "error", "message": str(e)}


def resolve_alert(alert_id: str, resolved_by: Optional[str] = None) -> dict:
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        sb.table("workflow_alert_event").update({
            "resolved": True,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
            "resolved_by": resolved_by,
        }).eq("id", alert_id).execute()
        return {"status": "success", "alert_id": alert_id, "action": "RESOLVE"}
    except Exception as e:
        logger.error("Resolve failed: %s — %s", alert_id, e)
        return {"status": "error", "message": str(e)}
