"""Calibration API."""
import logging
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel
logger=logging.getLogger(__name__)
router=APIRouter(prefix="/calibration",tags=["Calibration"])
def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()
@router.get("/profile")
def get_profile():
    from watch_engine.calibration.sensitivity_profile import get_active_profile,PROFILES
    return {"status":"success","data":{"active":get_active_profile(),"available":{k:v["label"] for k,v in PROFILES.items()}}}
class ProfP(BaseModel):
    name:str
@router.post("/profile")
def set_profile(body:ProfP):
    from watch_engine.calibration.sensitivity_profile import set_active_profile
    try: return {"status":"success","data":set_active_profile(body.name)}
    except ValueError as e: raise HTTPException(400,str(e))
@router.get("/false-positives")
def get_fp(hours:int=24):
    from watch_engine.calibration.false_positive_tracker import analyze_false_positives
    return {"status":"success","data":analyze_false_positives(_sb(),hours=hours)}
@router.get("/escalation-check")
def esc_check(repeated_count:int=0,tenant_spread:int=1,degradation_trending:bool=False,recovery_failed:bool=False,duration_minutes:int=0):
    from watch_engine.calibration.escalation_calibrator import should_escalate
    return {"status":"success","data":should_escalate(repeated_count,tenant_spread,degradation_trending,recovery_failed,duration_minutes)}
@router.get("/degradation-check")
def deg_check(raw_risk:int=50,recent_recovery:bool=False,spike_minutes:int=0,is_transient:bool=False):
    from watch_engine.calibration.degradation_calibrator import calibrate_degradation_risk
    return {"status":"success","data":calibrate_degradation_risk(raw_risk,recent_recovery,spike_minutes,is_transient)}
@router.get("/repeated-check")
def rep_check(count:int=3,density_per_hour:float=1.0,tenant_diversity:int=1,has_recovery:bool=False,importance:str="normal"):
    from watch_engine.calibration.repeated_failure_calibrator import calibrate_repeated_threshold
    return {"status":"success","data":calibrate_repeated_threshold(count,density_per_hour,tenant_diversity,has_recovery,importance)}
@router.get("/noise-check")
def noise_check(event_type:str="workflow.timeout",recovery_sec:int=None,is_duplicate:bool=False,retry_count:int=0,burst_recovered:bool=False):
    from watch_engine.calibration.operational_noise_filter import filter_noise
    return {"status":"success","data":filter_noise(event_type,recovery_sec,is_duplicate,retry_count,burst_recovered)}
@router.get("/summary")
def summary(hours:int=24):
    from watch_engine.calibration.sensitivity_profile import get_active_profile
    from watch_engine.calibration.false_positive_tracker import analyze_false_positives
    fp=analyze_false_positives(_sb(),hours=hours);p=get_active_profile()
    return {"status":"success","data":{"profile":p,"false_positive_ratio":fp.get("ratio",0),"false_positives":fp.get("false_positives",0),"total_events":fp.get("total",0),"top_fp_categories":list(fp.get("categories",{}).keys())[:5]}}
