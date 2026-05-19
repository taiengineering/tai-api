"""Situation Snapshot Generate — Scheduler DIRECT handler (v7 Refactored).

5분 주기. Enrichment Pipeline 모듈 사용.
"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def handler() -> dict[str, Any]:
    try:
        from watch_engine.trans_engine.situation_snapshot_builder import build_situation_snapshot
        from watch_engine.trans_engine.situation_snapshot_store import save_snapshot, get_snapshot_timeline
        from watch_engine.trans_engine.enrichment.delta_enrichment import apply_delta_enrichment
        from watch_engine.trans_engine.enrichment.attention_enrichment import apply_attention_enrichment
        from watch_engine.trans_engine.enrichment.guidance_enrichment import apply_guidance_enrichment
        from watch_engine.trans_engine.enrichment.learning_enrichment import apply_learning_enrichment
        from watch_engine.trans_engine.enrichment.closure_enrichment import apply_closure_enrichment

        events = await _fetch_recent_events()
        if not events:
            return {"status": "success", "message": "No events", "saved": 0}

        tenant_groups = _group_by_tenant(events)
        saved_count = 0

        for tenant_id, tenant_events in tenant_groups.items():
            try:
                snapshot = build_situation_snapshot(
                    events=tenant_events, tenant_id=tenant_id, audience="admin",
                )
                situation_id = snapshot.get("situation_id", "")

                # Previous snapshot for delta
                prev_snapshots = await get_snapshot_timeline(situation_id, limit=1)
                previous = prev_snapshots[0] if prev_snapshots else None

                # Enrichment Pipeline
                apply_delta_enrichment(snapshot, previous)
                apply_attention_enrichment(snapshot)
                apply_guidance_enrichment(snapshot)
                await apply_learning_enrichment(snapshot)
                await apply_closure_enrichment(snapshot)

                result = await save_snapshot(snapshot)
                if result:
                    saved_count += 1
            except Exception as e:
                logger.error(f"Snapshot error for {tenant_id}: {e}")

        return {
            "status": "success",
            "message": f"Saved {saved_count}/{len(tenant_groups)}",
            "saved": saved_count,
            "tenants": len(tenant_groups),
        }
    except Exception as e:
        logger.error(f"handler error: {e}")
        return {"status": "error", "message": str(e)}


async def _fetch_recent_events() -> list[dict[str, Any]]:
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        return (
            sb.table("watch_engine_events")
            .select("*")
            .gte("created_at", "now() - interval '5 minutes'")
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        ).data or []
    except Exception as e:
        logger.warning(f"Event fetch: {e}")
        return []


def _group_by_tenant(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list] = {}
    for e in events:
        tid = e.get("tenant_id") or "system"
        if tid not in groups:
            groups[tid] = []
        groups[tid].append(e)
    return groups
