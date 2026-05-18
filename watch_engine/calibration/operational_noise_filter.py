"""Operational Noise Filter."""
from watch_engine.calibration.sensitivity_profile import get_profile_value
def filter_noise(event_type="",recovery_within_sec=None,is_duplicate=False,retry_count=0,burst_recovered=False):
    if not get_profile_value("noise_suppression"): return {"is_noise":False,"reason":"disabled","action":"none"}
    tw=get_profile_value("transient_window_sec") or 180
    if recovery_within_sec is not None and recovery_within_sec<=tw:
        return {"is_noise":True,"pattern":"transient","action":"severity_downgrade","reason":f"recovery in {recovery_within_sec}s"}
    if is_duplicate: return {"is_noise":True,"pattern":"duplicate","action":"dedupe","reason":"duplicate"}
    if retry_count>=3: return {"is_noise":True,"pattern":"retry_ripple","action":"cooldown","reason":f"retry={retry_count}"}
    if burst_recovered: return {"is_noise":True,"pattern":"burst","action":"delay","reason":"burst recovered"}
    return {"is_noise":False,"action":"none"}
