"""Bridge Evaluator — business_event → integrity_event Projection.

\ucd5c\uadfc business_event\ub97c \uc77d\uace0, Control Severity\ub97c Projection\ud558\uc5ec
integrity_event\ub85c \ubcc0\ud658. Escalation \ud0d0\uc9c0 \ud3ec\ud568.
"""

import logging
from datetime import datetime, timezone, timedelta
from watch_engine.control_bridge.severity_projection import project_severity
from watch_engine.control_bridge.bridge_rules import ESCALATION_RULES

logger = logging.getLogger("watch_engine.control_bridge.evaluator")


def evaluate_bridge(sb=None, window_minutes: int = 5, include_mock: bool = True) -> dict:
    """Control Bridge \ud3c9\uac00.

    Args:
        sb: Supabase client
        window_minutes: \ucd5c\uadfc N\ubd84 business_event \uc77d\uae30
        include_mock: mock \ud658\uacbd \ud3ec\ud568 \uc5ec\ubd80 (Intelligence \ud559\uc2b5\uc6a9)
    """
    if sb is None:
        from db.supabase_client import get_supabase
        sb = get_supabase()

    since = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat()

    # 1. \ucd5c\uadfc business_event \uc77d\uae30
    q = sb.table("business_event") \
        .select("id,tenant_id,flow_key,step_key,event_type,result,trace_id,environment,created_at") \
        .gte("created_at", since) \
        .order("created_at", desc=True).limit(500)

    if not include_mock:
        q = q.neq("environment", "mock")

    events = q.execute()

    stats = {"evaluated": 0, "projected": 0, "escalation": 0, "skipped": 0}

    # \uc774\ubbf8 projection\ub41c trace \uc911\ubcf5 \ubc29\uc9c0
    projected_traces = set()
    try:
        recent_integrity = sb.table("engine_integrity_event") \
            .select("trace_id") \
            .gte("created_at", since) \
            .eq("domain", "control_bridge").execute()
        projected_traces = {r["trace_id"] for r in (recent_integrity.data or []) if r.get("trace_id")}
    except Exception:
        pass

    # 2. \uac01 event projection
    failure_counts = {}  # flow_key:event_type \u2192 count (escalation \ud0d0\uc9c0\uc6a9)
    tenant_failures = {}  # tenant_id \u2192 count

    for e in (events.data or []):
        stats["evaluated"] += 1
        et = e.get("event_type", "")
        result = e.get("result", "")

        # result \uae30\ubc18 canonical event_type \ubcf5\uc6d0
        canonical_et = _to_canonical(et, result, e.get("flow_key", ""))
        if not canonical_et:
            stats["skipped"] += 1
            continue

        proj = project_severity(canonical_et)
        if not proj:
            stats["skipped"] += 1
            continue

        trace_id = e.get("trace_id", "")
        if trace_id in projected_traces:
            stats["skipped"] += 1
            continue

        # integrity_event \uc0dd\uc131 (Control Runtime\uc73c\ub85c)
        try:
            sb.table("engine_integrity_event").insert({
                "tenant_id": e.get("tenant_id", "system"),
                "environment": e.get("environment", "production"),
                "service_key": "tai-api",
                "flow_key": e.get("flow_key", ""),
                "step_key": e.get("step_key"),
                "trace_id": trace_id,
                "event_type": canonical_et,
                "severity": proj["severity"],
                "integrity_status": "projected",
                "health_status": "warning" if proj["severity"] == "WARNING" else "critical",
                "domain": "control_bridge",
                "description": f"[BRIDGE] {proj['description']} ({canonical_et})",
                "resolved": False,
            }).execute()
            stats["projected"] += 1
            projected_traces.add(trace_id)
        except Exception as ex:
            logger.error("bridge projection failed: %s", ex)

        # Escalation \uce74\uc6b4\ud130
        fk = f"{e.get('flow_key', '')}:{canonical_et}"
        failure_counts[fk] = failure_counts.get(fk, 0) + 1
        tid = e.get("tenant_id", "")
        tenant_failures[tid] = tenant_failures.get(tid, 0) + 1

    # 3. Escalation \ud0d0\uc9c0
    for fk, count in failure_counts.items():
        for rule_name, rule in ESCALATION_RULES.items():
            threshold = rule.get("min_count", 3)
            if count >= threshold:
                _emit_escalation(sb, fk, count, rule, stats)

    # Multi-tenant escalation
    affected_tenants = sum(1 for c in tenant_failures.values() if c >= 2)
    mt_rule = ESCALATION_RULES.get("multi_tenant_failure", {})
    if affected_tenants >= mt_rule.get("min_tenants", 3):
        _emit_escalation(sb, f"multi_tenant:{affected_tenants}", affected_tenants, mt_rule, stats)

    logger.info("[BRIDGE] %s", stats)
    return stats


def _to_canonical(event_type: str, result: str, flow_key: str) -> str:
    """business_event\uc758 event_type/result \u2192 Canonical event_type."""
    if result == "failure" or "fail" in event_type:
        if flow_key in ("payment",):
            return "payment.failed"
        return f"workflow.failed" if not event_type or event_type in ("submit", "read", "create") else f"step.failed"
    if result == "timeout" or "timeout" in event_type:
        return "workflow.timeout"
    if result == "blocked" or "block" in event_type:
        return "workflow.blocked"
    return ""  # \uc131\uacf5 \uc774\ubca4\ud2b8\ub294 projection \ubd88\ud544\uc694


def _emit_escalation(sb, key: str, count: int, rule: dict, stats: dict):
    try:
        sb.table("engine_integrity_event").insert({
            "tenant_id": "system",
            "environment": "mock",
            "service_key": "tai-api",
            "flow_key": key.split(":")[0] if ":" in key else key,
            "trace_id": f"escalation_{key}_{datetime.now(timezone.utc).strftime('%H%M')}",
            "event_type": rule.get("event_type", "watch.integrity_detected"),
            "severity": rule.get("severity", "WARNING"),
            "integrity_status": "escalation",
            "health_status": "critical" if rule.get("severity") == "CRITICAL" else "warning",
            "domain": "control_bridge",
            "description": f"[BRIDGE ESCALATION] {rule.get('description', '')} ({key}: {count}\ud68c)",
            "resolved": False,
        }).execute()
        stats["escalation"] += 1
    except Exception as ex:
        logger.error("escalation emit failed: %s", ex)
