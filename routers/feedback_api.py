"""Feedback API."""
import logging
from fastapi import APIRouter
logger=logging.getLogger(__name__)
router=APIRouter(prefix="/feedback",tags=["\ud53c\ub4dc\ubc31"])
def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()
@router.get("/alert-quality")
def alert_q(hours:int=24):
    from watch_engine.feedback_loop import track_alert_quality
    return {"status":"success","data":track_alert_quality(_sb(),hours)}
@router.get("/escalation-quality")
def esc_q(hours:int=24):
    from watch_engine.feedback_loop import track_escalation_effectiveness
    return {"status":"success","data":track_escalation_effectiveness(_sb(),hours)}
@router.get("/degradation-feedback")
def deg_q(hours:int=24):
    from watch_engine.feedback_loop import track_degradation_feedback
    return {"status":"success","data":track_degradation_feedback(_sb(),hours)}
@router.get("/recovery-feedback")
def rec_q(hours:int=24):
    from watch_engine.feedback_loop import track_recovery_feedback
    return {"status":"success","data":track_recovery_feedback(_sb(),hours)}
@router.get("/signal-quality")
def sig_q(hours:int=24):
    from watch_engine.feedback_loop import generate_feedback_summary
    return {"status":"success","data":generate_feedback_summary(_sb(),hours)}
@router.get("/summary")
def summary(hours:int=24):
    from watch_engine.feedback_loop import generate_feedback_summary
    s=generate_feedback_summary(_sb(),hours)
    sq=s.get("signal_quality",{})
    return {"status":"success","data":{
        "overall_score":sq.get("overall",0),
        "alert_quality":sq.get("alert_quality",0),
        "noise_ratio":sq.get("noise_ratio",0),
        "escalation_quality":sq.get("escalation_quality",0),
        "recovery_quality":sq.get("recovery_quality",0),
        "stability_accuracy":sq.get("stability_accuracy",0),
        "hours":hours,
    }}
