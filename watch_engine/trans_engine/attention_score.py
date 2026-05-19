"""Attention Score — 상황 중요도 계산.

6요소: priority(30%) + worsening(20%) + recurrence(15%)
       + tenant_spread(15%) + customer_impact(10%) + acceleration(10%)
"""
from __future__ import annotations
from typing import Any

_P_SCORE = {"P1": 1.0, "P2": 0.7, "P3": 0.4, "P4": 0.1}

def compute_attention_score(snapshot: dict[str, Any]) -> dict[str, Any]:
    priority = _P_SCORE.get(snapshot.get("priority", "P4"), 0.1)
    dt = snapshot.get("delta_type", "")
    status = snapshot.get("status", "")
    worsening = 1.0 if dt == "worsening" or status == "escalating" else (0.5 if status == "active" else 0.0)
    recurrence = 1.0 if dt == "recurring" else 0.0
    tenant_id = snapshot.get("tenant_id", "")
    spread = 0.5 if tenant_id and tenant_id != "system" else 0.0
    sid = snapshot.get("situation_id", "")
    parts = sid.split(":")
    domain = parts[1] if len(parts) >= 2 else ""
    cust_domains = {"payment", "subscription", "document", "diagnosis"}
    customer = 1.0 if domain in cust_domains else 0.3
    trend = snapshot.get("trend", "stable")
    accel = 1.0 if trend == "accelerating" else (0.6 if trend == "degrading" else 0.0)

    score = round(
        priority * 0.30 + worsening * 0.20 + recurrence * 0.15
        + spread * 0.15 + customer * 0.10 + accel * 0.10, 3
    )

    if score >= 0.75: level = "critical"
    elif score >= 0.50: level = "high"
    elif score >= 0.25: level = "medium"
    else: level = "low"

    immediate = _check_immediate(snapshot, score)
    reasons = _build_reasons(snapshot, priority, worsening, recurrence, accel)

    return {
        "attention_score": score,
        "attention_level": level,
        "attention_reasons": reasons,
        "requires_immediate_attention": immediate,
        "recommended_focus_time": "즉시" if immediate else ("우선" if level in ("critical","high") else "관찰"),
        "factors": {"priority": priority, "worsening": worsening, "recurrence": recurrence,
                    "spread": spread, "customer": customer, "acceleration": accel},
    }

def _check_immediate(s: dict, score: float) -> bool:
    if s.get("priority") == "P1" and s.get("delta_type") == "worsening": return True
    if s.get("delta_type") == "recurring" and s.get("status") == "escalating": return True
    if s.get("trend") == "accelerating" and s.get("priority") in ("P1", "P2"): return True
    if score >= 0.80: return True
    return False

def _build_reasons(s: dict, p: float, w: float, r: float, a: float) -> list[str]:
    reasons = []
    if p >= 0.7: reasons.append("높은 우선순위 상황입니다")
    if w >= 0.5: reasons.append("상황이 악화되고 있습니다")
    if r >= 1.0: reasons.append("이전 문제가 재발하고 있습니다")
    if a >= 0.6: reasons.append("문제 증가 속도가 빠르다")
    if not reasons: reasons.append("운영 상황 모니터링 중입니다")
    return reasons
