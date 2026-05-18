"""Alert Quality Tracker."""
import logging
from datetime import datetime,timezone,timedelta
logger=logging.getLogger("watch_engine.feedback.alert")
def track_alert_quality(sb,hours=24):
    since=(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat()
    try:
        alerts=sb.table("alert_history").select("id,rule_code,channel,sent_at,created_at",count="exact").gte("created_at",since).execute()
        total=alerts.count or len(alerts.data or [])
        if total==0: return {"total":0,"meaningful_ratio":0,"noisy_ratio":0,"ignored_ratio":0}
        # integrity_event\uc5d0\uc11c resolved/ignored \ud655\uc778
        ie=sb.table("engine_integrity_event").select("id,resolved,ignored,severity",count="exact").neq("environment","mock").gte("created_at",since).execute()
        ie_total=ie.count or len(ie.data or [])
        resolved=sum(1 for e in (ie.data or []) if e.get("resolved"))
        ignored=sum(1 for e in (ie.data or []) if e.get("ignored"))
        active=ie_total-resolved-ignored
        # meaningful: resolved + active with severity>=WARNING
        warning_plus=sum(1 for e in (ie.data or []) if e.get("severity") in ("WARNING","CRITICAL","FATAL") and not e.get("ignored"))
        meaningful=min(total,warning_plus)
        noisy=max(0,total-meaningful)
        return {
            "total_alerts":total,"total_issues":ie_total,
            "meaningful":meaningful,"meaningful_ratio":round(meaningful/total,3) if total>0 else 0,
            "noisy":noisy,"noisy_ratio":round(noisy/total,3) if total>0 else 0,
            "ignored":ignored,"ignored_ratio":round(ignored/ie_total,3) if ie_total>0 else 0,
            "resolved":resolved,"active":active,"hours":hours,
        }
    except Exception as e:
        logger.error("alert quality: %s",e)
        return {"total_alerts":0,"error":str(e)}
