"""Integrity Evaluator v1.1 — with Flow Completion Semantics.

Changes from v1.0:
- Flow status computed BEFORE rule evaluation
- False positive suppression for failed flows
- field_mismatch and timeout_exceeded never suppressed
- sequence_violation and stuck_detected suppressed when flow_status=failed

Scheduler calls evaluate_recent_events() periodically.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from watch_engine.integrity.flow_status import (
    compute_flow_status, should_suppress, FAILED, STUCK
)
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
    """Evaluate recent business_events against integrity rules.

    Returns:
        {"evaluated_traces": int, "issues_found": int,
         "suppressed": int, "errors": int}
    """
    stats = {"evaluated_traces": 0, "issues_found": 0,
             "suppressed": 0, "errors": 0}

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
                traces[tid] = {
                    "events": [],
                    "flow_key": e.get("flow_key"),
                    "tenant_id": e.get("tenant_id"),
                    "environment": e.get("environment", "production"),
                    "service_key": e.get("service_key", "tai-api"),
                }
            traces[tid]["events"].append(e)

        # 3. Process each trace
        for trace_id, trace_data in traces.items():
            try:
                issues, suppressed = _evaluate_trace(
                    sb, trace_id, trace_data, now
                )
                stats["evaluated_traces"] += 1
                stats["issues_found"] += len(issues)
                stats["suppressed"] += suppressed

                for issue in issues:
                    _write_integrity_event(sb, issue)

            except Exception as e:
                logger.error("Error evaluating trace %s: %s", trace_id, e)
                stats["errors"] += 1

    except Exception as e:
        logger.error("evaluate_recent_events failed: %s", e)
        stats["errors"] += 1

    logger.info(
        "Evaluation: %d traces, %d issues, %d suppressed, %d errors",
        stats["evaluated_traces"], stats["issues_found"],
        stats["suppressed"], stats["errors"],
    )
    return stats


def _evaluate_trace(
    sb, trace_id: str, trace_data: dict, now: datetime
) -> tuple[list[dict], int]:
    """Evaluate a single trace. Returns (issues, suppressed_count)."""
    issues = []
    suppressed_count = 0
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

    # Load registries
    fr_resp = sb.table("flow_registry") \
        .select("*") \
        .eq("tenant_id", tenant_id) \
        .eq("environment", environment) \
        .eq("service_key", service_key) \
        .eq("flow_key", flow_key) \
        .limit(1).execute()
    flow_reg = (fr_resp.data or [None])[0]
    if not flow_reg:
        return [], 0

    sr_resp = sb.table("flow_step_registry") \
        .select("*") \
        .eq("tenant_id", tenant_id) \
        .eq("environment", environment) \
        .eq("service_key", service_key) \
        .eq("flow_key", flow_key) \
        .order("step_order").execute()
    registered_steps = sr_resp.data or []

    rr_resp = sb.table("flow_integrity_rule_registry") \
        .select("*") \
        .eq("tenant_id", tenant_id) \
        .eq("environment", environment) \
        .eq("service_key", service_key) \
        .eq("flow_key", flow_key) \
        .eq("is_active", True).execute()
    rules = rr_resp.data or []

    # ═══ STEP 1: Compute flow status FIRST ═══
    flow_status = compute_flow_status(
        events_by_step, registered_steps,
        stuck_threshold_ms=flow_reg.get("stuck_threshold_ms", 60000),
        now=now,
    )
    status = flow_status["status"]

    logger.debug(
        "Trace %s flow_status=%s terminal=%s",
        trace_id, status, flow_status.get("terminal_step"),
    )

    # ═══ STEP 2: Apply rules with suppression ═══
    candidate_issues = []

    # Rule-based checks
    for rule in rules:
        rt = rule.get("rule_type")
        if rt == "field_match":
            result = check_field_mismatch(rule, events_by_step, trace_id)
            if result:
                candidate_issues.append(result)
        elif rt == "sequence":
            result = check_sequence_violation(
                rule, events_by_step, trace_id, registered_steps
            )
            if result:
                candidate_issues.append(result)

    # Flow-level checks
    stuck = check_stuck_detected(
        flow_reg, events_by_step, trace_id, registered_steps, now
    )
    if stuck:
        candidate_issues.append(stuck)

    timeouts = check_timeout_exceeded(
        events_by_step, trace_id, registered_steps,
        flow_key, tenant_id, environment, service_key,
    )
    candidate_issues.extend(timeouts)

    # ═══ STEP 3: Suppress false positives ═══
    for issue in candidate_issues:
        event_type = issue.get("event_type", "")
        if should_suppress(event_type, status):
            suppressed_count += 1
            logger.info(
                "Suppressed %s for trace %s (flow_status=%s)",
                event_type, trace_id, status,
            )
        else:
            issues.append(issue)

    return issues, suppressed_count


def _write_integrity_event(sb, issue: dict) -> bool:
    """Write engine_integrity_event with dedupe."""
    try:
        trace_id = issue.get("trace_id")
        event_type = issue.get("event_type")
        step_key = issue.get("step_key")

        query = sb.table("engine_integrity_event") \
            .select("id") \
            .eq("trace_id", trace_id) \
            .eq("event_type", event_type)
        if step_key:
            query = query.eq("step_key", step_key)
        existing = query.limit(1).execute()

        if existing.data:
            return False

        import json
        detail = issue.get("detail")
        if detail and isinstance(detail, dict):
            issue["detail"] = json.loads(json.dumps(detail, default=str))

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
        return True

    except Exception as e:
        logger.error("Failed to write integrity event: %s", e)
        return False
