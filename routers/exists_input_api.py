"""EXISTS MVP 입력 API (CURSOR-TASK-002).

  GET  /diagnosis/mvp-exists-fields?sector=
  POST /diagnosis/exists-input/{factory_id}
  GET  /diagnosis/exists-input/{factory_id}/contract
  GET  /diagnosis/exists-input/{factory_id}/trace
"""
from __future__ import annotations

import time
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from constants.sectors import VALID_SECTORS
from db.supabase_client import get_supabase
from services.exists_input_service import (
    fetch_mvp_field_definitions,
    normalize_exists_payload,
    save_exists_inputs,
)
from services.input_contract_builder import (
    build_input_contract_for_factory,
    contract_has_stats,
)
from services.obligation_adapter_service import build_obligations_from_trigger_candidates
from services.obligation_instance_adapter import obligation_instances_to_trigger_candidates
from services.legal_rules import normalize_sector_db

router = APIRouter(prefix="/diagnosis", tags=["EXISTS 입력 (MVP)"])


class ExistsInputBody(BaseModel):
    """has_* field_code 그대로 전달 (TASK-002)."""

    inputs: Dict[str, bool] = Field(
        default_factory=dict,
        description="예: {\"has_welding\": true, \"has_crane\": true}",
    )


@router.get("/mvp-exists-fields")
def get_mvp_exists_fields(
    sector: str = Query(..., description="INDUSTRIAL | CONSTRUCTION | BUILDING"),
):
    """TASK-001: sector별 MVP boolean 질문 세트."""
    sector = normalize_sector_db(sector)
    if sector not in VALID_SECTORS:
        raise HTTPException(
            status_code=400,
            detail=f"sector는 {sorted(VALID_SECTORS)} 중 하나여야 합니다",
        )
    if sector not in ("INDUSTRIAL", "CONSTRUCTION", "BUILDING"):
        raise HTTPException(
            status_code=400,
            detail="MVP EXISTS 필드는 INDUSTRIAL | CONSTRUCTION | BUILDING 만 지원합니다",
        )

    sb = get_supabase()
    fields = fetch_mvp_field_definitions(sector, sb)
    return {
        "success": True,
        "data": {
            "sector": sector,
            "field_count": len(fields),
            "fields": fields,
        },
    }


@router.post("/exists-input/{factory_id}")
def post_exists_input(factory_id: str, body: ExistsInputBody):
    """has_* 저장 + facility_profiles.exists_inputs 동기화."""
    t0 = time.perf_counter()
    sb = get_supabase()
    normalized = normalize_exists_payload(body.inputs)
    if not normalized:
        raise HTTPException(status_code=400, detail="저장할 has_* 입력이 없습니다")

    try:
        result = save_exists_inputs(factory_id, normalized, sb)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    contract = build_input_contract_for_factory(factory_id, sb)
    stats = contract_has_stats(contract)
    save_ms = int((time.perf_counter() - t0) * 1000)

    return {
        "success": True,
        "factory_id": factory_id,
        "saved_inputs": normalized,
        "exists_inputs": result["exists_inputs"],
        "profile_id": result["profile_id"],
        "profile_version": result["profile_version"],
        "factory_columns_updated": result["factory_columns_updated"],
        "contract_has_true_count": stats["has_true_count"],
        "trace": {"save_ms": save_ms},
    }


@router.get("/exists-input/{factory_id}/contract")
def get_exists_input_contract(factory_id: str):
    """Input Contract Builder 출력 (Applicability Engine 입력 형태)."""
    sb = get_supabase()
    try:
        contract = build_input_contract_for_factory(factory_id, sb)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    stats = contract_has_stats(contract)
    return {
        "success": True,
        "contract": contract,
        "stats": stats,
    }


def _count_obligation_instances(factory_id: str, supabase) -> Dict[str, Any]:
    res = (
        supabase.table("obligation_instance")
        .select("trigger_type, trigger_l2")
        .eq("factory_id", factory_id)
        .eq("status", "ACTIVE")
        .execute()
    )
    rows = res.data or []
    from collections import Counter

    families = Counter(f"{r.get('trigger_type')}:{r.get('trigger_l2')}" for r in rows)
    exists_count = sum(
        1 for r in rows
        if (r.get("trigger_type") or "").upper() == "EXISTS"
        or (r.get("trigger_l2") or "").upper() == "EXISTS"
    )
    exists_by_type = sum(
        1 for r in rows if (r.get("trigger_type") or "").upper() == "EXISTS"
    )
    exists_by_l2 = sum(
        1 for r in rows if (r.get("trigger_l2") or "").upper() == "EXISTS"
    )
    exists_count = max(exists_count, exists_by_type, exists_by_l2)

    universal = sum(
        1 for r in rows
        if (r.get("trigger_l2") or "").upper() == "UNIVERSAL"
    )
    threshold = sum(
        1 for r in rows
        if (r.get("trigger_type") or "").upper() == "THRESHOLD"
    )
    return {
        "total": len(rows),
        "exists": exists_count,
        "universal": universal,
        "threshold": threshold,
        "families_top": families.most_common(12),
    }


@router.get("/exists-input/{factory_id}/trace")
def get_exists_input_trace(factory_id: str):
    """TASK-006: 입력 → Builder → obligation_instance → Glue → Adapter 전 구간 trace."""
    t0 = time.perf_counter()
    sb = get_supabase()

    t_contract = time.perf_counter()
    try:
        contract = build_input_contract_for_factory(factory_id, sb)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    contract_ms = int((time.perf_counter() - t_contract) * 1000)
    contract_stats = contract_has_stats(contract)

    t_oi = time.perf_counter()
    oi_stats = _count_obligation_instances(factory_id, sb)
    oi_ms = int((time.perf_counter() - t_oi) * 1000)

    t_glue = time.perf_counter()
    candidates = obligation_instances_to_trigger_candidates(factory_id, sb)
    glue_ms = int((time.perf_counter() - t_glue) * 1000)

    t_adapt = time.perf_counter()
    adapter_result = build_obligations_from_trigger_candidates(
        candidates, factory_id, trigger_codes=[]
    )
    adapt_ms = int((time.perf_counter() - t_adapt) * 1000)
    total_ms = int((time.perf_counter() - t0) * 1000)

    input_true = contract_stats["has_true_fields"]
    contract_true = contract_stats["has_true_fields"]
    input_contract_match = input_true == contract_true

    return {
        "success": True,
        "factory_id": factory_id,
        "trace": {
            "input": {
                "has_true_count": len(input_true),
                "has_true_fields": input_true,
            },
            "builder": {
                "has_true_count": contract_stats["has_true_count"],
                "has_true_fields": contract_true,
                "contract": contract,
                "input_contract_match": input_contract_match,
                "ms": contract_ms,
            },
            "obligation_instance": {
                **oi_stats,
                "ms": oi_ms,
            },
            "glue": {
                "candidate_count": len(candidates),
                "ms": glue_ms,
            },
            "adapter": {
                "obligation_count": adapter_result["obligation_count"],
                "verdict": adapter_result["verdict"],
                "ms": adapt_ms,
            },
            "total_ms": total_ms,
        },
    }
