"""EventEnvelope MVP — Wrapper over existing event_bus.

Does NOT replace event_bus.py. Wraps it with
tenant_id + trace_id + idempotency_key contract.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    """Canonical event wrapper for all TAI runtime events."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str  # e.g. "legal.obligation_detected", "runtime.task_created"
    tenant_id: str
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: str  # "legal_engine" | "runtime" | "notification" | ...
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = None


# ---------------------------------------------------------------------------
# Adapter helpers — emit via existing runtime_bus without replacing it
# ---------------------------------------------------------------------------

def create_envelope(
    event_type: str,
    tenant_id: str,
    source: str,
    payload: dict[str, Any],
    *,
    trace_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> EventEnvelope:
    """Factory for creating a well-formed EventEnvelope."""
    return EventEnvelope(
        event_type=event_type,
        tenant_id=tenant_id,
        source=source,
        payload=payload,
        trace_id=trace_id or str(uuid.uuid4()),
        idempotency_key=idempotency_key,
    )


async def emit_envelope(envelope: EventEnvelope) -> None:
    """Persist envelope to runtime_event_log (Supabase) for downstream consumers.

    Phase-1: direct INSERT.  Phase-2: route through event_bus subscriptions.
    """
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        sb.table("runtime_event_log").insert({
            "event_id": envelope.event_id,
            "event_type": envelope.event_type,
            "tenant_id": envelope.tenant_id,
            "trace_id": envelope.trace_id,
            "source": envelope.source,
            "payload": envelope.payload,
            "idempotency_key": envelope.idempotency_key,
            "created_at": envelope.timestamp.isoformat(),
        }).execute()
    except Exception:
        # Phase-1: log-only, never block caller
        import logging
        logging.getLogger(__name__).warning(
            "emit_envelope failed for %s", envelope.event_type, exc_info=True
        )
