"""Repeated Failure Calibrator."""
from watch_engine.calibration.sensitivity_profile import get_profile_value
def calibrate_repeated_threshold(count=3,time_density_per_hour=0.0,tenant_diversity=1,has_recovery=False,workflow_importance="normal"):
    min_c=get_profile_value("repeated_min_count") or 3
    eff=min_c;adj=[]
    if time_density_per_hour<1.0 and count<10: eff+=2;adj.append("low density +2")
    if has_recovery: eff+=1;adj.append("recovery +1")
    if workflow_importance=="critical": eff=max(2,eff-2);adj.append("critical wf -2")
    if tenant_diversity>=3: eff=max(2,eff-1);adj.append(f"multi-tenant -1")
    return {"count":count,"base_threshold":min_c,"effective_threshold":eff,"is_repeated":count>=eff,"adjustments":adj,"profile":get_profile_value("label")}
