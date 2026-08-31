"""
엔진 모델 마스터 관리 라우터 — v1.0.0

대상 테이블: equipment_model_master (2,874건)

엔드포인트:
  GET  /engine-model/stats      전체 통계
  GET  /engine-model/filters    필터 옵션 목록 (동적 로드용)
  GET  /engine-model/list       목록 조회 (페이지네이션 + 필터)
  GET  /engine-model/{id}       단건 상세
  PATCH /engine-model/{id}      수정
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime, timezone
from db.supabase_client import get_supabase
from services.time import now_kst, serialize_external_utc

router = APIRouter(prefix="/engine-model", tags=["엔진모델마스터"])

VERSION = "1.0.0"

# 수정 허용 필드
PATCH_ALLOWED = {
    "manufacturer", "model_name", "equipment_std", "primary_equipment_std",
    "equipment_lv2", "model_year",
    "expected_life_years", "maintenance_cycle_months",
    "risk_score", "criticality_score", "replacement_cost_index",
    "certification_class", "country_of_origin",
    "source_type", "cert_match_status",
}


def _now_iso() -> str:
    return serialize_external_utc(now_kst())


# ─────────────────────────────────────────────────────
# GET /engine-model/stats  전체 통계
# ─────────────────────────────────────────────────────
@router.get("/stats")
async def get_model_stats():
    """모델 마스터 전체 통계 조회 (2,874건 전체 집계)"""
    supabase = get_supabase()
    try:
        res = supabase.table("equipment_model_master").select(
            "id, equipment_std, manufacturer, source_type, "
            "cert_match_status, equipment_lv2, risk_score"
        ).execute()
        rows = res.data or []

        std_set = set()
        mfr_set = set()
        source_dist: dict = {}
        lv2_dist: dict = {}
        cert_matched = 0
        cert_no_match = 0
        risk_total = 0
        risk_count = 0

        for row in rows:
            std = row.get("equipment_std") or ""
            mfr = row.get("manufacturer") or ""
            src = row.get("source_type") or "UNKNOWN"
            lv2 = row.get("equipment_lv2") or "미분류"
            cert = row.get("cert_match_status") or ""
            risk = row.get("risk_score")

            if std:
                std_set.add(std)
            if mfr:
                mfr_set.add(mfr)
            source_dist[src] = source_dist.get(src, 0) + 1
            lv2_dist[lv2] = lv2_dist.get(lv2, 0) + 1

            if cert == "MATCHED":
                cert_matched += 1
            elif cert == "NO_CERT_MATCH":
                cert_no_match += 1

            if risk is not None:
                risk_total += float(risk)
                risk_count += 1

        return {
            "status": "success",
            "data": {
                "total": len(rows),
                "unique_std": len(std_set),
                "unique_manufacturer": len(mfr_set),
                "cert_matched": cert_matched,
                "cert_no_match": cert_no_match,
                "avg_risk_score": round(risk_total / risk_count, 1) if risk_count else None,
                "source_distribution": dict(sorted(source_dist.items(), key=lambda x: -x[1])),
                "lv2_distribution": dict(sorted(lv2_dist.items(), key=lambda x: -x[1])),
                "version": VERSION,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# GET /engine-model/filters  필터 옵션 목록
# ※ /{model_id} 보다 먼저 선언해야 라우팅 충돌 없음
# ─────────────────────────────────────────────────────
@router.get("/filters")
async def get_model_filters():
    """필터용 동적 옵션 목록 — 전체 조회 후 Python set 중복 제거"""
    supabase = get_supabase()
    try:
        res = supabase.table("equipment_model_master").select(
            "equipment_std, manufacturer, equipment_lv2, source_type"
        ).execute()
        rows = res.data or []

        std_set = set()
        mfr_set = set()
        lv2_set = set()
        src_set = set()

        for row in rows:
            if row.get("equipment_std"):
                std_set.add(row["equipment_std"])
            if row.get("manufacturer"):
                mfr_set.add(row["manufacturer"])
            if row.get("equipment_lv2"):
                lv2_set.add(row["equipment_lv2"])
            if row.get("source_type"):
                src_set.add(row["source_type"])

        return {
            "status": "success",
            "data": {
                "equipment_std_list": sorted(std_set),
                "manufacturer_list": sorted(mfr_set),
                "lv2_list": sorted(lv2_set),
                "source_type_list": sorted(src_set),
                "cert_match_status_list": ["MATCHED", "NO_CERT_MATCH"],
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# GET /engine-model/list  목록 조회 (페이지네이션 + 필터)
# ─────────────────────────────────────────────────────
@router.get("/list")
async def list_models(
    search: Optional[str] = Query(None, description="model_name/manufacturer/equipment_std 통합검색"),
    equipment_std: Optional[str] = Query(None, description="설비표준명 정확히 일치"),
    manufacturer: Optional[str] = Query(None, description="제조사 ilike 검색"),
    equipment_lv2: Optional[str] = Query(None, description="설비 lv2 분류 정확히 일치"),
    source_type: Optional[str] = Query(None, description="소스 타입 정확히 일치"),
    cert_match_status: Optional[str] = Query(None, description="인증 매칭 상태 정확히 일치"),
    risk_min: Optional[int] = Query(None, ge=0, le=100, description="risk_score 최솟값"),
    risk_max: Optional[int] = Query(None, ge=0, le=100, description="risk_score 최댓값"),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
):
    """모델 마스터 목록 (페이지네이션 + 7종 필터)"""
    supabase = get_supabase()
    try:
        query = supabase.table("equipment_model_master").select(
            "id, manufacturer, model_name, equipment_std, primary_equipment_std, "
            "equipment_lv2, model_year, expected_life_years, maintenance_cycle_months, "
            "risk_score, criticality_score, replacement_cost_index, "
            "certification_class, source_type, cert_match_status, "
            "country_of_origin, model_source, created_at",
            count="exact"
        )

        # 필터 적용
        if equipment_std:
            query = query.eq("equipment_std", equipment_std)
        if manufacturer:
            query = query.ilike("manufacturer", f"%{manufacturer}%")
        if equipment_lv2:
            query = query.eq("equipment_lv2", equipment_lv2)
        if source_type:
            query = query.eq("source_type", source_type)
        if cert_match_status:
            query = query.eq("cert_match_status", cert_match_status)
        if risk_min is not None:
            query = query.gte("risk_score", risk_min)
        if risk_max is not None:
            query = query.lte("risk_score", risk_max)
        if search:
            query = query.or_(
                f"model_name.ilike.%{search}%,"
                f"manufacturer.ilike.%{search}%,"
                f"equipment_std.ilike.%{search}%"
            )

        # 페이지네이션
        offset = (page - 1) * page_size
        query = query.order("equipment_std").order("manufacturer").range(offset, offset + page_size - 1)
        res = query.execute()

        total = res.count or 0
        return {
            "status": "success",
            "data": {
                "items": res.data or [],
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size if total else 0,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# GET /engine-model/{model_id}  단건 상세
# ─────────────────────────────────────────────────────
@router.get("/{model_id}")
async def get_model_detail(model_id: str):
    """모델 마스터 단건 전체 상세 조회"""
    supabase = get_supabase()
    try:
        res = supabase.table("equipment_model_master").select("*").eq(
            "id", model_id
        ).limit(1).execute()

        rows = res.data or []
        if not rows:
            raise HTTPException(status_code=404, detail="모델을 찾을 수 없습니다.")

        return {"status": "success", "data": rows[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# PATCH /engine-model/{model_id}  수정
# ─────────────────────────────────────────────────────
@router.patch("/{model_id}")
async def update_model(model_id: str, body: dict):
    """모델 마스터 수정 (허용 필드만)"""
    supabase = get_supabase()
    try:
        update_data = {k: v for k, v in body.items() if k in PATCH_ALLOWED}
        if not update_data:
            raise HTTPException(status_code=400, detail="수정할 필드가 없습니다.")

        res = supabase.table("equipment_model_master").update(
            update_data
        ).eq("id", model_id).execute()

        if not res.data:
            raise HTTPException(status_code=404, detail="모델을 찾을 수 없습니다.")

        return {
            "status": "success",
            "message": "모델이 수정됐습니다.",
            "data": res.data[0],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
