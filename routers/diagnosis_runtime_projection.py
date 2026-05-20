"""
routers/diagnosis_runtime_projection.py — v1.0.0

Runtime Compiler Projection API

기존 diagnosis engine을 대체하여 Runtime Compiler 결과를
Projection 형태로 반환하는 API.

핵심 원칙:
- 진단 = "해야 하는 것" (Projection)
- Runtime = "실제로 하고 있는가" (Operation)
- 이 API는 Projection만 반환. Runtime state 반환 금지.

금지 필드:
- overdue, completed, uploaded, reviewer, escalation, runtime_instance
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

router = APIRouter(prefix="/projection", tags=["진단Projection"])


@router.get("/factory/{factory_id}")
def get_factory_projection(factory_id: str):
    """
    Runtime Compiler Projection for a factory.
    Returns obligation structure, NOT runtime state.
    """
    supabase = get_supabase()

    # 1. Factory info
    fac = supabase.table("factories").select("*").eq("id", factory_id).limit(1).execute()
    if not fac.data:
        raise HTTPException(status_code=404, detail="사업장을 찾을 수 없습니다.")
    f = fac.data[0]

    # 2. Applicability
    app_res = supabase.table("facility_applicability").select("id, applicability_status").eq("factory_id", factory_id).execute()
    app_data = app_res.data or []
    match_count = sum(1 for a in app_data if a.get("applicability_status") == "MATCH_CANDIDATE")

    # 3. Metadata Resolution (핵심: WHO/HOW/WHEN/SCHEDULE)
    meta_res = supabase.rpc("get_factory_metadata_projection", {"p_factory_id": factory_id}).execute()
    # Fallback: direct query if RPC not available
    if not meta_res.data:
        meta_res = supabase.table("runtime_metadata_resolution").select("*").execute()

    # 4. Assignment Requirements
    req_res = supabase.table("runtime_assignment_requirement").select("*").eq("runtime_task_id", factory_id).execute()

    # 5. Build Projection
    return {
        "status": "success",
        "projection_type": "runtime_compiler",
        "engine_version": "v3.0",
        "data": {
            "factory": {
                "name": f.get("name"),
                "sector": f.get("sector"),
                "employee_count": f.get("employee_count"),
                "contractor_count": f.get("contractor_count"),
            },
            "applicability": {
                "total": len(app_data),
                "match": match_count,
            },
            "obligations": meta_res.data or [],
            "assignment_requirements": req_res.data or [],
        }
    }


@router.get("/token/{public_token}")
def get_token_projection(public_token: str):
    """
    Runtime Compiler Projection by token.
    Reads from anonymous_diagnosis_results (same as paid-result)
    but ensures Runtime state is NOT included.

    이 API는 paid-diagnosis-result.html에서 호출.
    """
    supabase = get_supabase()

    res = (
        supabase.table("anonymous_diagnosis_results")
        .select("id, public_token, tier_code, full_result, input_data, status, engine_version")
        .eq("public_token", public_token)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="진단 결과를 찾을 수 없습니다.")

    rec = res.data[0]
    full_result = rec.get("full_result") or {}
    input_data = rec.get("input_data") or {}

    # Runtime state 필드 제거 (보호)
    BANNED_FIELDS = {
        "runtime_instance", "overdue", "completed", "uploaded",
        "reviewer", "escalation", "runtime_health", "actual_state"
    }
    clean_result = {k: v for k, v in full_result.items() if k not in BANNED_FIELDS}

    return {
        "status": "success",
        "projection_type": "runtime_compiler",
        "engine_version": rec.get("engine_version") or "v3.0",
        "boundary": "diagnosis_projection",
        "data": {
            "public_token": public_token,
            "tier_code": rec.get("tier_code"),
            "company_name": input_data.get("company_name") or clean_result.get("company_name"),
            "sector": input_data.get("sector") or clean_result.get("sector"),
            "risk_level": clean_result.get("risk_level", "MEDIUM"),
            "summary": clean_result.get("summary", {}),
            "rules_table": clean_result.get("rules_table", []),
            "law_badges": clean_result.get("law_badges", []),
            "law_groups": clean_result.get("law_groups", []),
            "key_obligations": clean_result.get("key_obligations", []),
            "input_data": input_data,
        }
    }
