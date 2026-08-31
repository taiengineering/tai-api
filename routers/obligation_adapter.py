"""Obligation Adapter API — v1.3.2 (WO-CREATEDBY-FIX-001)

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

  POST /obligation-adapter/from-instances/{factory_id}   (v1.3.0 Glue, v1.3.1 persist 옵션)
    obligation_instance → candidate → 기존 Adapter.
    persist=true 시 기존 운영 Persist(_persist_result_data) 로 factory_diagnosis_results 저장.

원칙:
  - V4 불변 (evaluate 재사용, 수정 안 함)
  - 정제레이어 불변
  - 라우터는 HTTP만 (변환 로직은 서비스에)
  - 새 판단/법령/threshold 생성 금지
  - 익명 진단 트랙(anonymous_diagnosis_results) 손대지 않음

v1.1.1: schema_version 값을 컴럼 한계(varchar 10)에 맞춰 "v4adapt"로 수정.
v1.2.0: POST /run-trigger/{factory_id} 추가 (CURSOR-TASK-002).
v1.3.0: POST /from-instances/{factory_id} 추가 (CURSOR-TASK-001 Glue).
v1.3.1: /from-instances에 persist 옵션 추가 (WO-OPERATIONAL-INTEGRATION-001).
        새 Persist/Service/Adapter 없음 — _persist_result_data로 기존 저장 로직 재사용.
        기본 persist=false → 기존 동작 불변.
v1.3.2: persist 시 created_by 보강 (WO-CREATEDBY-FIX-001).
        옵션 Authorization 헤더 → 유효 토큰이면 users.id를 created_by에 저장(권한 컬럼만).
        토큰 없음/무효(서비스·시스템 실행) → created_by 미설정(기존 동작 유지, 억지 ID 금지).
        result_data/obligations/rule_count/verdict 등 불변. 새 Service/Router 없음 —
        기존 get_current_user 재사용.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException

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
from services.time import now_kst, serialize_external_utc

router = APIRouter(
    prefix="/obligation-adapter",
    tags=["Obligation Adapter (B안)"],
)

SCHEMA_VERSION = "v4adapt"


def _optional_user_id(authorization: Optional[str]) -> Optional[str]:
    """Authorization 헤더가 유효하면 users.id 반환, 아니면 None (WO-CREATEDBY-FIX-001).

    기존 get_current_user 로직 재사용 — 새 인증/판단 로직 없음.
    토큰 없음/무효/사용자 없음 → None (서비스·시스템 실행 시 created_by 미설정, 억지 ID 금지).
    """
    if not authorization:
        return None
    try:
        from routers.auth import get_current_user
        user = get_current_user(authorization=authorization)
        uid = user.get("id") if user else None
        return str(uid) if uid else None
    except Exception:
        return None


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


def _factory_sector(factory_id: str) -> str:
    """factories.sector 조회. 없으면 INDUSTRIAL 폴백.

    from-instances persist에는 v4_result가 없으므로 sector를 여기서 공급.
    """
    try:
        supabase = get_supabase()
        res = (
            supabase.table("factories")
            .select("sector")
            .eq("id", factory_id)
            .limit(1)
            .execute()
        )
        if res.data:
            return str(res.data[0].get("sector") or "INDUSTRIAL").upper()
    except Exception:
        pass
    return "INDUSTRIAL"


def _persist_result_data(
    factory_id: str,
    sector: str,
    result_data: Dict[str, Any],
    obligation_count: int,
    source: str,
    created_by: Optional[str] = None,
) -> str:
    """기존 운영 Persist 쓰기 로직 (factory_diagnosis_results 저장 + is_latest 토글).

    /persist 와 /from-instances(persist=true)가 공유. 새 저장 로직 아니라 기존 배선 추출.
    이전 동작(/persist v1.1.0)과 동일한 컴럼/토글.
    WO-CREATEDBY-FIX-001: created_by가 주어지면 권한 컬럼만 추가 채움(나머지 불변).
    """
    supabase = get_supabase()
    supabase.table("factory_diagnosis_results").update(
        {"is_latest": False}
    ).eq("factory_id", factory_id).eq("sector", sector).eq("is_latest", True).execute()

    row = {
        "factory_id": factory_id,
        "sector": sector,
        "diagnosis_stage": 2,
        "input_data": {"factory_id": factory_id, "source": source},
        "result_data": result_data,
        "rule_count": obligation_count,
        "is_latest": True,
        "schema_version": SCHEMA_VERSION,
        "created_at": serialize_external_utc(now_kst()),
    }
    if created_by:                      # WO-CREATEDBY-FIX-001: 인증 사용자면 권한 컬럼만 채움
        row["created_by"] = created_by
    ins = supabase.table("factory_diagnosis_results").insert(row).execute()
    if not ins.data:
        raise HTTPException(status_code=500, detail="factory_diagnosis_results 저장 실패")
    return str(ins.data[0].get("id"))


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
def persist_obligations(factory_id: str, authorization: Optional[str] = Header(None)):
    """어댑터 obligations → factory_diagnosis_results 저장 (Track A 배선).

    이후 정제레이어 GET /diagnosis/transform/latest/{factory_id}로
    사용자 화면까지 도달.
    WO-CREATEDBY-FIX-001: 유효 토큰이면 created_by=users.id 저장(없으면 기존대로 null).
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
    sector = v4_result.get("facility_sector") or "INDUSTRIAL"
    diagnosis_id = _persist_result_data(
        factory_id, sector, result_data,
        adapter_result["obligation_count"], "V4_OBLIGATION_ADAPTER",
        created_by=_optional_user_id(authorization),
    )
    return {
        "status": "success",
        "factory_id": factory_id,
        "diagnosis_id": diagnosis_id,
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
def adapt_from_obligation_instances(
    factory_id: str,
    persist: bool = False,
    authorization: Optional[str] = Header(None),
):
    """obligation_instance(Applicability Engine) → 45CM obligations.

    Glue: obligation_instance → candidate → 기존 Adapter.
    persist=true 일 때 기존 운영 Persist(_persist_result_data)로
    factory_diagnosis_results 저장 → 이후 GET /diagnosis/transform/latest/{factory_id}로 가시화.
    Check Engine / 정제레이어 / 기존 Persist 로직 무수정.
    WO-CREATEDBY-FIX-001: 유효 토큰이면 created_by=users.id 저장(없으면 기존대로 null).
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

    diagnosis_id: Optional[str] = None
    if persist and adapter_result["obligation_count"] > 0:
        sector = _factory_sector(factory_id)
        result_data = build_result_data(adapter_result, {"facility_sector": sector})
        diagnosis_id = _persist_result_data(
            factory_id, sector, result_data,
            adapter_result["obligation_count"], "FROM_INSTANCES_OBLIGATION_INSTANCE",
            created_by=_optional_user_id(authorization),
        )

    total_ms = int((time.perf_counter() - t0) * 1000)

    return {
        "status": "ok",
        "factory_id": factory_id,
        "candidate_count": len(candidates),
        "obligation_count": adapter_result["obligation_count"],
        "verdict": adapter_result["verdict"],
        "obligations": adapter_result["obligations"],
        "source": adapter_result["source"],
        "persisted": diagnosis_id is not None,
        "diagnosis_id": diagnosis_id,
        "trace": {
            "fetch_rows_ms": fetch_ms,
            "adapter_ms": adapt_ms,
            "total_ms": total_ms,
        },
    }
