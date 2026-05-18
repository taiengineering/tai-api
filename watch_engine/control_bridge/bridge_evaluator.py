"""Bridge Evaluator — business_event → integrity_event Projection.

최근 business_event를 읽고, Control Severity를 Projection하여
integrity_event로 변환. Escalation 탐지 포함.
"""

import logging
from datetime import datetime, timezone, timedelta
from watch_engine.control_bridge.severity_projection import project_severity
from watch_engine.control_bridge.bridge_rules import ESCALATION_RULES

logger = logging.getLogger("watch_engine.control_bridge.evaluator")


def evaluate_bridge(sb=None, window_minutes: int = 5, include_mock: bool = True) -> dict:
    if sb is None:
        from db.supabase_client import get_supabase
        sb = get_supabase()

    since = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat()

    q = sb.table("business_event") \
        .select("id,tenant_id,flow_key,step_key,event_type,result,trace_id,environment,created_at") \
        .gte("created_at", since) \
        .order("created_at", desc=True).limit(500)

    if not include_mock:
        q = q.neq("environment", "mock")

    events = q.execute()
    stats = {"evaluated": 0, "projected": 0, "escalation": 0, "skipped": 0}

    projected_traces = set()
    try:
        ri = sb.table("engine_integrity_event").select("trace_id") \
            .gte("created_at", since).eq("domain", "control_bridge").execute()
        projected_traces = {r["trace_id"] for r in (ri.data or []) if r.get("trace_id")}
    except Exception:
        pass

    failure_counts = {}
    tenant_failures = {}

    for e in (events.data or []):
        stats["evaluated"] += 1
        et = e.get("event_type", "")
        result = e.get("result", "")

        canonical_et = _to_canonical(et, result, e.get("flow_key", ""))
        if not canonical_et:
            stats["skipped"] += 1
            continue

        proj = project_severity(canonical_et)
        if not proj:
            stats["skipped"] += 1
            continue

        trace_id = e.get("trace_id") or ""
        if trace_id and trace_id in projected_traces:
            stats["skipped"] += 1
            continue

        try:
            sb.table("engine_integrity_event").insert({
                "tenant_id": e.get("tenant_id") or "system",
                "environment": e.get("environment") or "mock",
                "service_key": "tai-api",
                "flow_key": e.get("flow_key") or "",
                "step_key": e.get("step_key") or "",
                "trace_id": trace_id,
                "event_type": canonical_et,
                "severity": proj["severity"],
                "integrity_status": "projected",
                "health_status": "warning" if proj["severity"] == "WARNING" else "critical",
                "domain": "control_bridge",
                "description": f"[BRIDGE] {proj['description']} ({canonical_et})",
                "source_trace": trace_id or "bridge",
                "resolved": False,
                "acknowledged": False,
                "ignored": False,
            }).execute()
            stats["projected"] += 1
            if trace_id:
                projected_traces.add(trace_id)
        except Exception as ex:
            logger.error("bridge projection failed: %s", ex)

        fk = f"{e.get('flow_key', '')}:{canonical_et}"
        failure_counts[fk] = failure_counts.get(fk, 0) + 1
        tid = e.get("tenant_id", "")
        tenant_failures[tid] = tenant_failures.get(tid, 0) + 1

    for fk, count in failure_counts.items():
        for rule_name, rule in ESCALATION_RULES.items():
            threshold = rule.get("min_count", 3)
            if count >= threshold:
                _emit_escalation(sb, fk, count, rule, stats)

    affected = sum(1 for c in tenant_failures.values() if c >= 2)
    mt = ESCALATION_RULES.get("multi_tenant_failure", {})
    if affected >= mt.get("min_tenants", 3):
        _emit_escalation(sb, f"multi_tenant:{affected}", affected, mt, stats)

    logger.info("[BRIDGE] %s", stats)
    return stats


def _to_canonical(event_type, result, flow_key):
    if result == "failure" or "fail" in event_type:
        if flow_key in ("payment",):
            return "payment.failed"
        return "workflow.failed" if not event_type or event_type in ("submit", "read", "create") else "step.failed"
    if result == "timeout" or "timeout" in event_type:
        return "workflow.timeout"
    if result == "blocked" or "block" in event_type:
        return "workflow.blocked"
    return ""


def _emit_escalation(sb, key, count, rule, stats):
    try:
        sb.table("engine_integrity_event").insert({
            "tenant_id": "system",
            "environment": "mock",
            "service_key": "tai-api",
            "flow_key": key.split(":")[0] if ":" in key else key,
            "trace_id": f"esc_{key}_{datetime.now(timezone.utc).strftime('%H%M')}",
            "event_type": rule.get("event_type", "watch.integrity_detected"),
            "severity": rule.get("severity", "WARNING"),
            "integrity_status": "escalation",
            "health_status": "critical" if rule.get("severity") == "CRITICAL" else "warning",
            "domain": "control_bridge",
            "description": f"[BRIDGE ESC] {rule.get('description', '')} ({key}: {count}회)",
            "source_trace": f"esc_{key}",
            "resolved": False,
            "acknowledged": False,
            "ignored": False,
        }).execute()
        stats["escalation"] += 1
    except Exception as ex:
        logger.error("escalation failed: %s", ex)
