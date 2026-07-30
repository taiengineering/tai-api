"""routers/anonymous_diagnosis_leg.py — WO-PIPE-004: LEG 전용 standalone 진단 경로.

POST /anonymous-diagnosis-leg : UI 입력 -> LEG /rtm/evaluate -> 소비자 출력 저장 (TAI 미경유).
- LEG_PIPELINE_ENABLED 로 게이팅. 비활성 시 503.
- 실패 시 TAI fallback 없음(실패를 그대로 알린다).
- 기존 /anonymous-diagnosis(TAI)는 불변. 결과는 동일 테이블에 저장되어 GET /anonymous-diagnosis/{token}로 조회 가능.
"""
from __future__ import annotations

import os
import uuid
from datetime import timedelta
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from db.supabase_client import get_supabase
from services.diagnosis_helpers import _build_standard_output
from services.leg_diagnosis_svc import run_leg_diagnosis, LegDiagnosisError
from clients.leg_runtime_client import LegRuntimeError, is_enabled
from routers.anonymous_diagnosis import (
    AnonymousDiagnosisCreate,
    _build_step1_body,
    _now,
    TTL_DAYS,
)

router = APIRouter(prefix="/anonymous-diagnosis-leg", tags=["익명 무료진단 (LEG)"])

LEG_PIPELINE_ENABLED = os.getenv("LEG_PIPELINE_ENABLED", "").lower() in ("1", "true", "yes")
LEG_SOURCE_TYPE = "site_free_leg"


async def _create_anonymous_diagnosis_leg_impl(body: AnonymousDiagnosisCreate):
    if not LEG_PIPELINE_ENABLED:
        raise HTTPException(status_code=503, detail="LEG 파이프라인이 비활성화되어 있습니다 (LEG_PIPELINE_ENABLED).")
    if not is_enabled():
        raise HTTPException(status_code=503, detail="LEG_RUNTIME_URL이 설정되어 있지 않습니다.")

    supabase = get_supabase()
    step1_body = _build_step1_body(body)  # 잘못된 입력은 HTTPException(422)로 전파

    try:
        full_result = run_leg_diagnosis(step1_body)
    except (LegDiagnosisError, LegRuntimeError) as e:
        # TAI fallback 없음 — 실패를 그대로 알린다.
        raise HTTPException(status_code=502, detail="LEG 진단 실패: {}".format(e))

    partial = _build_standard_output(full_result)
    token = str(uuid.uuid4())
    expires = (_now() + timedelta(days=TTL_DAYS)).isoformat()
    created = _now().isoformat()
    obl_cnt = int(full_result.get("applicable_count") or 0)

    input_snapshot: Dict[str, Any] = {
        "site_kind": body.site_kind,
        "scale": body.scale,
        "workers": body.workers,
        "region": body.region,
        "sector": full_result.get("sector"),
    }
    row = {
        "public_token": token,
        "input_data": input_snapshot,
        "partial_result": partial,
        "full_result": full_result,
        "created_at": created,
        "expires_at": expires,
        "claimed_user_id": None,
        "status": "ACTIVE",
        "source_type": LEG_SOURCE_TYPE,
        "engine_version": full_result.get("engine_version") or "leg-runtime-v3",
        "rule_version": full_result.get("rule_source") or "leg-prod",
    }
    try:
        res = supabase.table("anonymous_diagnosis_results").insert(row).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="DB 저장 실패")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="DB 저장 실패: {}".format(e))

    return {
        "status": "success",
        "publicToken": token,
        "partialResult": partial,
        "hasFullResult": True,
        "expiresAt": expires,
        "engineFamily": "LEG",
        "legStatus": full_result.get("leg_status"),
        "obligationCount": obl_cnt,
    }


@router.post("")
async def create_anonymous_diagnosis_leg(body: AnonymousDiagnosisCreate):
    from services.canonical.flags import canonical_enabled
    if not canonical_enabled():
        return await _create_anonymous_diagnosis_leg_impl(body)
    from services.canonical.adapters import AnonymousAdapter
    from services.canonical.service import CanonicalDiagnosisService
    dto = AnonymousAdapter().to_canonical({
        "site_kind": body.site_kind, "scale": body.scale,
        "workers": body.workers, "region": body.region,
    })
    return await CanonicalDiagnosisService().evaluate(
        dto=dto, delegate=lambda: _create_anonymous_diagnosis_leg_impl(body)
    )
