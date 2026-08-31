"""
routers/diagnosis_roi.py — v1.0.0

BE-07: ROI 집계 API

GET /diagnosis/{diagnosis_id}/roi
  - 단일 진단 결과를 기반으로 ROI 계산
  - result_data.roi 필드 캐시된 값 우선 (FN-04 무부하)
  - 없으면 실시간 계산 후 반환

POST /diagnosis/{diagnosis_id}/roi/refresh
  - 말이 사용되는 파일구조 변화 등 roi 재계산 + result_data 업데이트
─────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone

from db.supabase_client import get_supabase
from services.roi_calculator import build_full_roi_response, calculate_roi
from services.time import now_kst, serialize_external_utc

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/diagnosis", tags=["ROI 계산"])

VERSION = "1.0.0"


def _now_iso() -> str:
    return serialize_external_utc(now_kst())


# ─────────────────────────────────────────────────────────────────────────
# GET /diagnosis/{diagnosis_id}/roi
# ─────────────────────────────────────────────────────────────────────────
@router.get("/{diagnosis_id}/roi")
def get_diagnosis_roi(diagnosis_id: str):
    """
    진단 결과 기반 ROI 계산.

    result_data.roi 필드가 있으면 캐시된 값 반환 (FN-04 무부하).
    없으면 실시간 계산 후 반환.
    """
    supabase = get_supabase()

    # ① 진단 레코드 조회
    diag_res = supabase.table("factory_diagnosis_results") \
        .select("id, factory_id, rule_count, diagnosis_stage, result_data, schema_version") \
        .eq("id", diagnosis_id).limit(1).execute()

    if not diag_res.data:
        raise HTTPException(status_code=404, detail="진단 레코드를 찾을 수 없습니다.")

    diag = diag_res.data[0]
    result_data: dict = diag.get("result_data") or {}

    # ② 캐시된 roi 필드 있으면 바로 사용
    if result_data.get("roi") and isinstance(result_data["roi"], dict):
        # factory 정보도 잘 대하하여 반환
        factory_id = diag.get("factory_id")
        fac_res = supabase.table("factories") \
            .select("id, name, sector, employee_count, construction_amount") \
            .eq("id", factory_id).limit(1).execute()
        factory = fac_res.data[0] if fac_res.data else {}

        cached_roi = result_data["roi"]
        return {
            "status":  "success",
            "cached":  True,
            "data":    build_full_roi_response(factory, diag, result_data),
        }

    # ③ 실시간 계산
    factory_id = diag.get("factory_id")
    fac_res = supabase.table("factories") \
        .select("id, name, sector, employee_count, construction_amount") \
        .eq("id", factory_id).limit(1).execute()

    if not fac_res.data:
        raise HTTPException(status_code=404, detail="시설 정보를 찾을 수 없습니다.")

    factory = fac_res.data[0]
    response_data = build_full_roi_response(factory, diag, result_data)

    # ④ 계산된 roi를 result_data에 저장 (다음 호출에서 캐시된 값 사용)
    roi_snapshot = {
        "annual_penalty_risk_krw":   response_data["current_exposure"]["penalty_max_krw"],
        "tai_safe_annual_cost_krw":  response_data["tai_safe_plan"]["annual_cost_krw"],
        "payback_days":              response_data["comparison"]["payback_days"],
        "risk_reduction_percent":    response_data["comparison"]["risk_reduction_percent"],
        "calculated_at":             _now_iso(),
    }
    try:
        supabase.table("factory_diagnosis_results").update({
            "result_data": {**result_data, "roi": roi_snapshot},
        }).eq("id", diagnosis_id).execute()
    except Exception as e:
        log.warning("[ROI] roi 캐시 저장 실패 (무시): %s", e)

    return {"status": "success", "cached": False, "data": response_data}


# ─────────────────────────────────────────────────────────────────────────
# POST /diagnosis/{diagnosis_id}/roi/refresh
# ─────────────────────────────────────────────────────────────────────────
@router.post("/{diagnosis_id}/roi/refresh")
def refresh_diagnosis_roi(diagnosis_id: str):
    """
    ROI 재계산 + result_data 업데이트.
    result_data 내 obligations/exposure 변경 후 구조구조 ROI를 재생성할 때 사용.
    """
    supabase = get_supabase()

    diag_res = supabase.table("factory_diagnosis_results") \
        .select("id, factory_id, rule_count, result_data") \
        .eq("id", diagnosis_id).limit(1).execute()
    if not diag_res.data:
        raise HTTPException(status_code=404, detail="진단 레코드를 찾을 수 없습니다.")

    diag = diag_res.data[0]
    result_data: dict = diag.get("result_data") or {}

    fac_res = supabase.table("factories") \
        .select("id, name, sector, employee_count, construction_amount") \
        .eq("id", diag["factory_id"]).limit(1).execute()
    if not fac_res.data:
        raise HTTPException(status_code=404, detail="시설 정보를 찾을 수 없습니다.")

    factory = fac_res.data[0]
    response_data = build_full_roi_response(factory, diag, result_data)

    roi_snapshot = {
        "annual_penalty_risk_krw":  response_data["current_exposure"]["penalty_max_krw"],
        "tai_safe_annual_cost_krw": response_data["tai_safe_plan"]["annual_cost_krw"],
        "payback_days":             response_data["comparison"]["payback_days"],
        "risk_reduction_percent":   response_data["comparison"]["risk_reduction_percent"],
        "calculated_at":            _now_iso(),
    }

    supabase.table("factory_diagnosis_results").update({
        "result_data": {**result_data, "roi": roi_snapshot},
    }).eq("id", diagnosis_id).execute()

    return {"status": "success", "refreshed": True, "data": response_data}
