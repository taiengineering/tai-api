"""경영 지표 라우터 (WO-14 StatsProvider).

Goal: G-ms4je4z3-33eada (통계 대시보드 G-ms5pdquz-9e76e5)
- GET /stats/business — 매출·구독(MRR)·결제건전성·전환. 얇은 위임.
- GET /stats/dashboard — 이커머스 수준 통계(매출·고객·상품·마케팅 유입). days 파라미터로 기간 조정.
- GET /stats/funnel — (신규 운영자 통계) 진단 퍼널: 익명(실제/테스트 분리)→공개요청→유료전환.
"""
from fastapi import APIRouter, Query

from services.stats_dashboard_svc import get_dashboard
from services.stats_ops_svc import get_funnel
from services.stats_provider_svc import get_stats

router = APIRouter(prefix="/stats", tags=["경영지표"])


@router.get("/business")
def business_stats():
    """경영 지표 종합."""
    return {"status": "success", "data": get_stats()}


@router.get("/dashboard")
def dashboard_stats(days: int = Query(default=90, ge=7, le=365)):
    """통계 대시보드 — 매출·결제 / 고객·구독 / 상품·진단 / 마케팅 유입."""
    return {"status": "success", "data": get_dashboard(days)}


@router.get("/funnel")
def funnel_stats(days: int = Query(default=90, ge=7, le=365)):
    """진단 퍼널 — 익명진단(실제/테스트 분리) → 공개요청 → 유료전환."""
    return {"status": "success", "data": get_funnel(days)}
