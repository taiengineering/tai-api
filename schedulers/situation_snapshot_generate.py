"""Situation Snapshot Generate — Scheduler DIRECT handler (v8).

5분 주기. Enrichment Pipeline 모듈 사용.
v8: 이벤트 소스를 engine_integrity_event + business_event로 수정.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from services.time import now_kst

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

                prev_snapshots = await get_snapshot_timeline(situation_id, limit=1)
                previous = prev_snapshots[0] if prev_snapshots else None

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
    """engine_integrity_event + business_event에서 최근 5분 이벤트 수집.

    event-stream API와 동일한 소스 사용.
    mock 포함 (Trans Engine은 PROD/SYN 모두 처리).
    """
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        stream: list[dict[str, Any]] = []

        # 1) engine_integrity_event — 무결성/장애 이벤트
        try:
            ie = (
                sb.table("engine_integrity_event")
                .select("id,tenant_id,flow_key,step_key,event_type,severity,description,environment,created_at")
                .gte("created_at", _since_5min())
                .order("created_at", desc=True)
                .limit(100)
                .execute()
            )
            for e in (ie.data or []):
                stream.append({
                    "event_id": str(e.get("id", "")),
                    "event_type": e.get("event_type", "unknown"),
                    "severity": e.get("severity", "WARNING"),
                    "tenant_id": e.get("tenant_id"),
                    "flow_key": e.get("flow_key"),
                    "step_key": e.get("step_key"),
                    "description": e.get("description", ""),
                    "source": "control",
                    "is_mock": e.get("environment") == "mock",
                    "environment": e.get("environment", "production"),
                    "created_at": e.get("created_at"),
                })
        except Exception as ex:
            logger.warning(f"integrity event fetch: {ex}")

        # 2) business_event — 워크플로우 이벤트
        try:
            be = (
                sb.table("business_event")
                .select("id,tenant_id,flow_key,step_key,event_type,result,environment,created_at")
                .gte("created_at", _since_5min())
                .order("created_at", desc=True)
                .limit(100)
                .execute()
            )
            for e in (be.data or []):
                result_val = e.get("result", "unknown")
                stream.append({
                    "event_id": str(e.get("id", "")),
                    "event_type": f"workflow.{result_val}" if result_val else "workflow.event",
                    "severity": "WARNING" if result_val == "failure" else "INFO",
                    "tenant_id": e.get("tenant_id"),
                    "flow_key": e.get("flow_key"),
                    "step_key": e.get("step_key"),
                    "description": f"{e.get('flow_key','')}.{e.get('step_key','')} → {result_val}",
                    "source": "workflow",
                    "is_mock": e.get("environment") == "mock",
                    "environment": e.get("environment", "production"),
                    "created_at": e.get("created_at"),
                })
        except Exception as ex:
            logger.warning(f"business event fetch: {ex}")

        stream.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return stream

    except Exception as e:
        logger.warning(f"_fetch_recent_events error: {e}")
        return []


def _since_5min() -> str:
    """5분 전 ISO timestamp."""
    return (now_kst() - timedelta(minutes=5)).isoformat()


def _group_by_tenant(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list] = {}
    for e in events:
        tid = e.get("tenant_id") or "system"
        if tid not in groups:
            groups[tid] = []
        groups[tid].append(e)
    return groups
