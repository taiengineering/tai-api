"""Watch Engine type definitions and enums."""

from typing import Optional
from dataclasses import dataclass, field

# ─── Enum constants ───

VALID_RESULTS = frozenset({"success", "failure", "timeout", "skipped", "pending"})
VALID_ACTOR_TYPES = frozenset({"user", "admin", "system", "synthetic_user", "scheduler"})
VALID_CONNECTOR_TYPES = frozenset({"api", "browser", "webhook", "database", "queue", "scheduler"})
VALID_ENVIRONMENTS = frozenset({"local", "dev", "staging", "production"})


@dataclass
class EventPayload:
    """Validated event payload for business_event insert."""
    tenant_id: str
    environment: str
    service_key: str
    flow_key: str
    step_key: str
    step_order: int
    trace_id: str
    event_type: str
    result: str = "pending"
    actor_type: str = "system"
    connector_type: str = "api"
    parent_trace_id: Optional[str] = None
    session_id: Optional[str] = None
    scenario_run_id: Optional[str] = None
    payload_summary: Optional[dict] = None
    payload_hash: Optional[str] = None
