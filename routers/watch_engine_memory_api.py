# routers/watch_engine_memory_api.py — Operational Memory API
"""
운영 메모리 자동 동기화 + 안정성 + 복구 효과.
"""

import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/watch-engine/memory", tags=["운영메모리"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


@router.get("/status")
def get_memory_status():
    """운영 메모리 요약."""
    try:
        from watch_engine.knowledge.stability import compute_stability, get_recovery_effectiveness
        sb = _sb()

        stability = compute_stability(sb, hours=24)
        effectiveness = get_recovery_effectiveness(sb)

        # Pattern summary
        patterns = sb.table("incident_pattern_registry") \
            .select("pattern_key,flow_key,event_type,repeat_count,resolution_success_rate") \
            .order("repeat_count", desc=True).limit(5).execute()

        # Worsening detection: patterns where repeat_count > 3 and success_rate < 50
        worsening = [p for p in (patterns.data or [])
                     if p.get("repeat_count", 0) > 3
                     and (p.get("resolution_success_rate") or 100) < 50]

        return {"status": "success", "data": {
            "stability": stability,
            "recovery_effectiveness": effectiveness,
            "top_patterns": patterns.data or [],
            "worsening_patterns": worsening,
        }}
    except Exception as e:
        logger.error("Memory status: %s", e)
        return {"status": "error", "message": str(e)}


@router.get("/stability")
def get_stability(hours: int = 24):
    """워크플로우 안정성."""
    try:
        from watch_engine.knowledge.stability import compute_stability
        results = compute_stability(_sb(), hours=hours)
        return {"status": "success", "data": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/recovery-effectiveness")
def get_effectiveness():
    """복구 효과 랭킹."""
    try:
        from watch_engine.knowledge.stability import get_recovery_effectiveness
        results = get_recovery_effectiveness(_sb())
        return {"status": "success", "data": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/sync")
def sync_patterns():
    """패턴 자동 갱신 (수동)."""
    try:
        from watch_engine.knowledge.pattern_updater import update_patterns
        result = update_patterns()
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}
