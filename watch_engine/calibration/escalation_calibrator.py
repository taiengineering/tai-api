"""Escalation Calibrator."""
from watch_engine.calibration.sensitivity_profile import get_profile_value
def should_escalate(repeated_count=0,tenant_spread=1,degradation_trending=False,recovery_failed=False,duration_minutes=0):
    min_c=get_profile_value("escalation_min_count") or 5
    score=0;reasons=[]
    if repeated_count>=min_c: score+=30;reasons.append(f"repeated {repeated_count}\ud68c")
    if tenant_spread>=3: score+=25;reasons.append(f"tenant {tenant_spread}\uac1c")
    if degradation_trending: score+=20;reasons.append("degradation")
    if recovery_failed: score+=15;reasons.append("recovery \uc2e4\ud328")
    if duration_minutes>=30: score+=10;reasons.append(f"{duration_minutes}\ubd84 \uc9c0\uc18d")
    return {"should_escalate":score>=50,"score":score,"threshold":50,"reasons":reasons,"profile":get_profile_value("label")}
