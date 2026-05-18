"""Event Store — 검증 통과한 Event 저장.

기존 business_event / engine_integrity_event 재사용.
NOT NULL 컬럼에 기본값 제공.
"""

import logging
import json
from typing import Optional

logger = logging.getLogger("watch_engine.runtime_bus.store")


def store_business_event(sb, ctx, event: dict) -> Optional[str]:
    try:
        row = {
            "tenant_id": event.get("tenant_id") or ctx.tenant_id or "system",
            "environment": ctx.environment or "production",
            "service_key": ctx.service or "tai-api",
            "flow_key": event.get("flow_key") or "",
            "step_key": event.get("step_key") or "",
            "step_order": event.get("step_order") or 0,
            "trace_id": event.get("trace_id") or "",
            "event_type": _map_event_type(event.get("event_type", "")),
            "result": _map_result(event),
            "connector_type": event.get("connector_type") or "api",
        }
        resp = sb.table("business_event").insert(row).execute()
        return resp.data[0]["id"] if resp.data else None
    except Exception as e:
        logger.error("store_business_event failed: %s", e)
        return None


def store_integrity_event(sb, ctx, event: dict) -> Optional[str]:
    try:
        row = {
            "tenant_id": event.get("tenant_id") or ctx.tenant_id or "system",
            "environment": ctx.environment or "production",
            "service_key": ctx.service or "tai-api",
            "flow_key": event.get("flow_key") or "",
            "trace_id": event.get("trace_id") or "",
            "event_type": event.get("event_type") or "",
            "severity": event.get("severity") or "INFO",
            "integrity_status": "recorded",
            "health_status": _severity_to_health(event.get("severity", "INFO")),
            "domain": event.get("flow_key") or "",
            "description": event.get("description") or f"[BUS] {event.get('event_type', '')}",
            "source_trace": event.get("trace_id") or "bus",
            "resolved": False,
            "acknowledged": False,
            "ignored": False,
        }
        if event.get("step_key"):
            row["step_key"] = event["step_key"]
        if event.get("payload"):
            row["detail"] = json.loads(json.dumps(event["payload"], default=str))
        resp = sb.table("engine_integrity_event").insert(row).execute()
        return resp.data[0]["id"] if resp.data else None
    except Exception as e:
        logger.error("store_integrity_event failed: %s", e)
        return None


def _map_event_type(event_type):
    parts = event_type.split(".")
    return parts[-1] if len(parts) >= 2 else event_type


def _map_result(event):
    et = event.get("event_type", "")
    if "failed" in et or "timeout" in et or "blocked" in et:
        return "failure"
    return "success"


def _severity_to_health(severity):
    return {"INFO": "ok", "WARNING": "warning", "CRITICAL": "critical", "FATAL": "critical"}.get(severity, "unknown")
