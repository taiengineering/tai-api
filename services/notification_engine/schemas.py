"""Notification Engine — Pydantic schemas (Event Contract)."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
import uuid


class NotificationEventCreate(BaseModel):
    """Event Contract — 모든 엔진이 이 규약으로 이벤트를 발행한다."""
    event_type: str
    source_engine: str
    severity: str = "INFO"  # INFO / WARNING / CRITICAL
    tenant_id: Optional[str] = None
    trace_id: Optional[str] = None
    payload: dict = Field(default_factory=dict)
    # source entity tracking
    source_domain: str = "unknown"
    source_entity_id: Optional[str] = None
    triggered_by: Optional[str] = None  # user_id (uuid as str)
    notification_required: bool = True
    escalation_required: bool = False

    def to_db_row(self) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "event_type": self.event_type,
            "source_engine": self.source_engine,
            "severity": self.severity,
            "tenant_id": self.tenant_id,
            "trace_id": self.trace_id or f"TRACE-{uuid.uuid4().hex[:12]}",
            "payload": self.payload,
            "source_domain": self.source_domain,
            "source_entity_id": self.source_entity_id,
            "triggered_by": self.triggered_by,
            "notification_required": self.notification_required,
            "escalation_required": self.escalation_required,
            "event_status": "PENDING",
            "occurred_at": now,
            "source_trace": "NOTIFICATION_ENGINE",
        }


class QueueItem(BaseModel):
    """Queue에 들어갈 항목."""
    runtime_event_id: str
    recipient_user_id: str
    notification_type: str
    delivery_channel: str = "TELEGRAM"
    message_title: str = ""
    message_body: str = ""
    dedupe_key: Optional[str] = None
    escalation_level: int = 0
