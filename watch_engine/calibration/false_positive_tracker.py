"""False Positive Tracker."""
import logging
from datetime import datetime,timezone,timedelta
logger=logging.getLogger("watch_engine.calibration.fp")
def analyze_false_positives(sb,hours=24):
    since=(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat()
    try:
        all_ev=sb.table("engine_integrity_event").select("id,resolved,ignored,severity,event_type,created_at",count="exact").neq("environment","mock").gte("created_at",since).execute()
        total=all_ev.count or len(all_ev.data or [])
        if total==0: return {"total":0,"false_positives":0,"ratio":0.0,"categories":{}}
        ignored=sum(1 for e in (all_ev.data or []) if e.get("ignored"))
        transient=sum(1 for e in (all_ev.data or []) if e.get("resolved") and e.get("severity") in ("INFO","WARNING"))
        fp=ignored+transient;ratio=round(fp/total,3) if total>0 else 0.0
        cats={}
        for e in (all_ev.data or []):
            et=e.get("event_type","unknown")
            if et not in cats: cats[et]={"total":0,"fp":0}
            cats[et]["total"]+=1
            if e.get("ignored") or (e.get("resolved") and e.get("severity") in ("INFO","WARNING")): cats[et]["fp"]+=1
        for v in cats.values(): v["ratio"]=round(v["fp"]/v["total"],3) if v["total"]>0 else 0.0
        return {"total":total,"false_positives":fp,"ignored":ignored,"transient_resolved":transient,"ratio":ratio,"categories":dict(sorted(cats.items(),key=lambda x:-x[1]["ratio"])[:10]),"hours":hours}
    except Exception as e:
        logger.error("fp: %s",e)
        return {"total":0,"false_positives":0,"ratio":0.0,"error":str(e)}
