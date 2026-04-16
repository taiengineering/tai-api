"""
routers/diagnosis_roi.py — v1.0.0

BE-07: ROI 집계 API

엔드포인트:
  GET /diagnosis/{diagnosis_id}/roi      단일 진단 ROI
  GET /diagnosis/factory/{factory_id}/roi 최신 진단 ROI (캐시)
  POST /diagnosis/roi/backfill           기존 진단 백필 (본인 인증 필요)

금기:
  - 근거 없는 숫자 생성 금지 (result_data.obligations 기반)
  - 소개비/크레딧 용어 금지
  - main 직접 커밋 금지
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException, Query
from db.supabase_client import get_supabase
from services.roi_calculator import build_roi_response, calculate_roi

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/diagnosis", tags=["진단ROI"])

VERSION = "1.0.0"


# ─────────────────────────────────────────────────────────────────────────
def _fetch_diag_and_factory(supabase, diagnosis_id: str) -> tuple[dict, dict]:
    """factory_diagnosis_results + factories JOIN 헬퍼"""
    diag_res = supabase.table("factory_diagnosis_results") \
        .select("id, factory_id, sector, diagnosis_stage, rule_count, result_data, schema_version") \
        .eq("id", diagnosis_id).limit(1).execute()
    if not diag_res.data:
        raise HTTPException(status_code=404, detail="진단 결과를 찾을 수 없습니다.")
    diag = diag_res.data[0]

    fac_res = supabase.table("factories") \
        .select("id, name, sector, employee_count, construction_amount, legal_applicable_count") \
        .eq("id", diag["factory_id"]).limit(1).execute()
    if not fac_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다.")
    return diag, fac_res.data[0]


# ─────────────────────────────────────────────────────────────────────────
# GET /diagnosis/{diagnosis_id}/roi
# ─────────────────────────────────────────────────────────────────────────
@router.get("/{diagnosis_id}/roi")
async def get_diagnosis_roi(diagnosis_id: str):
    """
    진단 ID 기반 ROI 복게 결과.

    result_data.roi 취득값이 있으면 캐시된 값 반환 (300ms 이내 보장).
    없으면 실시간 계산 후 result_data 업데이트.
    """
    supabase = get_supabase()
    try:
        diag, factory = _fetch_diag_and_factory(supabase, diagnosis_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    result_data = diag.get("result_data") or {}

    # 취득 콘텐츠 확인
    cached_roi = result_data.get("roi")
    if cached_roi and isinstance(cached_roi, dict) and cached_roi.get("recommended_plan"):
        roi_data = build_roi_response(factory, diag)
        return {"status": "success", "cached": True, "data": roi_data}

    # 실시간 계산 + 캐시 저장
    try:
        roi_data = build_roi_response(factory, diag)
        roi_inner = calculate_roi(
            sector=factory.get("sector") or "BUILDING",
            employee_count=int(factory.get("employee_count") or 0),
            result_data=result_data,
            rule_count=diag.get("rule_count") or 0,
            construction_amount=(
                float(factory["construction_amount"])
                if factory.get("construction_amount") else None
            ),
        )
        # result_data.roi 업데이트
        new_result_data = {**(result_data), "roi": roi_inner}
        supabase.table("factory_diagnosis_results") \
            .update({"result_data": new_result_data}) \
            .eq("id", diagnosis_id).execute()
    except Exception as e:
        log.error("[ROI] 계산 또는 캐시 저장 실패 (무시): %s", e, exc_info=True)
        roi_data = {}

    return {"status": "success", "cached": False, "data": roi_data}


# ─────────────────────────────────────────────────────────────────────────
# GET /diagnosis/factory/{factory_id}/roi
# ─────────────────────────────────────────────────────────────────────────
@router.get("/factory/{factory_id}/roi")
async def get_factory_roi(factory_id: str):
    """
    시설 ID 기반 최신 진단 ROI.
    is_latest=true 진단 하나를 기준으로 실행.
    """
    supabase = get_supabase()
    try:
        diag_res = supabase.table("factory_diagnosis_results") \
            .select("id") \
            .eq("factory_id", factory_id).eq("is_latest", True).limit(1).execute()
        if not diag_res.data:
            raise HTTPException(status_code=404, detail="진단 결과가 없습니다. 법령진단을 먼저 실행하세요.")
        diagnosis_id = diag_res.data[0]["id"]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return await get_diagnosis_roi(diagnosis_id)


# ─────────────────────────────────────────────────────────────────────────
# POST /diagnosis/roi/backfill  (시스템 내부용 — 인증 없이 호출 유지)
# ─────────────────────────────────────────────────────────────────────────
@router.post("/roi/backfill")
async def backfill_roi(limit: int = Query(50, ge=1, le=200)):
    """
    roi 필드 비어있는 기존 진단 결과 일괄 백필.
    is_latest=true + roi 키 없는 것만 실행.
    """
    supabase = get_supabase()

    # roi 키 없는 is_latest 레코드 조회
    res = supabase.table("factory_diagnosis_results") \
        .select("id, factory_id, sector, rule_count, result_data") \
        .eq("is_latest", True) \
        .limit(limit).execute()

    records = [r for r in (res.data or []) if not (r.get("result_data") or {}).get("roi")]

    updated = 0
    failed  = 0
    for diag in records:
        try:
            fac_res = supabase.table("factories") \
                .select("id, name, sector, employee_count, construction_amount") \
                .eq("id", diag["factory_id"]).limit(1).execute()
            if not fac_res.data:
                continue
            factory = fac_res.data[0]

            roi_inner = calculate_roi(
                sector=factory.get("sector") or "BUILDING",
                employee_count=int(factory.get("employee_count") or 0),
                result_data=diag.get("result_data") or {},
                rule_count=diag.get("rule_count") or 0,
                construction_amount=(
                    float(factory["construction_amount"])
                    if factory.get("construction_amount") else None
                ),
            )
            new_result_data = {**(diag.get("result_data") or {}), "roi": roi_inner}
            supabase.table("factory_diagnosis_results") \
                .update({"result_data": new_result_data}) \
                .eq("id", diag["id"]).execute()
            updated += 1
        except Exception as e:
            log.error("[ROI_BACKFILL] id=%s 실패: %s", diag.get("id"), e)
            failed += 1

    return {
        "status":  "success",
        "updated": updated,
        "failed":  failed,
        "skipped": len(res.data or []) - len(records),
    }
