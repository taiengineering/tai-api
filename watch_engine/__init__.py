"""Watch Engine SDK v1.1 — Thin Agent for Business Event Recording.

Usage:
    from watch_engine import emit_event, create_trace, TraceContext

    trace = create_trace("login", tenant_id="tai")
    emit_event(
        trace=trace,
        step_key="submit_form",
        step_order=1,
        event_type="submit",
        result="success",
        payload_summary={"has_username": True},
    )
"""

from watch_engine.emitter import emit_event  # noqa: F401
from watch_engine.trace import create_trace, TraceContext  # noqa: F401

__version__ = "1.1.0"
