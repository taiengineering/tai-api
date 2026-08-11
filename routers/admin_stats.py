"""
어드민 대시보드 통계 라우터 — v1.1.0
prefix: /admin

엔드포인트:
  GET  /admin/stats                    대시보드 통계 (dashboard_stats MV)
  POST /admin/stats/refresh            MV 수동 갱신
  GET  /admin/stats/diagnosis-funnel   A. 진단 퍼널 (RPC stats_diagnosis_funnel)
  GET  /admin/stats/customer-sites     C. 고객사·사업장 (RPC stats_customer_sites)

집계 규약: RPC 가 { summary, chart, by_* } jsonb 반환 → 여기서 { status, data } 로 래핑.
기간 파라미터: start_date, end_date (YYYY-MM-DD), period (daily|weekly|monthly).
"""
from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timezone, date, timedelta
from typing import Optional
from db.supabase_client import get_supabase

router = APIRouter(prefix="/admin", tags=["어드민통계"])

VERSION = "1.1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_range(start_date: Optional[str], end_date: Optional[str]) -> tuple[str, str]:
    """미지정 시 최근 30일. YYYY-MM-DD 문자열 반환."""
    today = date.today()
    e = end_date or today.isoformat()
    s = start_date or (today - timedelta(days=30)).isoformat()
    return s, e


def _period(period: Optional[str]) -> str:
    p = (period or "daily").lower()
    return p if p in ("daily", "weekly", "monthly") else "daily"


# ─────────────────────────────────────────────────────
# GET /admin/stats  대시보드 통계 (MV 기반)
# ─────────────────────────────────────────────────────
@router.get("/stats")
async def get_dashboard_stats():
    """
    dashboard_stats Materialized View 기반 통계 조회.
    빠른 응답 보장 (MV 직접 조회).
    """
    supabase = get_supabase()
    try:
        res = supabase.table("dashboard_stats").select("*").limit(1).execute()
        rows = res.data or []
        if not rows:
            # MV 비어있으면 갱신 후 재조회
            supabase.rpc("refresh_dashboard_stats").execute()
            res = supabase.table("dashboard_stats").select("*").limit(1).execute()
            rows = res.data or []

        data = rows[0] if rows else {}
        return {
            "status": "success",
            "data": {
                "total_companies":       data.get("total_companies", 0),
                "total_factories":       data.get("total_factories", 0),
                "active_contracts":      data.get("active_contracts", 0),
                "total_users":           data.get("total_users", 0),
                "total_surveys":         data.get("total_surveys", 0),
                "diagnosed_surveys":     data.get("diagnosed_surveys", 0),
                "total_inspection_sets": data.get("total_inspection_sets", 0),
                "completed_inspections": data.get("completed_inspections", 0),
                "overdue_inspections":   data.get("overdue_inspections", 0),
                "upcoming_inspections":  data.get("upcoming_inspections", 0),
                "total_equipment":       data.get("total_equipment", 0),
                "equipment_overdue":     data.get("equipment_overdue", 0),
                "synced_at":             data.get("synced_at"),
                "version":               VERSION,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# POST /admin/stats/refresh  MV 수동 갱신
# ─────────────────────────────────────────────────────
@router.post("/stats/refresh")
async def refresh_dashboard_stats():
    """dashboard_stats MV 수동 갱신"""
    supabase = get_supabase()
    try:
        supabase.rpc("refresh_dashboard_stats").execute()
        return {
            "status": "success",
            "message": "dashboard_stats MV가 갱신됐습니다.",
            "data": {"refreshed_at": _now_iso()}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# GET /admin/stats/diagnosis-funnel  A. 진단 퍼널
# ─────────────────────────────────────────────────────
@router.get("/stats/diagnosis-funnel")
async def get_diagnosis_funnel(
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    period: Optional[str] = Query("daily", description="daily|weekly|monthly"),
):
    """
    익명진단·공개요청·유료전환 퍼널.
    summary(anon_total/anon_real/anon_test/paid_total/pub_total/pub_pending/conv_rate)
    + chart(기간별 익명진단 total/real) + by_source + pub_status.
    test 트래픽(factory_test·runtime_compiler_projection)은 anon_real 에서 제외.
    """
    s, e = _resolve_range(start_date, end_date)
    supabase = get_supabase()
    try:
        res = supabase.rpc(
            "stats_diagnosis_funnel",
            {"p_start": s, "p_end": e, "p_period": _period(period)},
        ).execute()
        return {"status": "success", "data": res.data or {}, "range": {"start": s, "end": e, "period": _period(period)}}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


# ─────────────────────────────────────────────────────
# GET /admin/stats/customer-sites  C. 고객사·사업장
# ─────────────────────────────────────────────────────
@router.get("/stats/customer-sites")
async def get_customer_sites(
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    period: Optional[str] = Query("daily", description="daily|weekly|monthly"),
):
    """
    고객사·사업장 현황.
    summary(companies_total/factories_total/new_companies/new_factories)
    + chart(기간별 신규등록) + by_sector + by_region + by_size(직원수 구간).
    분포는 companies 기준(factories 분석축 미충전).
    """
    s, e = _resolve_range(start_date, end_date)
    supabase = get_supabase()
    try:
        res = supabase.rpc(
            "stats_customer_sites",
            {"p_start": s, "p_end": e, "p_period": _period(period)},
        ).execute()
        return {"status": "success", "data": res.data or {}, "range": {"start": s, "end": e, "period": _period(period)}}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))
