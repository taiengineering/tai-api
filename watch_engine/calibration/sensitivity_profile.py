"""Sensitivity Profile."""
PROFILES={"CONSERVATIVE":{"label":"\ubcf4\uc218\uc801","warning_threshold":5,"critical_threshold":15,"repeated_min_count":5,"escalation_min_count":8,"degradation_decay":0.7,"transient_window_sec":300,"cooldown_multiplier":2.0,"noise_suppression":True},"BALANCED":{"label":"\uade0\ud615","warning_threshold":3,"critical_threshold":10,"repeated_min_count":3,"escalation_min_count":5,"degradation_decay":0.5,"transient_window_sec":180,"cooldown_multiplier":1.0,"noise_suppression":True},"AGGRESSIVE":{"label":"\ubbfc\uac10","warning_threshold":1,"critical_threshold":5,"repeated_min_count":2,"escalation_min_count":3,"degradation_decay":0.3,"transient_window_sec":60,"cooldown_multiplier":0.5,"noise_suppression":False}}
_active_profile="BALANCED"
def get_active_profile():
    return {"name":_active_profile,**PROFILES[_active_profile]}
def set_active_profile(name):
    global _active_profile
    if name not in PROFILES: raise ValueError(f"Invalid: {name}")
    _active_profile=name
    return get_active_profile()
def get_profile_value(key):
    return PROFILES[_active_profile].get(key)
