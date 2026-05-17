# routers/watch_engine_intelligence_api.py — Operational Intelligence API
"""
\uc6b4\uc601 Intelligence \uc870\ud68c. Truth \uc0dd\uc131 \uae08\uc9c0.
recommendation / prediction / correlation / awareness \uc804\uc6a9.
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/watch/intelligence", tags=["\uc6b4\uc601\uc9c0\ub2a5"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


@router.get("/repeated-failures")
def get_repeated_failures(hours: int = 24):
    """\ubc18\ubcf5 \uc2e4\ud328 Intelligence."""
    try:
        from watch_engine.intelligence import analyze_repeated_failures
        results = analyze_repeated_failures(_sb(), hours=hours)
        return {"status": "success", "data": [r.to_dict() for r in results], "total": len(results)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/patterns")
def get_patterns(hours: int = 48):
    """\uc6b4\uc601 \ud328\ud134 \ucd94\uc138."""
    try:
        from watch_engine.intelligence import analyze_patterns
        results = analyze_patterns(_sb(), hours=hours)
        return {"status": "success", "data": [r.to_dict() for r in results], "total": len(results)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/tenant-degradation")
def get_tenant_degradation(hours: int = 24):
    """\ud14c\ub10c\ud2b8 \uc545\ud654 \uac10\uc9c0."""
    try:
        from watch_engine.intelligence import analyze_tenant_degradation
        results = analyze_tenant_degradation(_sb(), hours=hours)
        return {"status": "success", "data": [r.to_dict() for r in results], "total": len(results)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/recovery-recommendations")
def get_recovery_recommendations(event_type: str = None):
    """\ubcf5\uad6c \ucd94\ucc9c."""
    try:
        from watch_engine.intelligence import recommend_recovery
        results = recommend_recovery(_sb(), event_type=event_type)
        return {"status": "success", "data": [r.to_dict() for r in results], "total": len(results)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/summary")
def get_intelligence_summary(hours: int = 24):
    """Intelligence \uc694\uc57d."""
    try:
        from watch_engine.intelligence import (
            analyze_repeated_failures, analyze_patterns,
            analyze_tenant_degradation, recommend_recovery,
        )
        sb = _sb()

        repeated = analyze_repeated_failures(sb, hours=hours)
        patterns = analyze_patterns(sb, hours=hours * 2)
        degradation = analyze_tenant_degradation(sb, hours=hours)
        recovery = recommend_recovery(sb)

        # \uc704\ud5d8 \uc694\uc57d
        critical_repeated = sum(1 for r in repeated if r.severity == "CRITICAL")
        accelerating = sum(1 for p in patterns if p.details.get("trend") == "ACCELERATING")
        degrading_tenants = sum(1 for d in degradation if "\uc545\ud654" in d.summary)
        top_risk = max((r.risk_score for r in repeated), default=0)

        return {"status": "success", "data": {
            "repeated_failures": len(repeated),
            "critical_repeated": critical_repeated,
            "pattern_trends": len(patterns),
            "accelerating_trends": accelerating,
            "tenant_degradations": len(degradation),
            "degrading_tenants": degrading_tenants,
            "recovery_actions": len(recovery),
            "top_risk_score": top_risk,
            "analysis_hours": hours,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}
