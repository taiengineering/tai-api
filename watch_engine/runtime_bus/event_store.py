"""Event Store — \uac80\uc99d \ud1b5\uacfc\ud55c Event \uc800\uc7a5.

\ucd08\uae30\uc5d0\ub294 \uae30\uc874 business_event / engine_integrity_event \uc7ac\uc0ac\uc6a9.
Runtime Bus \ub0b4\ubd80\uc5d0\uc11c\ub9cc \uc800\uc7a5.
"""

import logging
import json
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("watch_engine.runtime_bus.store")


def store_business_event(sb, ctx, event: dict) -> Optional[str]:
    """business_event \ud14c\uc774\ube14\uc5d0 \uc800\uc7a5."""
    try:
        row = {
            "tenant_id": event.get("tenant_id") or ctx.tenant_id,
            "environment": ctx.environment,
            "service_key": ctx.service,
            "flow_key": event.get("flow_key", ""),
            "step_key": event.get("step_key"),
            "step_order": event.get("step_order"),
            "trace_id": event.get("trace_id"),
            "event_type": _map_event_type(event.get("event_type", "")),
            "result": _map_result(event),
            "connector_type": event.get("connector_type", "api"),
            "actor_id": event.get("actor_id") or ctx.actor_id or "system",
        }
        row = {k: v for k, v in row.items() if v is not None}
        resp = sb.table("business_event").insert(row).execute()
        return resp.data[0]["id"] if resp.data else None
    except Exception as e:
        logger.error("store_business_event failed: %s", e)
        return None


def store_integrity_event(sb, ctx, event: dict) -> Optional[str]:
    """engine_integrity_event \ud14c\uc774\ube14\uc5d0 \uc800\uc7a5."""
    try:
        row = {
            "tenant_id": event.get("tenant_id") or ctx.tenant_id or "system",
            "environment": ctx.environment,
            "service_key": ctx.service,
            "flow_key": event.get("flow_key", ""),
            "step_key": event.get("step_key"),
            "trace_id": event.get("trace_id"),
            "event_type": event.get("event_type", ""),
            "severity": event.get("severity", "INFO"),
            "integrity_status": "recorded",
            "health_status": _severity_to_health(event.get("severity", "INFO")),
            "domain": event.get("flow_key", ""),
            "description": event.get("description") or f"[BUS] {event.get('event_type', '')}",
            "detail": json.loads(json.dumps(event.get("payload", {}), default=str)) if event.get("payload") else None,
            "resolved": False,
        }
        row = {k: v for k, v in row.items() if v is not None}
        resp = sb.table("engine_integrity_event").insert(row).execute()
        return resp.data[0]["id"] if resp.data else None
    except Exception as e:
        logger.error("store_integrity_event failed: %s", e)
        return None


def _map_event_type(event_type: str) -> str:
    """Canonical event_type \u2192 business_event \ud638\ud658 \ub9e4\ud551."""
    parts = event_type.split(".")
    if len(parts) >= 2:
        return parts[-1]  # workflow.failed -> failed
    return event_type


def _map_result(event: dict) -> str:
    et = event.get("event_type", "")
    if "failed" in et or "timeout" in et or "blocked" in et:
        return "failure"
    return "success"


def _severity_to_health(severity: str) -> str:
    return {
        "INFO": "ok",
        "WARNING": "warning",
        "CRITICAL": "critical",
        "FATAL": "critical",
    }.get(severity, "unknown")
