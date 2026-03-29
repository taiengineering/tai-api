"""
어드민 대시보드 통계 라우터 — v1.0.0
prefix: /admin

엔드포인트:
  GET  /admin/stats         대시보드 통계 (dashboard_stats MV)
  POST /admin/stats/refresh MV 수동 갱신
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from db.supabase_client import get_supabase

router = APIRouter(prefix="/admin", tags=["어드민통계"])

VERSION = "1.0.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
