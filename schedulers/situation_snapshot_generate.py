"""Situation Snapshot Generate — Scheduler DIRECT handler.

5분 주기로 최근 이벤트를 수집하여 Situation Snapshot을 생성하고 DB에 저장한다.

DIRECT handler protocol:
  - async def handler() -> dict
  - {"status": "success"|"error", "message": str}
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def handler() -> dict[str, Any]:
    """Situation Snapshot 생성 + 저장."""
    try:
        from watch_engine.trans_engine.situation_snapshot_builder import build_situation_snapshot
        from watch_engine.trans_engine.situation_snapshot_store import save_snapshot

        # 최근 이벤트 수집
        events = await _fetch_recent_events()
        if not events:
            return {"status": "success", "message": "No events to snapshot", "saved": 0}

        # tenant별 그룹화
        tenant_groups = _group_by_tenant(events)
        saved_count = 0

        for tenant_id, tenant_events in tenant_groups.items():
            try:
                snapshot = build_situation_snapshot(
                    events=tenant_events,
                    tenant_id=tenant_id,
                    audience="admin",
                )
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
    """최근 5분 이벤트 수집 (event-stream API 내부 호출)."""
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()

        # watch_engine_events 테이블에서 최근 5분 이벤트
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
        # fallback: 빈 리스트 (테이블 미존재 시 정상 종료)
        return []


def _group_by_tenant(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """tenant_id별 그룹화. tenant_id 없으면 'system'."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        tid = e.get("tenant_id") or "system"
        if tid not in groups:
            groups[tid] = []
        groups[tid].append(e)
    return groups
