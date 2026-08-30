"""Event Store — persist validated runtime events.

Reuses business_event / engine_integrity_event. Provides defaults for NOT NULL
columns.

§91 A-NARROW: business_event has two physical writers; in THIS store, only an
event with environment == "mock" AND original event_type == "workflow.completed"
is promoted to Common Event Contract v1. Every other event stays legacy. The
canonical contract is built ONLY by the single §90 source
(watch_engine.canonical.build_contract_core); runtime_bus never re-implements a
canonical contract.
"""

import logging
import json
from typing import Optional

from watch_engine.canonical import build_contract_core

logger = logging.getLogger("watch_engine.runtime_bus.store")

# §91 canary boundary — exactly one (environment, event_type) pair is promoted.
CANARY_ENVIRONMENT = "mock"
CANARY_EVENT_TYPE = "workflow.completed"
CANARY_EVENT_NAME = "WORKFLOW_COMPLETED"


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

        # ─── §91 A-NARROW canary: mock workflow.completed → Common Event v1 ───
        # Gate on the ORIGINAL event_type (before _map_event_type) and the
        # sender environment. Only this exact pair is promoted; every other
        # event falls through to the unchanged legacy INSERT below.
        if (
            ctx.environment == CANARY_ENVIRONMENT
            and event.get("event_type") == CANARY_EVENT_TYPE
        ):
            actor_id = getattr(ctx, "actor_id", None)
            actor_ref = f"system:{actor_id}" if actor_id else None

            # §1/§9: reuse the SINGLE §90 canonical source. No runtime_bus-local
            # enum / regex / outcome mapper / version rule.
            core, errors = build_contract_core(
                event_name=CANARY_EVENT_NAME,
                actor_kind="SYSTEM",
                actor_ref=actor_ref,
                trace_id=row["trace_id"],
                service_key=row["service_key"],
                tenant_id=row["tenant_id"],
                environment=row["environment"],
                occurred_at=event.get("occurred_at"),
                outcome="SUCCESS",
            )
            if core is None:
                # v1-or-nothing (§7): do NOT record, do NOT downgrade to legacy.
                logger.warning(
                    "store_business_event: canary workflow.completed canonical "
                    "INVALID → not recorded (no legacy downgrade): %s",
                    errors,
                )
                return None
            # Dual-schema-in-one-row: legacy fields (event_type=completed,
            # result=success, …) stay; canonical v1 core is added.
            row.update(core)

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
