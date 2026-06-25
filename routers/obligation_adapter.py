"""Obligation Adapter API — v1.2.0 (CURSOR-TASK-002)

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

  POST /obligation-adapter/run-trigger/{factory_id}   (v1.2.0, CURSOR-TASK-002)
    1. Trigger Code Set 생성 (trigger_generator)
    2. semantic_clause 후보 생성 (trigger_obligation_generator)
    3. obligations 변환 (build_obligations_from_trigger_candidates)
    4. 요약 JSON 반환
    → V4 / evaluate_draft_for_facility 무수정

원칙:
  - V4 불변 (evaluate 재사용, 수정 안 함)
  - 정제레이어 불변
  - 라우터는 HTTP만 (변환 로직은 서비스에)
  - 새 판단/법령/threshold 생성 금지
  - 익명 진단 트랙(anonymous_diagnosis_results) 손대지 않음

v1.1.1: schema_version 값을 컬럼 한계(varchar 10)에 맞춰 "v4adapt"로 수정.
v1.2.0: POST /run-trigger/{factory_id} 추가 (CURSOR-TASK-002).
        V4 / Check Engine 무수정. 트리거 기반 후보 생성 연결.
v1.3.0: POST /from-instances/{factory_id} 추가 (CURSOR-TASK-001 Glue).
        obligation_instance → candidate → 기존 Adapter.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from db.supabase_client import get_supabase
from routers.applicability_api import evaluate as v4_evaluate
from services.obligation_instance_adapter import (
    obligation_instances_to_trigger_candidates,
)
from services.obligation_adapter_service import (
    build_obligations_from_trigger_candidates,
    build_obligations_from_v4,
    build_result_data,
)
from services.trigger_generator import generate_trigger_codes
from services.trigger_obligation_generator import generate_obligation_candidates

router = APIRouter(
    prefix="/obligation-adapter",
    tags=["Obligation Adapter (B안)"],
)

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
    supabase.table("factory_diagnosis_results").update(
        {"is_latest": False}
    ).eq("factory_id", factory_id).eq("sector", sector).eq("is_latest", True).execute()

    row = {
        "factory_id": factory_id,
        "sector": sector,
        "diagnosis_stage": 2,
        "input_data": {"factory_id": factory_id, "source": "V4_OBLIGATION_ADAPTER"},
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


@router.post("/run-trigger/{factory_id}")
def run_trigger_based_obligation_adapter(factory_id: str):
    """Trigger 기반 의무후보 생성 → obligations 변환 (v1.2.0).

    V4 / evaluate_draft_for_facility 무수정.
    Trigger Generator → semantic_clause 후보 → obligation_adapter_service 연결.

    Returns:
      {
        factory_id, trigger_count, candidate_count, matched_count,
        trigger_codes, obligations, status
      }
    """
    supabase = get_supabase()

    # Step 1: Trigger Code Set 생성
    try:
        trigger_codes = generate_trigger_codes(factory_id, supabase)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Step 2: semantic_clause 의무후보 생성
    candidates = generate_obligation_candidates(trigger_codes, supabase)

    # Step 3: obligations 변환 (기존 어댑터 서비스 재사용)
    adapter_result = build_obligations_from_trigger_candidates(
        candidates, factory_id, trigger_codes
    )

    return {
        "factory_id": factory_id,
        "trigger_count": len(trigger_codes),
        "candidate_count": len(candidates),
        "matched_count": adapter_result["obligation_count"],
        "trigger_codes": trigger_codes,
        "obligations": adapter_result["obligations"],
        "status": "ok",
        "source": adapter_result["source"],
    }


@router.post("/from-instances/{factory_id}")
def adapt_from_obligation_instances(factory_id: str):
    """obligation_instance(Applicability Engine) → 45CM obligations.

    Glue: obligation_instance → candidate → 기존 Adapter.
    Check Engine / 정제레이어 무수정.
    """
    t0 = time.perf_counter()
    supabase = get_supabase()

    t_fetch = time.perf_counter()
    candidates = obligation_instances_to_trigger_candidates(factory_id, supabase)
    fetch_ms = int((time.perf_counter() - t_fetch) * 1000)

    t_adapt = time.perf_counter()
    adapter_result = build_obligations_from_trigger_candidates(
        candidates, factory_id, trigger_codes=[]
    )
    adapt_ms = int((time.perf_counter() - t_adapt) * 1000)
    total_ms = int((time.perf_counter() - t0) * 1000)

    return {
        "status": "ok",
        "factory_id": factory_id,
        "candidate_count": len(candidates),
        "obligation_count": adapter_result["obligation_count"],
        "verdict": adapter_result["verdict"],
        "obligations": adapter_result["obligations"],
        "source": adapter_result["source"],
        "trace": {
            "fetch_rows_ms": fetch_ms,
            "adapter_ms": adapt_ms,
            "total_ms": total_ms,
        },
    }
