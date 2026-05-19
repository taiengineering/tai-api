"""Situation Snapshot Generate — Scheduler DIRECT handler (v6 FINAL).

5분 주기. Snapshot → Delta → Attention → Guidance → Learning → Closure → DB.

T-06: delta, lifecycle_transition, risk_direction, change_summary
T-08: attention_score/level, requires_attention, attention_summary
T-09: guidance_level, recommended_actions/checks/order, guidance_summary
T-10: last_response_outcome, learned_effectiveness, recurrence_risk, operational_memory_notes
T-11: closure_status, resolved_by, resolved_at (from existing closure records)
"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)

async def handler() -> dict[str, Any]:
    try:
        from watch_engine.trans_engine.situation_snapshot_builder import build_situation_snapshot
        from watch_engine.trans_engine.situation_snapshot_store import save_snapshot, get_snapshot_timeline
        from watch_engine.trans_engine.situation_evolution import compute_situation_evolution
        from watch_engine.trans_engine.attention_engine import enrich_snapshot_attention
        from watch_engine.trans_engine.response_guidance import enrich_snapshot_guidance
        from watch_engine.trans_engine.operational_memory import build_operational_memory

        events = await _fetch_recent_events()
        if not events:
            return {"status": "success", "message": "No events", "saved": 0}

        tenant_groups = _group_by_tenant(events)
        saved_count = 0

        for tenant_id, tenant_events in tenant_groups.items():
            try:
                snapshot = build_situation_snapshot(events=tenant_events, tenant_id=tenant_id, audience="admin")
                situation_id = snapshot.get("situation_id", "")

                prev_snapshots = await get_snapshot_timeline(situation_id, limit=1)
                previous = prev_snapshots[0] if prev_snapshots else None

                evolution = compute_situation_evolution(previous, snapshot)
                snapshot["previous_snapshot_id"] = previous.get("id") if previous else None
                snapshot["delta_type"] = evolution.get("delta_type", "new")
                snapshot["lifecycle_transition"] = evolution.get("lifecycle_transition")
                snapshot["risk_direction"] = evolution.get("risk_direction", "stable")
                snapshot["change_summary"] = evolution.get("change_summary", "")

                enrich_snapshot_attention(snapshot)
                enrich_snapshot_guidance(snapshot)

                # T-10: learning
                try:
                    memory = await build_operational_memory(situation_id)
                    snapshot["learned_effectiveness"] = memory.get("learned_effectiveness")
                    snapshot["recurrence_risk"] = memory.get("recurrence_risk", "low")
                    snapshot["operational_memory_notes"] = " ".join(memory.get("memory_notes", []))
                    if memory.get("outcomes"):
                        outcomes = memory["outcomes"]
                        snapshot["last_response_outcome"] = max(outcomes, key=outcomes.get) if outcomes else None
                except Exception:
                    pass

                # T-11: closure status from existing closures
                try:
                    from watch_engine.trans_engine.closure_workflow import get_closure_history
                    closures = await get_closure_history(situation_id)
                    if closures:
                        latest_c = closures[0]
                        snapshot["closure_status"] = latest_c.get("resolution_type")
                        snapshot["resolved_by"] = latest_c.get("operator_id")
                        snapshot["resolved_at"] = latest_c.get("closed_at")
                        snapshot["closure_summary"] = latest_c.get("resolution_summary", "")
                except Exception:
                    pass

                result = await save_snapshot(snapshot)
                if result: saved_count += 1
            except Exception as e:
                logger.error(f"Snapshot error for {tenant_id}: {e}")

        return {"status": "success", "message": f"Saved {saved_count}/{len(tenant_groups)}",
                "saved": saved_count, "tenants": len(tenant_groups)}
    except Exception as e:
        logger.error(f"handler error: {e}")
        return {"status": "error", "message": str(e)}

async def _fetch_recent_events() -> list[dict[str, Any]]:
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        return (sb.table("watch_engine_events").select("*")
                .gte("created_at", "now() - interval '5 minutes'")
                .order("created_at", desc=True).limit(100).execute()).data or []
    except Exception as e:
        logger.warning(f"Event fetch: {e}"); return []

def _group_by_tenant(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    g: dict[str, list] = {}
    for e in events:
        t = e.get("tenant_id") or "system"
        if t not in g: g[t] = []
        g[t].append(e)
    return g
