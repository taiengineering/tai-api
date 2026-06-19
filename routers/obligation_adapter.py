"""Obligation Adapter API — v1.1.1 (WO-USER-VISIBLE-BRIDGE-IMPL-002)

B안 어댑터 라우터 (HTTP only).

흐름:
  GET /obligation-adapter/{factory_id}
    1. V4 evaluate() 호출 (routers.applicability_api.evaluate)
    2. applicability_conditions 조회 → conditions_by_id 조립
    3. obligation_adapter_service.build_obligations_from_v4() 호출
    4. result_data.obligations 호환 JSON 반환

  POST /obligation-adapter/{factory_id}/persist   (v1.1.0, Track A 저장 배선)
    1~3 동일
    4. build_result_data() → factory_diagnosis_results 저장 (is_latest=true)
    → 이후 정제레이어 GET /diagnosis/transform/latest/{factory_id}로 가시화

원칙:
  - V4 불변 (evaluate 재사용, 수정 안 함)
  - 정제레이어 불변
  - 라우터는 HTTP만 (변환 로직은 서비스에)
  - 새 판단/법령/threshold 생성 금지
  - 익명 진단 트랙(anonymous_diagnosis_results) 손대지 않음

v1.1.1: schema_version 값을 컬럼 한계(varchar 10)에 맞춰 "v4adapt"로 수정.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from db.supabase_client import get_supabase
from routers.applicability_api import evaluate as v4_evaluate
from services.obligation_adapter_service import (
    build_obligations_from_v4,
    build_result_data,
)

router = APIRouter(
    prefix="/obligation-adapter",
    tags=["Obligation Adapter (B안)"],
)

# schema_version 컬럼은 varchar(10). 10자 이하 유지 필수.
SCHEMA_VERSION = "v4adapt"


def _load_conditions_by_id() -> Dict[str, Dict[str, Any]]:
    """ACTIVE applicability_conditions → {id: row}."""
    supabase = get_supabase()
    cond_res = (
        supabase.table("applicability_conditions")
        .select("id, law_name, appendix_no, action_type, action_text, "
                "industry_name, required_count, sector, status")
        .eq("status", "ACTIVE")
        .execute()
    )
    return {str(c["id"]): c for c in (cond_res.data or [])}


def _adapt(factory_id: str) -> Dict[str, Any]:
    """V4 평가 → obligations 변환 (공통 코어)."""
    v4_result = v4_evaluate(factory_id=factory_id, save=False)
    conditions_by_id = _load_conditions_by_id()
    adapter_result = build_obligations_from_v4(v4_result, conditions_by_id)
    return {"v4_result": v4_result, "adapter_result": adapter_result}


@router.get("/{factory_id}")
def adapt_obligations(factory_id: str):
    """V4 verdict → result_data.obligations 변환 (조회 전용)."""
    out = _adapt(factory_id)
    result = out["adapter_result"]
    return {
        "status": "success",
        "factory_id": factory_id,
        "verdict": result["verdict"],
        "obligation_count": result["obligation_count"],
        "obligations": result["obligations"],
        "source": result["source"],
    }


@router.post("/{factory_id}/persist")
def persist_obligations(factory_id: str):
    """어댑터 obligations → factory_diagnosis_results 저장 (Track A 배선).

    이후 정제레이어 GET /diagnosis/transform/latest/{factory_id}로
    사용자 화면까지 도달.
    """
    out = _adapt(factory_id)
    v4_result = out["v4_result"]
    adapter_result = out["adapter_result"]

    if adapter_result["obligation_count"] == 0:
        raise HTTPException(
            status_code=422,
            detail="MATCH된 의무가 없어 저장할 obligations가 없습니다.",
        )

    result_data = build_result_data(adapter_result, v4_result)
    now_iso = datetime.now(timezone.utc).isoformat()
    sector = v4_result.get("facility_sector") or "INDUSTRIAL"

    supabase = get_supabase()

    # 기존 is_latest=true 해제 (같은 factory_id + sector)
    supabase.table("factory_diagnosis_results").update(
        {"is_latest": False}
    ).eq("factory_id", factory_id).eq("sector", sector).eq("is_latest", True).execute()

    # 신규 저장
    row = {
        "factory_id": factory_id,
        "sector": sector,
        "diagnosis_stage": 2,
        "input_data": {
            "factory_id": factory_id,
            "source": "V4_OBLIGATION_ADAPTER",
        },
        "result_data": result_data,
        "rule_count": adapter_result["obligation_count"],
        "is_latest": True,
        "schema_version": SCHEMA_VERSION,
        "created_at": now_iso,
    }
    ins = supabase.table("factory_diagnosis_results").insert(row).execute()
    if not ins.data:
        raise HTTPException(status_code=500, detail="factory_diagnosis_results 저장 실패")

    saved = ins.data[0]
    return {
        "status": "success",
        "factory_id": factory_id,
        "diagnosis_id": str(saved.get("id")),
        "verdict": adapter_result["verdict"],
        "obligation_count": adapter_result["obligation_count"],
        "is_latest": True,
        "source": adapter_result["source"],
        "next": f"GET /diagnosis/transform/latest/{factory_id}",
    }
