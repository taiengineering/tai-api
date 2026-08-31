"""Repeated Failure Detection v1.1 — Production isolation.

v1.1: Mock environment 제외 (TASK 30).
동일 flow_key + event_type 반복 시 repeated_failure / workflow_instability 생성.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from services.time import now_kst

logger = logging.getLogger("watch_engine.incident.repeated")


def detect_repeated_failures(
    sb,
    window_minutes: int = 60,
    now: Optional[datetime] = None,
) -> dict:
    """Detect repeated failures and create aggregated events.

    Returns: {"detected": int, "created": int, "errors": int}
    """
    stats = {"detected": 0, "created": 0, "errors": 0}
    if now is None:
        now = now_kst()

    try:
        since = (now - timedelta(minutes=window_minutes)).isoformat()

        risk_resp = sb.table("workflow_risk_registry") \
            .select("flow_key,repeat_failure_threshold,business_impact_level") \
            .eq("enabled", True).execute()
        risk_map = {r["flow_key"]: r for r in (risk_resp.data or [])}

        # TASK 30: Mock environment 제외
        issues = sb.table("engine_integrity_event") \
            .select("flow_key,event_type,severity,trace_id") \
            .eq("resolved", False).eq("ignored", False) \
            .not_.is_("trace_id", "null") \
            .neq("environment", "mock") \
            .gte("created_at", since) \
            .execute()

        groups = {}
        for i in (issues.data or []):
            key = f"{i['flow_key']}_{i['event_type']}"
            if key not in groups:
                groups[key] = {
                    "flow_key": i["flow_key"],
                    "event_type": i["event_type"],
                    "severity": i["severity"],
                    "count": 0,
                    "traces": set(),
                }
            groups[key]["count"] += 1
            if i.get("trace_id"):
                groups[key]["traces"].add(i["trace_id"])

        for key, group in groups.items():
            fk = group["flow_key"]
            risk = risk_map.get(fk, {})
            threshold = risk.get("repeat_failure_threshold", 5)

            if group["count"] < threshold:
                continue

            stats["detected"] += 1

            existing = sb.table("engine_integrity_event") \
                .select("id") \
                .eq("event_type", "repeated_failure") \
                .eq("flow_key", fk) \
                .gte("created_at", since) \
                .eq("resolved", False) \
                .limit(1).execute()

            if existing.data:
                continue

            flow_event_types = set(
                g["event_type"] for k, g in groups.items()
                if g["flow_key"] == fk and g["count"] >= 2
            )
            is_instability = len(flow_event_types) >= 2

            event_type = "workflow_instability" if is_instability else "repeated_failure"
            sev = "CRITICAL" if is_instability else group["severity"]

            import json
            row = {
                "tenant_id": "tai",
                "environment": "production",
                "service_key": "tai-api",
                "flow_key": fk,
                "trace_id": list(group["traces"])[0] if group["traces"] else None,
                "event_type": event_type,
                "severity": sev,
                "integrity_status": "violation",
                "health_status": "critical" if sev == "CRITICAL" else "warning",
                "domain": fk,
                "description": f"{fk}: {group['event_type']} {group['count']}\ud68c \ubc18\ubcf5 ({window_minutes}\ubd84)"
                    + (f" + {len(flow_event_types)}\uc885 \uc774\uc288 \ubcf5\ud569" if is_instability else ""),
                "detail": json.loads(json.dumps({
                    "flow_key": fk,
                    "base_event_type": group["event_type"],
                    "repeat_count": group["count"],
                    "affected_traces": len(group["traces"]),
                    "threshold": threshold,
                    "is_instability": is_instability,
                    "event_types": list(flow_event_types) if is_instability else None,
                }, default=str)),
                "resolved": False,
            }
            row = {k: v for k, v in row.items() if v is not None}

            try:
                sb.table("engine_integrity_event").insert(row).execute()
                stats["created"] += 1
            except Exception as e:
                logger.error("Failed to create repeated_failure: %s", e)
                stats["errors"] += 1

    except Exception as e:
        logger.error("detect_repeated_failures failed: %s", e)
        stats["errors"] += 1

    return stats
