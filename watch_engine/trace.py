"""Trace propagation — trace_id generation and context management.

Design:
    - 1 independent flow = 1 trace_id
    - Format: {flow_key}_{ulid_short}
    - TraceContext carries trace metadata through async boundaries
    - contextvars-based for async safety
"""

import uuid
import time
import logging
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("watch_engine.trace")

# ─── Context variable for async-safe trace propagation ───
_current_trace: ContextVar[Optional["TraceContext"]] = ContextVar(
    "watch_engine_trace", default=None
)


def _generate_short_id() -> str:
    """Generate a short time-sortable ID (UUID v7 inspired).

    Format: 12-char base32-like string.
    Collision-safe for single-service use.
    """
    ts = int(time.time() * 1000)  # ms precision
    rand = uuid.uuid4().int & 0xFFFFFFFF  # 32-bit random
    combined = (ts << 32) | rand
    # Base36 encoding for readability
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = []
    while combined > 0:
        result.append(chars[combined % 36])
        combined //= 36
    return "".join(reversed(result))[:12]


@dataclass
class TraceContext:
    """Immutable trace context for a single flow execution."""
    trace_id: str
    flow_key: str
    tenant_id: str
    environment: str = "production"
    service_key: str = "tai-api"
    parent_trace_id: Optional[str] = None
    session_id: Optional[str] = None
    scenario_run_id: Optional[str] = None
    actor_type: str = "system"


def create_trace(
    flow_key: str,
    tenant_id: str,
    environment: str = "production",
    service_key: str = "tai-api",
    parent_trace_id: Optional[str] = None,
    session_id: Optional[str] = None,
    scenario_run_id: Optional[str] = None,
    actor_type: str = "system",
) -> TraceContext:
    """Create a new TraceContext and set it as current.

    Call once at flow start. The trace_id is immutable for the flow duration.
    """
    trace_id = f"{flow_key}_{_generate_short_id()}"

    ctx = TraceContext(
        trace_id=trace_id,
        flow_key=flow_key,
        tenant_id=tenant_id,
        environment=environment,
        service_key=service_key,
        parent_trace_id=parent_trace_id,
        session_id=session_id,
        scenario_run_id=scenario_run_id,
        actor_type=actor_type,
    )

    _current_trace.set(ctx)
    logger.debug("Trace created: %s", trace_id)
    return ctx


def get_current_trace() -> Optional[TraceContext]:
    """Get the current trace context (async-safe via contextvars)."""
    return _current_trace.get()


def clear_trace() -> None:
    """Clear the current trace context (call at flow end)."""
    _current_trace.set(None)
