"""Repeated Failure Intelligence.

\ub3d9\uc77c flow/step/event \ubc18\ubcf5 \ud0d0\uc9c0 + \ucd94\uc138 \ubd84\uc11d.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from watch_engine.intelligence.intelligence_result import IntelligenceResult

logger = logging.getLogger("watch_engine.intelligence.repeated")


def analyze_repeated_failures(
    sb, hours: int = 24, now: Optional[datetime] = None,
) -> list[IntelligenceResult]:
    if now is None:
        now = datetime.now(timezone.utc)
    since = (now - timedelta(hours=hours)).isoformat()

    try:
        events = sb.table("engine_integrity_event") \
            .select("flow_key,event_type,severity,tenant_id,trace_id,created_at") \
            .eq("resolved", False).eq("ignored", False) \
            .neq("environment", "mock") \
            .not_.is_("trace_id", "null") \
            .gte("created_at", since).execute()

        # flow_key + event_type \uadf8\ub8f9\ud654
        groups = {}
        for e in (events.data or []):
            key = f"{e.get('flow_key', '')}:{e.get('event_type', '')}"
            if key not in groups:
                groups[key] = {"flow_key": e["flow_key"], "event_type": e["event_type"],
                               "count": 0, "tenants": set(), "traces": set(),
                               "severities": [], "times": []}
            g = groups[key]
            g["count"] += 1
            if e.get("tenant_id"): g["tenants"].add(e["tenant_id"])
            if e.get("trace_id"): g["traces"].add(e["trace_id"])
            g["severities"].append(e.get("severity", "WARNING"))
            if e.get("created_at"): g["times"].append(e["created_at"])

        results = []
        for key, g in groups.items():
            if g["count"] < 3:
                continue

            critical_ratio = g["severities"].count("CRITICAL") / len(g["severities"]) if g["severities"] else 0
            tenant_spread = len(g["tenants"])
            risk = min(100, g["count"] * 8 + int(critical_ratio * 40) + tenant_spread * 10)
            confidence = min(1.0, g["count"] / 10)

            sev = "CRITICAL" if risk >= 70 else "WARNING" if risk >= 30 else "INFO"

            results.append(IntelligenceResult(
                intelligence_type="repeated_failure",
                severity=sev,
                risk_score=risk,
                confidence=round(confidence, 2),
                summary=f"{g['flow_key']}: {g['event_type']} {g['count']}\ud68c \ubc18\ubcf5 ({hours}h), {tenant_spread} tenant \uc601\ud5a5",
                recommendations=_recommend(g),
                evidence=[{"flow_key": g["flow_key"], "event_type": g["event_type"],
                           "count": g["count"], "tenant_count": tenant_spread,
                           "critical_ratio": round(critical_ratio, 2)}],
            ))

        results.sort(key=lambda r: r.risk_score, reverse=True)
        return results

    except Exception as e:
        logger.error("analyze_repeated_failures failed: %s", e)
        return []


def _recommend(g: dict) -> list:
    recs = []
    et = g["event_type"]
    if "field_mismatch" in et:
        recs.append("schema_reload \ub610\ub294 \ud544\ub4dc \ub9e4\ud551 \ud655\uc778")
    if "timeout" in et:
        recs.append("timeout \uc784\uacc4\uac12 \uc870\uc815 \ub610\ub294 \uc11c\ubc84 \uc131\ub2a5 \ud655\uc778")
    if "selector" in et or "button" in et:
        recs.append("\ud504\ub860\ud2b8\uc5d4\ub4dc UI \ubcc0\uacbd \ud655\uc778 + selector \uc5c5\ub370\uc774\ud2b8")
    if "sla" in et:
        recs.append("SLA \uc784\uacc4\uac12 \uc870\uc815 \ub610\ub294 \ud504\ub85c\uc138\uc2a4 \ucd5c\uc801\ud654")
    if g["count"] >= 10:
        recs.append("\ubc18\ubcf5 \ube48\ub3c4 \ub192\uc74c \u2014 \uadfc\ubcf8 \uc6d0\uc778 \uc870\uc0ac \ud544\uc694")
    if len(g["tenants"]) > 2:
        recs.append("\ub2e4\uc218 tenant \uc601\ud5a5 \u2014 \ud50c\ub7ab\ud3fc \uc218\uc900 \uc774\uc288 \uac00\ub2a5\uc131")
    if not recs:
        recs.append("\ud574\ub2f9 flow/step \ub85c\uadf8 \ud655\uc778")
    return recs
