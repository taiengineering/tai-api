"""Synthetic Cleanup — 운영 데이터 오염 방지.

Synthetic Scenario가 생성한 데이터를 주기적으로 정리.
운영 데이터는 절대 삭제하지 않음.

Isolation strategy:
- business_event: actor_type = 'synthetic_user'
- engine_integrity_event: trace synthetic events
- Service data: SYNTHETIC_FACTORY_ID 기반 또는 process_name = 'SYNTHETIC_HEARTBEAT'

Retention:
- business_event (synthetic): 7일
- engine_integrity_event (synthetic): 7일
- Service data (synthetic): 24시간

Fail-safe: 절대 서비스 영향 없음.
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("watch_engine.synthetic.cleanup")

# Synthetic markers (never delete data without these markers)
SYNTHETIC_ACTOR = "synthetic_user"
SYNTHETIC_PROCESS_NAME = "SYNTHETIC_HEARTBEAT"


def cleanup_synthetic_data(
    event_retention_days: int = 7,
    service_data_retention_hours: int = 24,
    now: Optional[datetime] = None,
) -> dict:
    """Clean up synthetic data across all tables.

    SAFETY:
    - Only deletes rows with explicit synthetic markers
    - Never touches rows without markers
    - Fail-safe: any error -> skip that table, continue

    Returns:
        {"business_events_deleted": int, "integrity_events_deleted": int,
         "service_data_deleted": int, "errors": int}
    """
    stats = {
        "business_events_deleted": 0,
        "integrity_events_deleted": 0,
        "service_data_deleted": 0,
        "errors": 0,
    }

    if now is None:
        now = datetime.now(timezone.utc)

    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
    except Exception as e:
        logger.error("Cleanup: failed to get supabase: %s", e)
        stats["errors"] = 1
        return stats

    # 1. business_event cleanup (synthetic, older than retention)
    try:
        cutoff = (now - timedelta(days=event_retention_days)).isoformat()
        resp = sb.table("business_event") \
            .delete() \
            .eq("actor_type", SYNTHETIC_ACTOR) \
            .lt("created_at", cutoff) \
            .execute()
        deleted = len(resp.data) if resp.data else 0
        stats["business_events_deleted"] = deleted
        if deleted > 0:
            logger.info("Cleanup: deleted %d synthetic business_events (>%dd)", deleted, event_retention_days)
    except Exception as e:
        logger.error("Cleanup business_event failed: %s", e)
        stats["errors"] += 1

    # 2. engine_integrity_event cleanup (linked to synthetic traces)
    try:
        # Find synthetic trace_ids first
        synthetic_traces = sb.table("business_event") \
            .select("trace_id") \
            .eq("actor_type", SYNTHETIC_ACTOR) \
            .lt("created_at", cutoff) \
            .execute()
        trace_ids = list(set(
            t["trace_id"] for t in (synthetic_traces.data or []) if t.get("trace_id")
        ))

        if trace_ids:
            # Delete integrity events for these traces
            for tid in trace_ids:
                try:
                    resp = sb.table("engine_integrity_event") \
                        .delete() \
                        .eq("trace_id", tid) \
                        .execute()
                    stats["integrity_events_deleted"] += len(resp.data) if resp.data else 0
                except Exception:
                    pass

            if stats["integrity_events_deleted"] > 0:
                logger.info("Cleanup: deleted %d synthetic integrity_events", stats["integrity_events_deleted"])
    except Exception as e:
        logger.error("Cleanup integrity_event failed: %s", e)
        stats["errors"] += 1

    # 3. Service data cleanup (factory_process with synthetic marker)
    try:
        service_cutoff = (now - timedelta(hours=service_data_retention_hours)).isoformat()
        factory_id = os.environ.get("SYNTHETIC_FACTORY_ID", "")

        # Clean by process_name marker (safest)
        resp = sb.table("factory_process") \
            .delete() \
            .eq("process_name", SYNTHETIC_PROCESS_NAME) \
            .lt("created_at", service_cutoff) \
            .execute()
        deleted = len(resp.data) if resp.data else 0
        stats["service_data_deleted"] = deleted
        if deleted > 0:
            logger.info("Cleanup: deleted %d synthetic factory_process records (>%dh)", deleted, service_data_retention_hours)
    except Exception as e:
        # factory_process table might not exist or have different name
        logger.warning("Cleanup service_data skipped: %s", e)
        # Not counting as error since table may not exist

    logger.info(
        "Cleanup complete: be=%d, ie=%d, svc=%d, errors=%d",
        stats["business_events_deleted"],
        stats["integrity_events_deleted"],
        stats["service_data_deleted"],
        stats["errors"],
    )
    return stats
