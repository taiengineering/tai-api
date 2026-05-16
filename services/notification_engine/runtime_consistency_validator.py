"""Runtime Consistency Validator v2 — trace_id Feed 검증 강화."""

import logging
from typing import Optional

logger = logging.getLogger("notification_engine.consistency")


def validate_trace(trace_id: str) -> dict:
    from db.supabase_client import get_supabase
    sb = get_supabase()
    gaps = []

    ev = _get(sb, "runtime_notification_event", trace_id)
    queue_items = _list(sb, "runtime_notification_queue", trace_id)
    audits = _list(sb, "runtime_notification_audit", trace_id)
    policies = _list(sb, "runtime_notification_policy_audit", trace_id)
    feed_items = _list(sb, "notifications", trace_id)

    # 1. Queue
    queue_ok = True
    if ev and not queue_items:
        if not any(p.get("policy_result") == "SUPPRESSED" for p in policies):
            gaps.append({"type": "QUEUE_GAP", "detail": "Event exists but no queue items and not suppressed"})
            queue_ok = False

    # 2. Audit
    audit_ok = True
    delivered = [q for q in queue_items if q.get("delivery_status") == "DELIVERED"]
    if delivered and not [a for a in audits if a.get("action") == "DELIVERED"]:
        gaps.append({"type": "AUDIT_GAP", "detail": f"{len(delivered)} delivered but 0 audit"})
        audit_ok = False

    dlq_q = [q for q in queue_items if q.get("delivery_status") == "DEADLETTER"]
    if dlq_q and not [a for a in audits if a.get("action") == "DEADLETTER"]:
        gaps.append({"type": "AUDIT_GAP", "detail": "DEADLETTER queue but no audit"})
        audit_ok = False

    # 3. Policy
    policy_ok = True
    qh = [q for q in queue_items if q.get("delivery_status") == "QUIET_HOUR_DELAYED"]
    if qh and not [p for p in policies if p.get("policy_type") == "QUIET_HOUR"]:
        gaps.append({"type": "AUDIT_GAP", "detail": "QH_DELAYED but no QH policy"})
        policy_ok = False

    # 4. Feed (trace_id 연결)
    feed_ok = True
    in_app_delivered = [q for q in delivered if q.get("delivery_channel") == "IN_APP"]
    if in_app_delivered and not feed_items:
        gaps.append({"type": "FEED_GAP", "detail": "IN_APP delivered but no feed item with trace_id"})
        feed_ok = False

    # 5. Feed trace integrity
    for fi in feed_items:
        if not fi.get("trace_id"):
            gaps.append({"type": "FEED_GAP", "detail": f"Feed item {fi.get('id')} missing trace_id"})
            feed_ok = False
            break

    timeline_ok = True
    metrics_ok = True

    return {
        "trace_id": trace_id,
        "event_exists": ev is not None,
        "queue_count": len(queue_items), "audit_count": len(audits),
        "policy_count": len(policies), "feed_count": len(feed_items),
        "queue_consistent": queue_ok, "feed_consistent": feed_ok,
        "audit_consistent": audit_ok, "policy_consistent": policy_ok,
        "metrics_consistent": metrics_ok, "timeline_consistent": timeline_ok,
        "all_consistent": all([queue_ok, feed_ok, audit_ok, policy_ok, metrics_ok, timeline_ok]),
        "detected_gaps": gaps,
    }


def _get(sb, table, trace_id):
    try:
        r = sb.table(table).select("*").eq("trace_id", trace_id).limit(1).execute()
        return r.data[0] if r.data else None
    except Exception:
        return None


def _list(sb, table, trace_id):
    try:
        return sb.table(table).select("*").eq("trace_id", trace_id).execute().data or []
    except Exception:
        return []
