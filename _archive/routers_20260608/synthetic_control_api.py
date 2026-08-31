"""Synthetic Runtime Control API."""
import logging
from datetime import datetime,timezone,timedelta
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel
from services.time import now_kst, serialize_external_utc
logger=logging.getLogger(__name__)
router=APIRouter(prefix="/synthetic",tags=["Synthetic"])
def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()
_state={"enabled":False,"intensity":"normal","started_at":None,"ticks":0,"events":0,"last_tick":None,"last_stats":None}
INTENSITY={"low":{"chaos":0.05,"label":"\ub0ae\uc74c"},"normal":{"chaos":0.15,"label":"\ubcf4\ud1b5"},"high":{"chaos":0.30,"label":"\ub192\uc74c"},"extreme":{"chaos":0.50,"label":"\uadf9\ud55c"}}
SYN_JOBS=["SYNTHETIC_RUNTIME_TICK","SYNTHETIC_CHAOS_INJECTION","CONTROL_BRIDGE_EVALUATE"]
@router.get("/status")
def status():
    sb=_sb();cron={};recent=[]
    try:
        j=sb.table("cron_job_master").select("job_code,is_active").in_("job_code",SYN_JOBS).execute()
        cron={x["job_code"]:x["is_active"] for x in (j.data or [])}
        l=sb.table("cron_job_log").select("job_code,status,started_at,duration_seconds").in_("job_code",SYN_JOBS).order("started_at",desc=True).limit(9).execute()
        recent=l.data or []
    except: pass
    return {"status":"success","data":{**_state,"intensity_config":INTENSITY.get(_state["intensity"],{}),"cron_active":cron,"scheduler_recent":recent}}
class StartP(BaseModel):
    intensity:str="normal"
@router.post("/start")
def start(body:StartP):
    if body.intensity not in INTENSITY: raise HTTPException(400,f"Invalid: {body.intensity}")
    sb=_sb()
    for c in SYN_JOBS: sb.table("cron_job_master").update({"is_active":True}).eq("job_code",c).execute()
    try:
        from scheduler import load_jobs_from_db,scheduler as aps
        load_jobs_from_db()
        if not aps.running: aps.start()
    except Exception as e: logger.error("reload: %s",e)
    _state.update(enabled=True,intensity=body.intensity,started_at=serialize_external_utc(now_kst()))
    return {"status":"success","message":f"Synthetic Runtime \uc2dc\uc791\ub428 (intensity={body.intensity})"}
@router.post("/stop")
def stop():
    sb=_sb()
    for c in ["SYNTHETIC_RUNTIME_TICK","SYNTHETIC_CHAOS_INJECTION"]: sb.table("cron_job_master").update({"is_active":False}).eq("job_code",c).execute()
    try:
        from scheduler import load_jobs_from_db
        load_jobs_from_db()
    except: pass
    _state["enabled"]=False
    return {"status":"success","message":"Synthetic Runtime \uc815\uc9c0\ub428"}
class IntP(BaseModel):
    intensity:str
@router.post("/intensity")
def set_int(body:IntP):
    if body.intensity not in INTENSITY: raise HTTPException(400,f"Invalid: {body.intensity}")
    _state["intensity"]=body.intensity
    return {"status":"success","intensity":body.intensity,"config":INTENSITY[body.intensity]}
@router.post("/tick")
def tick():
    try:
        from watch_engine.synthetic_runtime.orchestrator import run_synthetic_tick
        s=run_synthetic_tick()
        _state["ticks"]+=1;_state["events"]+=s.get("events",0);_state["last_tick"]=serialize_external_utc(now_kst());_state["last_stats"]=s
        return {"status":"success","data":s}
    except Exception as e: raise HTTPException(500,str(e))
@router.post("/bridge")
def bridge():
    try:
        from watch_engine.control_bridge.bridge_evaluator import evaluate_bridge
        return {"status":"success","data":evaluate_bridge(window_minutes=5,include_mock=True)}
    except Exception as e: raise HTTPException(500,str(e))
@router.get("/stats")
def stats(hours:int=24):
    sb=_sb();since=(now_kst()-timedelta(hours=hours)).isoformat()
    be=sb.table("business_event").select("id",count="exact").eq("environment","mock").gte("created_at",since).execute()
    ie=sb.table("engine_integrity_event").select("id",count="exact").eq("environment","mock").gte("created_at",since).execute()
    return {"status":"success","data":{"hours":hours,"business_events":be.count or 0,"integrity_events":ie.count or 0,"total":(be.count or 0)+(ie.count or 0)}}
class CleanP(BaseModel):
    hours_to_keep:int=24
@router.post("/cleanup")
def cleanup(body:CleanP):
    sb=_sb();cutoff=(now_kst()-timedelta(hours=body.hours_to_keep)).isoformat()
    bd=sb.table("business_event").delete().eq("environment","mock").lt("created_at",cutoff).execute()
    ie=sb.table("engine_integrity_event").delete().eq("environment","mock").lt("created_at",cutoff).execute()
    return {"status":"success","data":{"be_deleted":len(bd.data or []),"ie_deleted":len(ie.data or [])}}
