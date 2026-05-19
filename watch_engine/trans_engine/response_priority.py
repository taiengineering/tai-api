"""Response Priority — 대응 우선순위 계산."""
from __future__ import annotations
from typing import Any

def compute_guidance_level(snapshot: dict[str, Any]) -> str:
    att = snapshot.get("attention_level", "low")
    dt = snapshot.get("delta_type", "")
    status = snapshot.get("status", "")
    if att == "critical" or (dt == "recurring" and status == "escalating"): return "critical"
    if att == "high" or dt == "worsening": return "high"
    if att == "medium" or status in ("active", "emerging"): return "medium"
    return "low"
