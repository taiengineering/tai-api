"""Escalation Effectiveness."""
import logging
from datetime import datetime,timezone,timedelta
logger=logging.getLogger("watch_engine.feedback.escalation")
def track_escalation_effectiveness(sb,hours=24):
    since=(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat()
    try:
        actions=sb.table("incident_action_log").select("id,action_type,outcome_status,created_at").gte("created_at",since).execute()
        escalations=[a for a in (actions.data or []) if a.get("action_type")=="ESCALATED"]
        total=len(escalations)
        if total==0: return {"total":0,"effective_ratio":0,"noisy_ratio":0}
        resolved_after=sum(1 for a in (actions.data or []) if a.get("action_type") in ("RESOLVED","RECOVERED") and a.get("outcome_status")=="resolved")
        effective=min(total,resolved_after)
        noisy=max(0,total-effective)
        return {
            "total_escalations":total,"effective":effective,
            "effective_ratio":round(effective/total,3) if total>0 else 0,
            "noisy":noisy,"noisy_ratio":round(noisy/total,3) if total>0 else 0,
            "hours":hours,
        }
    except Exception as e:
        logger.error("escalation eff: %s",e)
        return {"total_escalations":0,"error":str(e)}
