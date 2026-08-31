"""Pattern Auto Updater — 반복 패턴 자동 축적.

integrity event 발생 → pattern_key 계산 → repeat_count 증가 → success_rate 재계산.
Scheduler에서 주기적 호출.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from services.time import now_kst

logger = logging.getLogger("watch_engine.knowledge.pattern_updater")


def update_patterns(
    window_hours: int = 24,
    now: Optional[datetime] = None,
) -> dict:
    """Scan recent integrity events and update pattern registry.

    Returns: {"patterns_updated": int, "patterns_created": int, "errors": int}
    """
    stats = {"patterns_updated": 0, "patterns_created": 0, "errors": 0}
    if now is None:
        now = now_kst()

    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        since = (now - timedelta(hours=window_hours)).isoformat()

        # Get recent integrity events
        events = sb.table("engine_integrity_event") \
            .select("flow_key,event_type,resolved,created_at") \
            .not_.is_("trace_id", "null") \
            .gte("created_at", since) \
            .execute()

        # Aggregate by pattern_key
        patterns = {}
        for e in (events.data or []):
            fk = e.get("flow_key", "unknown")
            et = e.get("event_type", "unknown")
            pk = f"{fk}::{et}"
            if pk not in patterns:
                patterns[pk] = {"flow_key": fk, "event_type": et, "count": 0, "resolved": 0}
            patterns[pk]["count"] += 1
            if e.get("resolved"):
                patterns[pk]["resolved"] += 1

        # Browser/SLA detection
        browser_types = {"browser_render_failed", "selector_not_found", "button_not_clickable", "page_timeout", "ui_value_mismatch"}
        sla_types = {"sla_warning", "sla_critical", "workflow_degraded"}

        for pk, data in patterns.items():
            try:
                browser = data["event_type"] in browser_types or data["flow_key"].endswith("_browser")
                sla = data["event_type"] in sla_types
                rate = round(data["resolved"] / data["count"] * 100, 2) if data["count"] > 0 else None

                # Upsert pattern
                existing = sb.table("incident_pattern_registry") \
                    .select("id,repeat_count,total_resolutions,successful_resolutions") \
                    .eq("pattern_key", pk).limit(1).execute()

                if existing.data:
                    row = existing.data[0]
                    new_total = row.get("total_resolutions", 0) + data["resolved"]
                    new_success = row.get("successful_resolutions", 0) + data["resolved"]
                    new_rate = round(new_success / new_total * 100, 2) if new_total > 0 else None

                    sb.table("incident_pattern_registry").update({
                        "repeat_count": row.get("repeat_count", 0) + data["count"],
                        "last_seen_at": now.isoformat(),
                        "total_resolutions": new_total,
                        "successful_resolutions": new_success,
                        "resolution_success_rate": new_rate,
                        "browser_related": browser,
                        "sla_related": sla,
                        "updated_at": now.isoformat(),
                    }).eq("id", row["id"]).execute()
                    stats["patterns_updated"] += 1
                else:
                    sb.table("incident_pattern_registry").insert({
                        "pattern_key": pk,
                        "event_type": data["event_type"],
                        "flow_key": data["flow_key"],
                        "browser_related": browser,
                        "sla_related": sla,
                        "repeat_count": data["count"],
                        "first_seen_at": now.isoformat(),
                        "last_seen_at": now.isoformat(),
                        "total_resolutions": data["resolved"],
                        "successful_resolutions": data["resolved"],
                        "resolution_success_rate": rate,
                    }).execute()
                    stats["patterns_created"] += 1

            except Exception as e:
                logger.error("Pattern update failed for %s: %s", pk, e)
                stats["errors"] += 1

    except Exception as e:
        logger.error("update_patterns failed: %s", e)
        stats["errors"] += 1

    return stats
