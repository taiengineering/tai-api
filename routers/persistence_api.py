"""TAI Persistence API v1.0.0
Prefix: /persistence
장기 운영 deterministic consistency.
"""
from fastapi import APIRouter,HTTPException,Query
from typing import Optional
from schemas.persistence import SnapshotIn,ReEvalIn,DriftCheckIn,ScheduleInstanceIn
from services import persistence_svc as svc

router=APIRouter(prefix="/persistence",tags=["런타임 지속성"])

@router.post("/snapshots")
def create_snapshot(body:SnapshotIn):
    try:return{"status":"success","data":svc.create_snapshot(body.facility_id,body.evaluation_context_id)}
    except ValueError as e:raise HTTPException(400,str(e))

@router.post("/snapshots/{snapshot_id}/diff")
def compute_diff(snapshot_id:str,body:SnapshotIn):
    try:return{"status":"success","data":svc.compute_diff(body.facility_id,snapshot_id)}
    except ValueError as e:raise HTTPException(400,str(e))

@router.post("/re-evaluate")
def queue_re_eval(body:ReEvalIn):
    try:return{"status":"success","data":svc.queue_re_evaluation(body.facility_id,body.trigger_type,body.trigger_detail)}
    except ValueError as e:raise HTTPException(400,str(e))

@router.get("/re-evaluate/queue")
def list_queue(facility_id:Optional[str]=Query(None),status:Optional[str]=Query(None),page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100)):
    return{"status":"success","data":svc.list_re_evaluation_queue(facility_id,status,page,page_size)}

@router.post("/schedules")
def create_schedule(body:ScheduleInstanceIn):
    try:return{"status":"success","data":svc.create_schedule_instance(body.facility_id,body.schedule_type,body.schedule_key,body.next_due_date,body.schedule_activation_id)}
    except ValueError as e:raise HTTPException(400,str(e))

@router.post("/drift-check")
def check_drift(body:DriftCheckIn):
    return{"status":"success","data":svc.check_drift(body.facility_id)}

@router.get("/history/{facility_id}")
def get_history(facility_id:str):
    return{"status":"success","data":svc.get_facility_history(facility_id)}
