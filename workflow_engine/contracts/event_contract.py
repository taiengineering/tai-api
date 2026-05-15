"""Workflow Event Contract — Workflow Engine ↔ Platform Event 규약.

모든 Workflow 상태 변화는 이 규약을 따라 Event를 발행한다.
Workflow Engine은 직접 Notification을 호출하지 않는다.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
import uuid


class WorkflowEventContract(BaseModel):
    """Workflow Engine ↔ Platform Event 규약."""
    workflow_id: str
    workflow_type: str
    workflow_state: str  # to_state
    from_state: Optional[str] = None
    event_type: str
    transition: Optional[str] = None
    trace_id: Optional[str] = None
    tenant_id: Optional[str] = None
    triggered_by: Optional[str] = None
    occurred_at: Optional[str] = None
    payload: dict = Field(default_factory=dict)

    def to_event_log_row(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "workflow_type": self.workflow_type,
            "from_state": self.from_state,
            "to_state": self.workflow_state,
            "event_type": self.event_type,
            "transition_name": self.transition,
            "trace_id": self.trace_id or f"WF-{uuid.uuid4().hex[:12]}",
            "tenant_id": self.tenant_id,
            "triggered_by": self.triggered_by,
            "payload": self.payload,
            "occurred_at": self.occurred_at or datetime.now(timezone.utc).isoformat(),
        }

    def to_notification_event_dict(self) -> dict:
        """이 Workflow Event를 Notification Runtime Event로 변환.
        Workflow → Event Layer → Notification Runtime 경유.
        """
        return {
            "event_type": self.event_type,
            "source_engine": "workflow_engine",
            "severity": "INFO",
            "tenant_id": self.tenant_id,
            "trace_id": self.trace_id or f"WF-{uuid.uuid4().hex[:12]}",
            "payload": {
                "workflow_id": self.workflow_id,
                "workflow_type": self.workflow_type,
                "from_state": self.from_state,
                "to_state": self.workflow_state,
                "transition": self.transition,
                **self.payload,
            },
            "source_domain": "workflow_engine",
            "source_entity_id": self.workflow_id,
            "triggered_by": self.triggered_by,
        }
