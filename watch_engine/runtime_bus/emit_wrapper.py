"""emit_event Wrapper — \uae30\uc874 emit_event\ub97c Runtime Bus\ub85c \uc810\uc9c4 \uc5f0\uacb0.

\uae30\uc874 emit_event interface \uc720\uc9c0\ud558\uba74\uc11c
Runtime Bus\ub97c \uacbd\uc720\ud558\ub3c4\ub85d \ub798\ud551.

\uc0ac\uc6a9\ubc95:
    from watch_engine.runtime_bus.emit_wrapper import emit_event_via_bus

    # \uae30\uc874 emit_event \ub300\uccb4
    emit_event_via_bus(
        step_key="save_db",
        step_order=2,
        event_type="submit",
        result="success",
        connector_type="api",
        flow_key="process_registration",
        tenant_id="tai",
        trace_id="procreg_123",
    )
"""

import logging
from typing import Optional

logger = logging.getLogger("watch_engine.runtime_bus.wrapper")


def emit_event_via_bus(
    step_key: str,
    step_order: int = 0,
    event_type: str = "submit",
    result: str = "success",
    connector_type: str = "api",
    flow_key: str = "",
    tenant_id: str = None,
    trace_id: str = None,
    actor_id: str = None,
    payload_summary: dict = None,
    environment: str = "production",
) -> dict:
    """\uae30\uc874 emit_event \uc2dc\uadf8\ub2c8\ucc98 \u2192 Runtime Bus \ub798\ud551.

    Returns: EventResult.to_dict()
    """
    try:
        from watch_engine.runtime_bus import emit_runtime_event, make_context

        # \uae30\uc874 result \u2192 Canonical event_type \ub9e4\ud551
        canonical = _map_to_canonical(flow_key, step_key, event_type, result)
        severity = "INFO" if result == "success" else "WARNING"

        ctx = make_context(
            runtime="workflow",
            tenant_id=tenant_id,
            actor_id=actor_id,
            environment=environment,
        )

        event = {
            "event_type": canonical,
            "flow_key": flow_key,
            "step_key": step_key,
            "step_order": step_order,
            "trace_id": trace_id,
            "severity": severity,
            "tenant_id": tenant_id,
            "connector_type": connector_type,
            "payload": payload_summary,
        }
        event = {k: v for k, v in event.items() if v is not None}

        r = emit_runtime_event(ctx, event)
        return r.to_dict()

    except Exception as e:
        logger.warning("emit_event_via_bus failed (non-blocking): %s", e)
        return {"status": "failed", "error": str(e)}


def _map_to_canonical(flow_key: str, step_key: str, event_type: str, result: str) -> str:
    """\uae30\uc874 event \ud30c\ub77c\ubbf8\ud130 \u2192 Canonical event_type."""
    if result == "success":
        if step_key and event_type == "read":
            return "step.completed"
        return "workflow.completed" if not step_key else "step.completed"
    elif result == "failure":
        return "workflow.failed" if not step_key else "step.failed"
    elif result == "timeout":
        return "workflow.timeout"
    elif result == "blocked":
        return "workflow.blocked"
    else:
        return f"workflow.{result}" if not step_key else f"step.{result}"
