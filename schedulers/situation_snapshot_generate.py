"""Situation Snapshot Generate — Scheduler DIRECT handler (v2).

5분 주기로 최근 이벤트를 수집하여 Situation Snapshot을 생성하고,
이전 snapshot과 비교하여 delta/evolution을 계산하여 DB에 저장한다.

T-06: delta_type, lifecycle_transition, risk_direction, change_summary,
      previous_snapshot_id 자동 계산 추가.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def handler() -> dict[str, Any]:
    """Situation Snapshot 생성 + Delta 계산 + 저장."""
    try:
        from watch_engine.trans_engine.situation_snapshot_builder import build_situation_snapshot
        from watch_engine.trans_engine.situation_snapshot_store import save_snapshot, get_snapshot_timeline
        from watch_engine.trans_engine.situation_evolution import compute_situation_evolution

        events = await _fetch_recent_events()
        if not events:
            return {"status": "success", "message": "No events to snapshot", "saved": 0}

        tenant_groups = _group_by_tenant(events)
        saved_count = 0

        for tenant_id, tenant_events in tenant_groups.items():
            try:
                snapshot = build_situation_snapshot(
                    events=tenant_events,
                    tenant_id=tenant_id,
                    audience="admin",
                )

                # T-06: 이전 snapshot 조회 + delta 계산
                situation_id = snapshot.get("situation_id", "")
                prev_snapshots = await get_snapshot_timeline(situation_id, limit=1)
                previous = prev_snapshots[0] if prev_snapshots else None

                evolution = compute_situation_evolution(previous, snapshot)
                snapshot["previous_snapshot_id"] = previous.get("id") if previous else None
                snapshot["delta_type"] = evolution.get("delta_type", "new")
                snapshot["lifecycle_transition"] = evolution.get("lifecycle_transition")
                snapshot["risk_direction"] = evolution.get("risk_direction", "stable")
                snapshot["change_summary"] = evolution.get("change_summary", "")

                result = await save_snapshot(snapshot)
                if result:
                    saved_count += 1
            except Exception as e:
                logger.error(f"Snapshot build/save error for {tenant_id}: {e}")

        return {
            "status": "success",
            "message": f"Saved {saved_count} snapshots from {len(tenant_groups)} tenants",
            "saved": saved_count,
            "tenants": len(tenant_groups),
        }

    except Exception as e:
        logger.error(f"situation_snapshot_generate handler error: {e}")
        return {"status": "error", "message": str(e)}


async def _fetch_recent_events() -> list[dict[str, Any]]:
    """최근 5분 이벤트 수집."""
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        result = (
            sb.table("watch_engine_events")
            .select("*")
            .gte("created_at", "now() - interval '5 minutes'")
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.warning(f"Event fetch failed (table may not exist): {e}")
        return []


def _group_by_tenant(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """tenant_id별 그룹화."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        tid = e.get("tenant_id") or "system"
        if tid not in groups:
            groups[tid] = []
        groups[tid].append(e)
    return groups
