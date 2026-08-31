"""Degradation Feedback."""
import logging
from datetime import datetime,timezone,timedelta
from services.time import now_kst
logger=logging.getLogger("watch_engine.feedback.degradation")
def track_degradation_feedback(sb,hours=24):
    since=(now_kst()-timedelta(hours=hours)).isoformat()
    try:
        ie=sb.table("engine_integrity_event").select("id,resolved,ignored,severity,event_type").neq("environment","mock").gte("created_at",since).execute()
        total=len(ie.data or [])
        if total==0: return {"total":0,"false_degradation_ratio":0,"confidence":0}
        # false degradation: ignored or quickly resolved with low severity
        false_deg=sum(1 for e in (ie.data or []) if e.get("ignored") or (e.get("resolved") and e.get("severity")=="INFO"))
        true_deg=total-false_deg
        confidence=round(true_deg/total,3) if total>0 else 0
        return {
            "total":total,"true_degradation":true_deg,"false_degradation":false_deg,
            "false_degradation_ratio":round(false_deg/total,3) if total>0 else 0,
            "confidence":confidence,"hours":hours,
        }
    except Exception as e:
        logger.error("deg feedback: %s",e)
        return {"total":0,"error":str(e)}
