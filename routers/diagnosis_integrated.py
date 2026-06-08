"""Integrated diagnosis router."""
from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from db.supabase_client import get_supabase
from schemas.diagnosis_integrated import DiagnosisRunBody, DisclaimerBody, UpgradeBody
from schemas.legal_engine import DiagnoseStep1Body
from services.diagnosis_helpers import _auto_tier, _build_partial, _now, _sha256
from services import diagnosis_integrated_svc
from services.diagnosis_nexas_adapter import (
    build_nexas_run_response,
    nexas_run_body_from_request,
)
from services.anonymous_factory_service import ANONYMOUS_COMPILER_ENGINE_VERSION
from services.diagnosis_integrated_svc import run_step1_via_compiler
from services.diagnosis_runtime_step1 import convert_rules_table_to_matched_rules
from services.legal_adapter import project_rules

log = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnosis", tags=["진단통합"])

VERSION = "1.0.2"
ENGINE_VERSION = ANONYMOUS_COMPILER_ENGINE_VERSION
_ALLOWED_DIAGNOSE_SECTORS = frozenset({"BUILDING", "MANUFACTURING", "CONSTRUCTION", "SPECIAL_FACILITY", "SPECIAL"})

# 이니시스 환경변수
INICIS_MID      = os.getenv("INICIS_VERIFY_MID", "")
INICIS_SITE_CD  = os.getenv("INICIS_VERIFY_SITE_CD", "")
INICIS_SITE_KEY = os.getenv("INICIS_VERIFY_SITE_KEY", "")
INICIS_RETURN_URL = os.getenv(
    "INICIS_VERIFY_RETURN_URL",
    "https://api.taieng.co.kr/diagnosis/auth/callback"
)

# FIX-2: 면책 확정 문구 (TASK 6) — 확정 문구로 교체
DISCLAIMER_TEXT = (
    "본 진단 결과는 현행 법령과 사업장 정보를 정밀 분석하여 "
    "적용 가능한 법적 의무를 도출한 것입니다. "
    "본 서비스는 법률 상담·자문·의견 제공이 아니며, "
    "개별 사안에 대한 법적 판단이나 해석을 포함하지 않습니다. "
    "실제 행정 처분·감독 기준은 관할 기관의 판단에 따라 "
    "달라질 수 있으므로, 구체적 법률 적용이 필요한 경우 "
    "관할 행정기관 또는 법률 전문가에게 확인하시기 바랍니다."
)

# 다음 TIER구도 동일 페이지 접수용 가격 테이블
PAID_TIER_PRICES: Dict[str, int] = {
    "BUILDING_V2":         99000,
    "BUILDING_LARGE_V2":  249000,
    "INDUSTRY_V2":         79000,
    "INDUSTRY_STANDARD":  149000,
    "INDUSTRY_PREMIUM":   249000,
    "CONSTRUCTION":       145000,
    "CONSTRUCTION_PREMIUM": 299000,
}

FREE_TIER_CODES = frozenset({
    "BUILDING_FREE", "INDUSTRY_FREE", "CONSTRUCTION_FREE"
})


def _run_step1_via_service(supabase, step1_body: DiagnoseStep1Body) -> Dict[str, Any]:
    try:
        return run_step1_via_compiler(supabase, step1_body, _ALLOWED_DIAGNOSE_SECTORS)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _resolve_auth_log(supabase, auth_token: str) -> dict:
    return diagnosis_integrated_svc.resolve_auth_log(supabase, auth_token)


@router.post("/auth/prepare")
def prepare_diagnosis_auth():
    if not INICIS_MID:
        raise HTTPException(
            status_code=503,
            detail="본인인증 서비스 준비 중입니다. 잠시 후 이용해 주세요."
        )
    ts  = str(int(time.time() * 1000))
    sig = _sha256(INICIS_SITE_KEY + ts + INICIS_MID) if INICIS_SITE_KEY else ""
    return {
        "status": "success",
        "data": {
            "mid":        INICIS_MID,
            "site_cd":    INICIS_SITE_CD,
            "timestamp":  ts,
            "signature":  sig,
            "return_url": INICIS_RETURN_URL,
            "popup_title": "사업장 정보 보호를 위한 본인 확인",
        },
    }


@router.post("/auth/callback")
async def diagnosis_auth_callback(request: Request):
    try:
        form = await request.form()
        data: Dict[str, Any] = dict(form)
    except Exception:
        try:
            data = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="요청 파싱 실패")

    log.info("[DIAG AUTH] callback keys: %s", list(data.keys()))

    result_code = str(data.get("resultCode") or data.get("result_code") or "")
    result_msg  = str(data.get("resultMsg")  or data.get("result_msg")  or "인증 실패")

    # 실패 코드
    _FAIL_HTML = (
        "<script>"
        "window.opener?.postMessage({{type:'DIAG_AUTH',success:false,"
        "message:'{msg}'}}, '*');"
        "window.close();</script>"
    )
    _OK_HTML = (
        "<script>"
        "window.opener?.postMessage({{type:'DIAG_AUTH',success:true,"
        "authToken:'{tok}',name:'{name}',freeRemaining:{rem}}}, '*');"
        "window.close();</script>"
    )

    if result_code != "0000":
        return HTMLResponse(_FAIL_HTML.format(msg=result_msg))

    # CI 추출 (이니시스 필드명 다양해 다중 키 시도)
    ci      = str(data.get("ci") or data.get("CI") or "")
    name    = str(data.get("name") or data.get("userName") or "")
    phone   = str(data.get("phoneNo") or data.get("userPhone") or "")
    birth   = str(data.get("birthDate") or data.get("userBirthday") or "")
    gender  = str(data.get("gender") or data.get("userGender") or "")

    if not ci:
        return HTMLResponse(_FAIL_HTML.format(msg="CI를 받지 못했습니다."))

    ci_hash = _sha256(ci)
    supabase = get_supabase()
    now      = _now()

    # diagnosis_auth_log upsert (ci_hash UNIQUE 기준)
    # 이미 있으면 업데이트, 없으면 생성
    existing = (
        supabase.table("diagnosis_auth_log")
        .select("id, auth_token, free_count, free_limit")
        .eq("ci_hash", ci_hash)
        .limit(1)
        .execute()
    )

    if existing.data:
        row = existing.data[0]
        # 이미 등록된 CI — name/phone/verified_at 업데이트, auth_token 재생성
        new_token = str(uuid.uuid4())
        supabase.table("diagnosis_auth_log").update({
            "name":        name,
            "phone":       phone,
            "verified_at": now,
            "updated_at":  now,
            "auth_token":  new_token,
            "status":      "ACTIVE",
        }).eq("id", row["id"]).execute()
        free_remaining = max(0, (row.get("free_limit") or 3) - (row.get("free_count") or 0))
        auth_token = new_token
    else:
        # 신규 CI — INSERT (FIX-5: CI 평문 저장 안 함, ci_hash만 사용)
        ins = supabase.table("diagnosis_auth_log").insert({
            "ci":          "",           # CI 평문 저장 안 함
            "ci_hash":     ci_hash,
            "name":        name,
            "phone":       phone,
            "verified_at": now,
            "free_count":  0,
            "free_limit":  3,
            "status":      "ACTIVE",
            "created_at":  now,
            "updated_at":  now,
        }).execute()
        if not ins.data:
            return HTMLResponse(_FAIL_HTML.format(msg="내부 오류가 발생했습니다."))
        auth_token     = str(ins.data[0].get("auth_token") or "")
        free_remaining = 3

    return HTMLResponse(_OK_HTML.format(
        tok=auth_token,
        name=name.replace("'", ""),
        rem=free_remaining,
    ))


@router.get("/auth/check")
def check_diagnosis_free_usage(
    auth_token: str = Query(..., description="본인인증 콜백에서 받은 auth_token"),
):
    supabase = get_supabase()
    return diagnosis_integrated_svc.check_free_usage(supabase, auth_token)


@router.get("/price-tier")
def get_price_tier(
    sector:              str   = Query(..., description="BUILDING | INDUSTRIAL | CONSTRUCTION | SPECIAL_FACILITY"),
    floor_area:          float = Query(0.0, description="바닥면적 (㎡) — BUILDING 자동판정용"),
    contract_amount_eok: float = Query(0.0, description="공사금액(억원) — CONSTRUCTION 자동판정용"),
    user_tier:           Optional[str] = Query(None, description="산업(INDUSTRIAL) 사용자 선택 티어"),
):
    return diagnosis_integrated_svc.get_price_tier_payload(
        sector=sector,
        floor_area=floor_area,
        contract_amount_eok=contract_amount_eok,
        user_tier=user_tier,
        auto_tier_func=_auto_tier,
        paid_tier_prices=PAID_TIER_PRICES,
        free_tier_codes=FREE_TIER_CODES,
    )


@router.post("/disclaimer")
def save_disclaimer(body: DisclaimerBody, request: Request):
    supabase = get_supabase()
    return diagnosis_integrated_svc.save_disclaimer(
        supabase=supabase,
        auth_token=body.auth_token,
        agreed=body.agreed,
        ip_address=body.ip_address,
        user_agent=body.user_agent,
        request=request,
        disclaimer_text=DISCLAIMER_TEXT,
    )


@router.post("/run")
async def run_diagnosis(body: DiagnosisRunBody):
    supabase = get_supabase()
    run_body = nexas_run_body_from_request(body.model_dump())
    result = diagnosis_integrated_svc.run_diagnosis(
        supabase=supabase,
        body=run_body,
        run_step1_func=_run_step1_via_service,
        auto_tier_func=_auto_tier,
        build_partial_func=_build_partial,
        now_func=_now,
        paid_tier_prices=PAID_TIER_PRICES,
        free_tier_codes=FREE_TIER_CODES,
        engine_version=ENGINE_VERSION,
    )

    factory_id = (body.factory_id or "").strip() or None
    company_id = (body.company_id or "").strip() or None
    if factory_id and not company_id:
        try:
            fac = (
                supabase.table("factories")
                .select("company_id")
                .eq("id", factory_id)
                .limit(1)
                .execute()
            )
            if fac.data:
                company_id = str(fac.data[0].get("company_id") or "").strip() or None
        except Exception as e:
            log.warning("Binding Engine company_id lookup failed (non-blocking): %s", e)

    if factory_id and company_id:
        try:
            full_result = result.get("result") or {}
            rules_for_binding = convert_rules_table_to_matched_rules(
                full_result.get("rules_table") or []
            )
            if rules_for_binding:
                diagnosis_id = result.get("diagnosis_id") or result.get("public_token") or "unknown"
                binding_result = await project_rules(
                    tenant_id=str(company_id),
                    facility_id=str(factory_id),
                    matched_rules=rules_for_binding,
                    trace_id=f"diagnosis-{diagnosis_id}",
                )
                log.info("Binding Engine: %s", binding_result.get("stats"))
        except Exception as e:
            log.warning("Binding Engine 호출 실패 (non-blocking): %s", e)

    return build_nexas_run_response(result)


@router.post("/upgrade")
async def upgrade_diagnosis(body: UpgradeBody):
    supabase = get_supabase()
    return diagnosis_integrated_svc.upgrade_diagnosis(
        supabase=supabase,
        body=body,
        run_step1_func=_run_step1_via_service,
        build_partial_func=_build_partial,
        paid_tier_prices=PAID_TIER_PRICES,
    )
