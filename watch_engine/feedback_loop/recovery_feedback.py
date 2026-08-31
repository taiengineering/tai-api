"""Recovery Feedback."""
import logging
from datetime import datetime,timezone,timedelta
from services.time import now_kst
logger=logging.getLogger("watch_engine.feedback.recovery")
def track_recovery_feedback(sb,hours=24):
    since=(now_kst()-timedelta(hours=hours)).isoformat()
    try:
        actions=sb.table("incident_action_log").select("id,action_type,outcome_status").gte("created_at",since).execute()
        recovery_actions=[a for a in (actions.data or []) if a.get("action_type") in ("RECOVERY","RECOVERED","RETRY","FIX")]
        total=len(recovery_actions)
        if total==0:
            # fallback: \uc804\uccb4 action \uc911 resolved
            all_actions=actions.data or []
            resolved=sum(1 for a in all_actions if a.get("outcome_status")=="resolved")
            return {"total_actions":len(all_actions),"resolved":resolved,"recovery_actions":0,"effectiveness":round(resolved/len(all_actions),3) if all_actions else 0,"hours":hours}
        successful=sum(1 for a in recovery_actions if a.get("outcome_status")=="resolved")
        failed=total-successful
        return {
            "total_actions":len(actions.data or []),"recovery_actions":total,
            "successful":successful,"failed":failed,
            "effectiveness":round(successful/total,3) if total>0 else 0,
            "hours":hours,
        }
    except Exception as e:
        logger.error("recovery feedback: %s",e)
        return {"recovery_actions":0,"error":str(e)}
