"""Feedback Summary."""
from datetime import datetime,timezone
def generate_feedback_summary(sb,hours=24):
    from watch_engine.feedback_loop.alert_quality_tracker import track_alert_quality
    from watch_engine.feedback_loop.escalation_effectiveness import track_escalation_effectiveness
    from watch_engine.feedback_loop.degradation_feedback import track_degradation_feedback
    from watch_engine.feedback_loop.recovery_feedback import track_recovery_feedback
    from watch_engine.feedback_loop.signal_quality_score import compute_signal_quality
    aq=track_alert_quality(sb,hours)
    eq=track_escalation_effectiveness(sb,hours)
    dq=track_degradation_feedback(sb,hours)
    rq=track_recovery_feedback(sb,hours)
    sq=compute_signal_quality(aq,eq,dq,rq)
    return {
        "alert_quality":aq,"escalation_quality":eq,"degradation_feedback":dq,
        "recovery_feedback":rq,"signal_quality":sq,
        "hours":hours,"generated_at":datetime.now(timezone.utc).isoformat(),
    }
