"""Tenant Degradation Intelligence.

\ud14c\ub10c\ud2b8 \uc0c1\ud0dc \uc545\ud654 \uc870\uae30 \uac10\uc9c0. \ucd94\uc138 \uae30\ubc18.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from watch_engine.intelligence.intelligence_result import IntelligenceResult
from services.time import now_kst

logger = logging.getLogger("watch_engine.intelligence.degradation")


def analyze_tenant_degradation(
    sb, hours: int = 24, now: Optional[datetime] = None,
) -> list[IntelligenceResult]:
    if now is None:
        now = now_kst()
    since = (now - timedelta(hours=hours)).isoformat()

    try:
        events = sb.table("engine_integrity_event") \
            .select("tenant_id,event_type,severity,resolved") \
            .neq("environment", "mock") \
            .not_.is_("trace_id", "null") \
            .gte("created_at", since).execute()

        tenants = {}
        for e in (events.data or []):
            tid = e.get("tenant_id", "unknown")
            if tid.startswith("mock_"):
                continue
            if tid not in tenants:
                tenants[tid] = {"total": 0, "critical": 0, "active": 0,
                                "sla": 0, "repeated": 0, "types": set()}
            t = tenants[tid]
            t["total"] += 1
            if not e.get("resolved"): t["active"] += 1
            if e.get("severity") == "CRITICAL": t["critical"] += 1
            et = e.get("event_type", "")
            if "sla" in et: t["sla"] += 1
            if "repeated" in et or "instability" in et: t["repeated"] += 1
            t["types"].add(et)

        # \uae30\uc874 registry\uc5d0\uc11c \uc774\uc804 \uc0c1\ud0dc \ucc38\uc870
        reg = sb.table("tenant_operational_registry") \
            .select("tenant_id,stability_status,escalation_level") \
            .not_.like("tenant_id", "mock_%").execute()
        prev = {r["tenant_id"]: r for r in (reg.data or [])}

        results = []
        for tid, t in tenants.items():
            risk = min(100,
                t["active"] * 5 +
                t["critical"] * 15 +
                t["sla"] * 10 +
                t["repeated"] * 12 +
                len(t["types"]) * 3
            )

            if risk < 10:
                continue

            p = prev.get(tid, {})
            prev_status = p.get("stability_status", "HEALTHY")
            status_order = {"HEALTHY": 0, "WATCH": 1, "RISK": 2, "CRITICAL": 3}
            curr_status = "CRITICAL" if risk >= 60 else "RISK" if risk >= 35 else "WATCH" if risk >= 15 else "HEALTHY"
            degrading = status_order.get(curr_status, 0) > status_order.get(prev_status, 0)

            sev = "CRITICAL" if degrading and risk >= 50 else "WARNING" if risk >= 25 else "INFO"
            confidence = min(1.0, t["total"] / 8)

            results.append(IntelligenceResult(
                intelligence_type="tenant_degradation",
                severity=sev,
                risk_score=risk,
                confidence=round(confidence, 2),
                summary=f"{tid}: {prev_status}\u2192{curr_status} (active {t['active']}, critical {t['critical']}, {hours}h)"
                    + (" \u26a0\ufe0f \uc545\ud654 \ucd94\uc138" if degrading else ""),
                recommendations=_degradation_recommend(t, degrading),
                evidence=[{"tenant_id": tid, "prev_status": prev_status, "curr_status": curr_status,
                           "degrading": degrading, **{k: v for k, v in t.items() if k != "types"},
                           "event_types": list(t["types"])}],
            ))

        results.sort(key=lambda r: r.risk_score, reverse=True)
        return results

    except Exception as e:
        logger.error("analyze_tenant_degradation failed: %s", e)
        return []


def _degradation_recommend(t: dict, degrading: bool) -> list:
    recs = []
    if degrading:
        recs.append("\ud14c\ub10c\ud2b8 \uc0c1\ud0dc \uc545\ud654 \uc911 \u2014 \uc6b0\uc120 \ub300\uc751 \ud544\uc694")
    if t["critical"] >= 3:
        recs.append(f"CRITICAL \uc774\uc288 {t['critical']}\uac74 \u2014 \uc989\uc2dc \uc870\uc0ac")
    if t["sla"] >= 2:
        recs.append(f"SLA \uc704\ubc18 {t['sla']}\uac74 \u2014 \ud504\ub85c\uc138\uc2a4 \ucd5c\uc801\ud654 \uac80\ud1a0")
    if t["repeated"] >= 1:
        recs.append("\ubc18\ubcf5 \uc2e4\ud328 \ubc1c\uc0dd \u2014 \uadfc\ubcf8 \uc6d0\uc778 \uc870\uc0ac")
    if not recs:
        recs.append("\ud14c\ub10c\ud2b8 \ubaa8\ub2c8\ud130\ub9c1 \uc9c0\uc18d")
    return recs
