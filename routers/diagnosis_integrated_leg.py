"""routers/diagnosis_integrated_leg.py — WO-PIPE-004(유료): LEG 전용 유료 진단 실행 경로.

POST /diagnosis/run-leg : 인증·티어·과금·저장 오케스트레이션(diagnosis_integrated_svc.run_diagnosis)을
그대로 재사용하고, 엔진(run_step1_func)만 LEG(/rtm/evaluate)로 교체한다.
- LEG_PIPELINE_ENABLED 게이팅. 비활성 시 503.
- TAI Compiler Core 미경유. LEG 실패 시 TAI fallback 없음(502).
- 기존 POST /diagnosis/run(TAI)은 불변.
결과는 run_diagnosis가 anonymous_diagnosis_results에 저장(engine_version=leg-runtime-v3로 식별).
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from db.supabase_client import get_supabase
from routers.auth import get_current_user_optional
from schemas.diagnosis_integrated import DiagnosisRunBody
from services import diagnosis_integrated_svc
from services.diagnosis_helpers import _auto_tier, _build_partial, _now
from services.leg_diagnosis_svc import run_leg_diagnosis, LegDiagnosisError
from services.canonical.industrial_www import build_industrial_www_step1
from clients.leg_runtime_client import LegRuntimeError, is_enabled
# 유료 티어 가격/무료 코드는 TAI 유료 라우터의 정의를 재사용(단일 출처)
from routers.diagnosis_integrated import PAID_TIER_PRICES, FREE_TIER_CODES

router = APIRouter(prefix="/diagnosis", tags=["진단통합 (LEG)"])

LEG_PIPELINE_ENABLED = os.getenv("LEG_PIPELINE_ENABLED", "").lower() in ("1", "true", "yes")
LEG_ENGINE_VERSION = "leg-runtime-v3"


def _run_step1_via_leg(supabase, step1_body) -> Dict[str, Any]:
    """엔진 주입점(LEG판). run_step1_func 시그니처 호환. supabase 미사용(LEG는 rtm 호출)."""
    try:
        full = run_leg_diagnosis(step1_body)
    except (LegDiagnosisError, LegRuntimeError) as e:
        # TAI fallback 없음 — 실패를 그대로 알린다.
        raise HTTPException(status_code=502, detail="LEG 진단 실패: {}".format(e))
    return {"status": "success", "data": full}


async def _run_leg_impl(body: DiagnosisRunBody, current_user: Optional[dict] = None):
    if not LEG_PIPELINE_ENABLED:
        raise HTTPException(status_code=503, detail="LEG 파이프라인이 비활성화되어 있습니다 (LEG_PIPELINE_ENABLED).")
    if not is_enabled():
        raise HTTPException(status_code=503, detail="LEG_RUNTIME_URL이 설정되어 있지 않습니다.")

    supabase = get_supabase()
    # WO-FE-CST-GAP-IMPL-001 E-C: Nexas 격리. official paid input envelope = DiagnosisRunBody.form_data.
    # run_diagnosis 가 _available.update(form_data) → canonical_applicability → DiagnoseStep1Body.input 으로
    # lossless materialize 하므로 nexas adapter 를 경유하지 않고 body 를 그대로 전달한다.
    run_body = body

    # 오케스트레이션(인증·티어·과금·무료횟수·저장) 전부 재사용, 엔진만 LEG.
    result = diagnosis_integrated_svc.run_diagnosis(
        supabase=supabase,
        body=run_body,
        run_step1_func=_run_step1_via_leg,
        auto_tier_func=_auto_tier,
        build_partial_func=_build_partial,
        now_func=_now,
        paid_tier_prices=PAID_TIER_PRICES,
        free_tier_codes=FREE_TIER_CODES,
        engine_version=LEG_ENGINE_VERSION,
        current_user=current_user,
        canonical_step1_factory_func=build_industrial_www_step1,
    )

    full = result.get("result") or {}
    return {
        "status": "success",
        "publicToken": result.get("public_token"),
        "diagnosisId": result.get("diagnosis_id"),
        "tierCode": result.get("tier_code"),
        "isFree": result.get("is_free"),
        "expiresAt": result.get("expires_at"),
        "freeRemainingAfter": result.get("free_remaining_after"),
        "engineFamily": "LEG",
        "legStatus": full.get("leg_status"),
        "obligationCount": full.get("applicable_count"),
        "partialResult": _build_partial(full),
    }


@router.post("/run-leg")
async def run_diagnosis_leg(
    body: DiagnosisRunBody,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    from services.canonical.flags import canonical_enabled
    if not canonical_enabled():
        return await _run_leg_impl(body, current_user)
    from services.canonical.adapters import MemberAdapter
    from services.canonical.service import CanonicalDiagnosisService
    dto = MemberAdapter().to_canonical(body.model_dump())
    return await CanonicalDiagnosisService().evaluate(
        dto=dto, delegate=lambda: _run_leg_impl(body, current_user)
    )
