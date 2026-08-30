"""Watch Engine type definitions and enums."""

from typing import Optional
from dataclasses import dataclass, field

# ─── Enum constants ───

VALID_RESULTS = frozenset({"success", "failure", "timeout", "skipped", "pending"})
VALID_ACTOR_TYPES = frozenset({"user", "admin", "system", "synthetic_user", "scheduler"})
VALID_CONNECTOR_TYPES = frozenset({"api", "browser", "webhook", "database", "queue", "scheduler"})
# Aligned with DB be_env_chk (includes 'mock'); no DB change (§4/§14).
VALID_ENVIRONMENTS = frozenset({"local", "dev", "staging", "production", "mock"})


@dataclass
class EventPayload:
    """Validated event payload for business_event insert.

    Legacy fields are always populated. Common Event Contract v1 fields
    (§87/§90) are OPTIONAL and set ONLY when a complete canonical core is
    produced by watch_engine.canonical.build_contract_core; otherwise they
    remain None and the row is a legacy event (event_version IS NULL).
    """
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
    # ─── Common Event Contract v1 (additive, optional) ───
    event_name: Optional[str] = None
    event_version: Optional[int] = None
    occurred_at: Optional[str] = None
    actor_kind: Optional[str] = None
    actor_ref: Optional[str] = None
    outcome: Optional[str] = None
