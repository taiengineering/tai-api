"""경영 지표 라우터 (WO-14 StatsProvider).

Goal: G-ms4je4z3-33eada
- GET /stats/business — 매출·구독(MRR)·결제건전성·전환. 얇은 위임.
"""
from fastapi import APIRouter

from services.stats_provider_svc import get_stats

router = APIRouter(prefix="/stats", tags=["경영지표"])


@router.get("/business")
def business_stats():
    """경영 지표 종합."""
    return {"status": "success", "data": get_stats()}
