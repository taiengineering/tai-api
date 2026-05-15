"""Integrity Evaluator — batch evaluation of recent business_events.

Scheduler calls evaluate_recent_events() periodically.
Reads business_event → applies rules → writes engine_integrity_event.

Fail-safe: never raises, never blocks service.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from watch_engine.integrity.rules.field_mismatch import check_field_mismatch
from watch_engine.integrity.rules.sequence_violation import check_sequence_violation
from watch_engine.integrity.rules.stuck_detected import check_stuck_detected
from watch_engine.integrity.rules.timeout_exceeded import check_timeout_exceeded

logger = logging.getLogger("watch_engine.integrity.evaluator")

_supabase_client = None


def _get_supabase():
    global _supabase_client
    if _supabase_client is None:
        try:
            from db.supabase_client import get_supabase
            _supabase_client = get_supabase()
        except Exception as e:
            logger.error("Failed to init supabase: %s", e)
            return None
    return _supabase_client


def evaluate_recent_events(
    last_minutes: int = 5,
    now: Optional[datetime] = None,
) -> dict:
    """Evaluate recent business_events against registered integrity rules.

    Args:
        last_minutes: Look back window in minutes.
        now: Current time (injectable for testing).

    Returns:
        {"evaluated_traces": int, "issues_found": int, "errors": int}
    """
    stats = {"evaluated_traces": 0, "issues_found": 0, "errors": 0}

    try:
        sb = _get_supabase()
        if sb is None:
            stats["errors"] = 1
            return stats

        if now is None:
            now = datetime.now(timezone.utc)
        since = now - timedelta(minutes=last_minutes)

        # 1. Get recent business_events
        resp = sb.table("business_event") \
            .select("*") \
            .gte("created_at", since.isoformat()) \
            .order("created_at") \
            .execute()
        events = resp.data or []

        if not events:
            return stats

        # 2. Group by trace_id
        traces = {}
        for e in events:
            tid = e.get("trace_id", "unknown")
            if tid not in traces:
                traces[tid] = {"events": [], "flow_key": e.get("flow_key"), "tenant_id": e.get("tenant_id"), "environment": e.get("environment", "production"), "service_key": e.get("service_key", "tai-api")}
            traces[tid]["events"].append(e)

        # 3. Process each trace
        for trace_id, trace_data in traces.items():
            try:
                issues = _evaluate_trace(
                    sb, trace_id, trace_data, now
                )
                stats["evaluated_traces"] += 1
                stats["issues_found"] += len(issues)

                # 4. Write integrity events (with dedupe)
                for issue in issues:
                    _write_integrity_event(sb, issue)

            except Exception as e:
                logger.error("Error evaluating trace %s: %s", trace_id, e)
                stats["errors"] += 1

    except Exception as e:
        logger.error("evaluate_recent_events failed: %s", e)
        stats["errors"] += 1

    logger.info(
        "Integrity evaluation complete: %d traces, %d issues, %d errors",
        stats["evaluated_traces"], stats["issues_found"], stats["errors"],
    )
    return stats


def _evaluate_trace(
    sb, trace_id: str, trace_data: dict, now: datetime
) -> list[dict]:
    """Evaluate a single trace against all applicable rules."""
    issues = []
    flow_key = trace_data["flow_key"]
    tenant_id = trace_data["tenant_id"]
    environment = trace_data["environment"]
    service_key = trace_data["service_key"]
    events = trace_data["events"]

    # Group events by step_key
    events_by_step = {}
    for e in events:
        sk = e.get("step_key", "unknown")
        if sk not in events_by_step:
            events_by_step[sk] = []
        events_by_step[sk].append(e)

    # Load flow registry
    fr_resp = sb.table("flow_registry") \
        .select("*") \
        .eq("tenant_id", tenant_id) \
        .eq("environment", environment) \
        .eq("service_key", service_key) \
        .eq("flow_key", flow_key) \
        .limit(1) \
        .execute()
    flow_reg = (fr_resp.data or [None])[0]
    if not flow_reg:
        return []  # Unregistered flow, skip

    # Load step registry
    sr_resp = sb.table("flow_step_registry") \
        .select("*") \
        .eq("tenant_id", tenant_id) \
        .eq("environment", environment) \
        .eq("service_key", service_key) \
        .eq("flow_key", flow_key) \
        .order("step_order") \
        .execute()
    registered_steps = sr_resp.data or []

    # Load rules
    rr_resp = sb.table("flow_integrity_rule_registry") \
        .select("*") \
        .eq("tenant_id", tenant_id) \
        .eq("environment", environment) \
        .eq("service_key", service_key) \
        .eq("flow_key", flow_key) \
        .eq("is_active", True) \
        .execute()
    rules = rr_resp.data or []

    # Apply rules
    for rule in rules:
        rt = rule.get("rule_type")

        if rt == "field_match":
            result = check_field_mismatch(rule, events_by_step, trace_id)
            if result:
                issues.append(result)

        elif rt == "sequence":
            result = check_sequence_violation(
                rule, events_by_step, trace_id, registered_steps
            )
            if result:
                issues.append(result)

    # Stuck detection (flow-level, not rule-level)
    stuck = check_stuck_detected(
        flow_reg, events_by_step, trace_id, registered_steps, now
    )
    if stuck:
        issues.append(stuck)

    # Timeout detection (step-level)
    timeouts = check_timeout_exceeded(
        events_by_step, trace_id, registered_steps,
        flow_key, tenant_id, environment, service_key,
    )
    issues.extend(timeouts)

    return issues


def _write_integrity_event(sb, issue: dict) -> bool:
    """Write engine_integrity_event with dedupe check.

    Dedupe key: (trace_id, event_type, step_key)
    """
    try:
        trace_id = issue.get("trace_id")
        event_type = issue.get("event_type")
        step_key = issue.get("step_key")

        # Dedupe check
        query = sb.table("engine_integrity_event") \
            .select("id") \
            .eq("trace_id", trace_id) \
            .eq("event_type", event_type)
        if step_key:
            query = query.eq("step_key", step_key)
        existing = query.limit(1).execute()

        if existing.data:
            return False  # Already exists

        # Convert detail to jsonb-safe
        import json
        detail = issue.get("detail")
        if detail and isinstance(detail, dict):
            issue["detail"] = json.loads(json.dumps(detail, default=str))

        # Map to table columns
        row = {
            "tenant_id": issue.get("tenant_id"),
            "environment": issue.get("environment"),
            "service_key": issue.get("service_key"),
            "flow_key": issue.get("flow_key"),
            "step_key": step_key,
            "trace_id": trace_id,
            "event_type": event_type,
            "severity": issue.get("severity", "WARNING"),
            "integrity_status": issue.get("integrity_status", "unknown"),
            "health_status": issue.get("health_status", "unknown"),
            "domain": issue.get("domain"),
            "description": issue.get("description"),
            "detail": issue.get("detail"),
            "source_event_id": issue.get("source_event_id"),
            "resolved": False,
        }
        row = {k: v for k, v in row.items() if v is not None}

        sb.table("engine_integrity_event").insert(row).execute()
        logger.info("Integrity event created: %s/%s [%s]", event_type, step_key, trace_id)
        return True

    except Exception as e:
        logger.error("Failed to write integrity event: %s", e)
        return False
