"""Core event emitter — lightweight, async-safe, fail-safe.

This is the ONLY function services need to call.
All other Watch Engine logic is internal.

Fail-safe guarantee:
    emit_event() NEVER raises exceptions.
    emit_event() NEVER blocks the service.
    If recording fails, a warning is logged and the service continues.

    FAIL-SAFE means the business service is unaffected. It does NOT mean an
    invalid event is converted into legacy data.

Common Event Contract v1 (§87/§90):
    Passing any of event_name / actor_kind / actor_ref / occurred_at / outcome
    signals a request to record the canonical v1 core. Then exactly one of:
        * the canonical core is valid  -> event_version=1 INSERT -> True
        * the canonical core is invalid -> NO INSERT, warning, return False
    A failed canonical request is NEVER silently downgraded to a legacy row
    (§90 PATCH-1). When no canonical fields are passed, the legacy write path is
    used unchanged.
"""

import hashlib
import json
import logging
import os
from typing import Optional

from watch_engine.pii import strip_pii
from watch_engine.trace import TraceContext, get_current_trace
from watch_engine.types import EventPayload
from watch_engine.validation import validate_event, validate_contract_v1
from watch_engine.canonical import build_contract_core

logger = logging.getLogger("watch_engine.emitter")

# ─── Supabase client (lazy init) ───
_supabase_client = None


def _get_supabase():
    """Lazy-load supabase client. Fail-safe."""
    global _supabase_client
    if _supabase_client is None:
        try:
            from db.supabase_client import get_supabase
            _supabase_client = get_supabase()
        except Exception as e:
            logger.error("Failed to init supabase client: %s", e)
            return None
    return _supabase_client


def _compute_hash(payload_summary: dict | None) -> str | None:
    """Compute SHA-256 hash of payload_summary for integrity comparison."""
    if not payload_summary:
        return None
    try:
        canonical = json.dumps(payload_summary, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    except Exception:
        return None


def emit_event(
    *,
    step_key: str,
    step_order: int,
    event_type: str,
    result: str = "success",
    connector_type: str = "api",
    payload_summary: Optional[dict] = None,
    # Trace override (if not using context)
    trace: Optional[TraceContext] = None,
    # Direct fields (override trace context)
    tenant_id: Optional[str] = None,
    environment: Optional[str] = None,
    service_key: Optional[str] = None,
    flow_key: Optional[str] = None,
    trace_id: Optional[str] = None,
    parent_trace_id: Optional[str] = None,
    session_id: Optional[str] = None,
    scenario_run_id: Optional[str] = None,
    actor_type: Optional[str] = None,
    # ─── Common Event Contract v1 (optional; §90) ───
    event_name: Optional[str] = None,
    actor_kind: Optional[str] = None,
    actor_ref: Optional[str] = None,
    occurred_at: Optional[str] = None,
    outcome: Optional[str] = None,
) -> bool:
    """Record a business event. NEVER raises. NEVER blocks.

    Priority for field resolution:
        1. Direct keyword arguments
        2. Explicit trace parameter
        3. Current context trace (contextvars)
        4. Defaults

    Common Event Contract v1 (§90 PATCH-1):
        If any canonical field is supplied, the event is recorded as v1 or NOT
        recorded at all. An invalid canonical request returns False and inserts
        nothing — it is never downgraded to a legacy row.

    Returns:
        True  if the event was recorded successfully.
        False if recording failed or an invalid canonical event was rejected
              (service continues normally; no exception propagates).
    """
    try:
        # ─── Resolve trace context ───
        ctx = trace or get_current_trace()

        resolved_tenant = tenant_id or (ctx.tenant_id if ctx else None) or "unknown"
        resolved_env = environment or (ctx.environment if ctx else None) or "production"
        resolved_service = service_key or (ctx.service_key if ctx else None) or "unknown"
        resolved_flow = flow_key or (ctx.flow_key if ctx else None) or "unknown"
        resolved_trace_id = trace_id or (ctx.trace_id if ctx else None) or "no_trace"
        resolved_parent = parent_trace_id or (ctx.parent_trace_id if ctx else None)
        resolved_session = session_id or (ctx.session_id if ctx else None)
        resolved_scenario = scenario_run_id or (ctx.scenario_run_id if ctx else None)
        resolved_actor = actor_type or (ctx.actor_type if ctx else None) or "system"

        # ─── PII protection ───
        cleaned_payload = strip_pii(payload_summary)

        # ─── Compute hash ───
        p_hash = _compute_hash(cleaned_payload)

        # ─── Common Event Contract v1 (succeed-or-do-not-record; §90 PATCH-1) ───
        canonical_requested = any(
            v is not None
            for v in (event_name, actor_kind, actor_ref, occurred_at, outcome)
        )
        core = None
        if canonical_requested:
            core, core_errors = build_contract_core(
                event_name=event_name,
                actor_kind=actor_kind,
                actor_ref=actor_ref,
                trace_id=resolved_trace_id,
                service_key=resolved_service,
                tenant_id=resolved_tenant,
                environment=resolved_env,
                occurred_at=occurred_at,
                outcome=outcome,
                result=result,
            )
            if core is None:
                # Invalid canonical request → do NOT record, do NOT downgrade to
                # legacy (§17/§90 PATCH-1). Business continues (no exception).
                logger.warning(
                    "Canonical v1 emission requested but INVALID for %s/%s → NOT "
                    "recorded (no legacy downgrade): %s",
                    resolved_flow, step_key, core_errors,
                )
                return False

        _core = core or {}

        # ─── Build payload ───
        payload = EventPayload(
            tenant_id=resolved_tenant,
            environment=resolved_env,
            service_key=resolved_service,
            flow_key=resolved_flow,
            step_key=step_key,
            step_order=step_order,
            trace_id=resolved_trace_id,
            event_type=event_type,
            result=result,
            actor_type=resolved_actor,
            connector_type=connector_type,
            parent_trace_id=resolved_parent,
            session_id=resolved_session,
            scenario_run_id=resolved_scenario,
            payload_summary=cleaned_payload,
            payload_hash=p_hash,
            event_name=_core.get("event_name"),
            event_version=_core.get("event_version"),
            occurred_at=_core.get("occurred_at"),
            actor_kind=_core.get("actor_kind"),
            actor_ref=_core.get("actor_ref"),
            outcome=_core.get("outcome"),
        )

        # ─── Legacy structural validation (non-blocking, warn only) ───
        is_valid, errors = validate_event(payload)
        if not is_valid:
            logger.warning(
                "Event validation failed for %s/%s: %s — recording anyway",
                resolved_flow, step_key, errors,
            )

        # ─── v1 application validation layer (§17) ───
        # Only runs for canonical requests. On failure the event is NOT recorded
        # and NOT downgraded to legacy.
        if canonical_requested:
            v1_ok, v1_errors = validate_contract_v1(payload)
            if not v1_ok:
                logger.warning(
                    "Canonical v1 application validation failed for %s/%s → NOT "
                    "recorded (no legacy downgrade): %s",
                    resolved_flow, step_key, v1_errors,
                )
                return False

        # ─── Insert ───
        sb = _get_supabase()
        if sb is None:
            logger.error("Supabase unavailable — event lost: %s/%s", resolved_flow, step_key)
            return False

        row = {
            "tenant_id": payload.tenant_id,
            "environment": payload.environment,
            "service_key": payload.service_key,
            "flow_key": payload.flow_key,
            "step_key": payload.step_key,
            "step_order": payload.step_order,
            "trace_id": payload.trace_id,
            "parent_trace_id": payload.parent_trace_id,
            "session_id": payload.session_id,
            "scenario_run_id": payload.scenario_run_id,
            "actor_type": payload.actor_type,
            "connector_type": payload.connector_type,
            "event_type": payload.event_type,
            "result": payload.result,
            "payload_summary": payload.payload_summary,
            "payload_hash": payload.payload_hash,
            # ─── Common Event Contract v1 (present only for a valid v1 event) ───
            "event_name": payload.event_name,
            "event_version": payload.event_version,
            "occurred_at": payload.occurred_at,
            "actor_kind": payload.actor_kind,
            "actor_ref": payload.actor_ref,
            "outcome": payload.outcome,
        }

        # Remove None values for clean insert
        row = {k: v for k, v in row.items() if v is not None}

        sb.table("business_event").insert(row).execute()

        logger.debug(
            "Event recorded: %s/%s [%s] result=%s ver=%s",
            resolved_flow, step_key, resolved_trace_id, result,
            payload.event_version if payload.event_version else "legacy",
        )
        return True

    except Exception as e:
        # ─── FAIL-SAFE: swallow all exceptions (business unaffected) ───
        logger.error(
            "emit_event FAILED (service unaffected): %s — flow=%s step=%s",
            str(e),
            flow_key or "?",
            step_key,
        )
        return False
