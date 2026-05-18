"""Degradation Calibrator."""
from watch_engine.calibration.sensitivity_profile import get_profile_value
def calibrate_degradation_risk(raw_risk=50,recent_recovery_success=False,spike_duration_minutes=0,is_transient=False):
    decay=get_profile_value("degradation_decay") or 0.5
    tw=get_profile_value("transient_window_sec") or 180
    cal=raw_risk;adj=[]
    if is_transient or spike_duration_minutes<=(tw/60): cal=int(cal*decay);adj.append(f"transient decay x{decay}")
    if recent_recovery_success: cal=max(0,cal-20);adj.append("recovery -20")
    if spike_duration_minutes<=5 and raw_risk<50: cal=max(0,cal-15);adj.append("short spike -15")
    cal=max(0,min(100,cal))
    return {"raw_risk":raw_risk,"calibrated_risk":cal,"reduction":raw_risk-cal,"adjustments":adj,"profile":get_profile_value("label")}
