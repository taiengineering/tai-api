"""
routers/diagnosis_integrated.py — v1.0.1

BE-10: 법령진단 통합 백엔드
  TASK 1: POST /diagnosis/auth/prepare   이니시스 팝업 파라미터 생성
  TASK 1: POST /diagnosis/auth/callback  이니시스 콜백 → CI 저장 → auth_token 반환
  TASK 2: GET  /diagnosis/auth/check     무료 횟수 확인
  TASK 3: POST /diagnosis/run            통합 진단 실행 (무료/유료 동일 API)
  TASK 4: GET  /diagnosis/price-tier     가격 자동 판정
  TASK 5: POST /diagnosis/upgrade        업그레이드 차액 결제
  TASK 6: POST /diagnosis/disclaimer     면책 동의 저장

v1.0.1 수정:
  FIX-1: "면접" → "면책" 오타 전체 수정
  FIX-2: DISCLAIMER_TEXT 확정 문구 교체
  FIX-3: 가격 판정 설명 오타 4곳 수정
  FIX-4: callback docstring 인코딩 정상화
  FIX-5: CI 평문 저장 제거 (ci_hash만 사용)

주요 설계 원칙:
  - CI 노출 금지: auth_token(UUID)로 세션 관리, CI는 내부 해시만 사용
  - 무료: CI당 총 3회, 리셋 없음
  - 마케팅사이트(taieng.co.kr) 비로그인 사용자 대상
  - 진단 결과: anonymous_diagnosis_results 저장
  - 이니시스 API 키 미수령 시 INICIS_VERIFY_MID 환경변수 비어 있으면 503

환경변수 (Fly.io Secrets):
  INICIS_VERIFY_MID       이니시스 통합인증 MID
  INICIS_VERIFY_SITE_CD   사이트 코드
  INICIS_VERIFY_SITE_KEY  사이트 키 (서명 생성용)
  INICIS_VERIFY_RETURN_URL  콜백 URL
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnosis", tags=["진단통합"])

VERSION = "1.0.1"

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


# ───────────────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ───────────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _resolve_auth_log(supabase, auth_token: str) -> dict:
    """
    auth_token으로 diagnosis_auth_log 조회.
    없으면 401 발생.
    """
    res = (
        supabase.table("diagnosis_auth_log")
        .select("id, ci_hash, name, phone, free_count, free_limit, status")
        .eq("auth_token", auth_token)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=401, detail="인증 세션이 유효하지 않습니다. 본인인증을 다시 시도해 주세요.")
    row = res.data[0]
    if row.get("status") != "ACTIVE":
        raise HTTPException(status_code=403, detail="사용할 수 없는 인증 세션입니다.")
    return row


def _auto_tier(sector: str,
               floor_area: float = 0.0,
               contract_amount_eok: float = 0.0,
               user_tier: Optional[str] = None) -> str:
    """
    TASK 4: 가격 자동 판정.
      BUILDING     : 5,000㎡ 기준
      CONSTRUCTION : 공사금액 50억 기준
      INDUSTRY     : 사용자 선택 (user_tier)
    """
    if sector == "BUILDING":
        return "BUILDING_LARGE_V2" if (floor_area or 0) >= 5000 else "BUILDING_V2"
    if sector == "CONSTRUCTION":
        return "CONSTRUCTION_PREMIUM" if (contract_amount_eok or 0) >= 50 else "CONSTRUCTION"
    # INDUSTRY: 사용자 선택
    return user_tier or "INDUSTRY_V2"


# ───────────────────────────────────────────────────────────────────────────
# TASK 1-A: POST /diagnosis/auth/prepare — 이니시스 팝업 파라미터
# ───────────────────────────────────────────────────────────────────────────

@router.post("/auth/prepare")
def prepare_diagnosis_auth():
    """
    TASK 1: 이니시스 통합인증 팝업 파라미터 생성.
    FE가 이 데이터로 이니시스 JS SDK를 호출하면 팝업 실행.
    """
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


# ───────────────────────────────────────────────────────────────────────────
# TASK 1-B: POST /diagnosis/auth/callback — 이니시스 콜백 처리
# ───────────────────────────────────────────────────────────────────────────

@router.post("/auth/callback")
async def diagnosis_auth_callback(request: Request):
    """
    TASK 1: 이니시스 통합인증 콜백.
    CI 추출 → diagnosis_auth_log upsert → auth_token을 HTML postMessage로 전달 후 팝업 닫기.

    FE는 window.addEventListener('message') 로 auth_token을 받음.
    """
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


# ───────────────────────────────────────────────────────────────────────────
# TASK 2: GET /diagnosis/auth/check — 무료 횟수 확인
# ───────────────────────────────────────────────────────────────────────────

@router.get("/auth/check")
def check_diagnosis_free_usage(
    auth_token: str = Query(..., description="본인인증 콜백에서 받은 auth_token"),
):
    """
    TASK 2: 무료 횟수 확인.
    CI당 총 3회, 리셋 없음.
    """
    supabase = get_supabase()
    row = _resolve_auth_log(supabase, auth_token)
    used      = row.get("free_count")  or 0
    limit_cnt = row.get("free_limit") or 3
    remaining = max(0, limit_cnt - used)
    return {
        "status":       "success",
        "can_free":     remaining > 0,
        "free_used":    used,
        "free_limit":   limit_cnt,
        "free_remaining": remaining,
        "name":         row.get("name"),
    }


# ───────────────────────────────────────────────────────────────────────────
# TASK 4: GET /diagnosis/price-tier — 가격 자동 판정
# ───────────────────────────────────────────────────────────────────────────

@router.get("/price-tier")
def get_price_tier(
    sector:              str   = Query(..., description="BUILDING | INDUSTRY | CONSTRUCTION"),
    floor_area:          float = Query(0.0, description="바닥면적 (㎡) — BUILDING 자동판정용"),
    contract_amount_eok: float = Query(0.0, description="공사금액(억원) — CONSTRUCTION 자동판정용"),
    user_tier:           Optional[str] = Query(None, description="INDUSTRY 사용자 선택 티어"),
):
    """
    TASK 4: 진단 가격 자동 판정.
      BUILDING     : 5,000㎡ 기준 (BUILDING_V2 99K / BUILDING_LARGE_V2 249K)
      CONSTRUCTION : 50억 기준 (CONSTRUCTION 145K / CONSTRUCTION_PREMIUM 299K)
      INDUSTRY     : 사용자 선택 (79K / 149K / 249K)
    """
    sector = sector.strip().upper()
    tier_code = _auto_tier(sector, floor_area, contract_amount_eok, user_tier)

    price     = PAID_TIER_PRICES.get(tier_code, 0)
    is_free   = tier_code in FREE_TIER_CODES
    auto_det  = sector in ("BUILDING", "CONSTRUCTION")

    # FIX-3: 가격 판정 설명 오타 4곳 수정
    determination_note = ""
    if sector == "BUILDING":
        if floor_area >= 5000:
            determination_note = f"입력 면적 {floor_area:,.0f}㎡ ≥ 5,000㎡ → 대형건물로 자동 판정"
        else:
            determination_note = f"입력 면적 {floor_area:,.0f}㎡ < 5,000㎡ → 소형건물로 자동 판정"
    elif sector == "CONSTRUCTION":
        if contract_amount_eok >= 50:
            determination_note = f"공사금액 {contract_amount_eok}억 ≥ 50억 → 종합으로 자동 판정"
        else:
            determination_note = f"공사금액 {contract_amount_eok}억 < 50억 → 기본으로 자동 판정"
    else:
        determination_note = "산업 섹터는 사용자가 직접 등급을 선택합니다"

    return {
        "status":             "success",
        "sector":             sector,
        "tier_code":          tier_code,
        "price_krw":          price,
        "is_free":            is_free,
        "auto_determined":    auto_det,
        "determination_note": determination_note,
    }


# ───────────────────────────────────────────────────────────────────────────
# TASK 6: POST /diagnosis/disclaimer — 면책 동의 저장
# ───────────────────────────────────────────────────────────────────────────

class DisclaimerBody(BaseModel):
    auth_token: str  = Field(..., description="본인인증 auth_token")
    agreed:     bool = Field(..., description="true이어야 진단 실행 가능")
    ip_address: Optional[str] = Field(None, description="FE에서 수집한 제출자 IP")
    user_agent: Optional[str] = Field(None, description="User-Agent")


@router.post("/disclaimer")
def save_disclaimer(body: DisclaimerBody, request: Request):
    """
    TASK 6: 진단 실행 직전 면책 동의 저장.
    agreed=true여야만 disclaimer_log_id를 반환.
    클라이언트는 이 id를 POST /diagnosis/run에 제출해야 진단 실행 가능.
    """
    if not body.agreed:
        raise HTTPException(
            status_code=400,
            detail="면책 동의를 체크해 주세요."  # FIX-1
        )
    supabase = get_supabase()
    auth_row = _resolve_auth_log(supabase, body.auth_token)

    # 실제 IP: FE 전달 또는 request에서 추출
    ip = body.ip_address or (request.client.host if request.client else None)
    ua = body.user_agent or request.headers.get("user-agent", "")

    res = supabase.table("diagnosis_disclaimer_log").insert({
        "ci_hash":        auth_row["ci_hash"],
        "auth_log_id":    auth_row["id"],
        "disclaimer_text": DISCLAIMER_TEXT,
        "agreed":         True,
        "ip_address":     ip,
        "user_agent":     ua[:500] if ua else None,
    }).execute()

    if not res.data:
        raise HTTPException(status_code=500, detail="동의 저장에 실패했습니다.")

    return {
        "status":           "success",
        "disclaimer_log_id": res.data[0]["id"],
        "agreed_at":        res.data[0].get("agreed_at"),
        "disclaimer_text":  DISCLAIMER_TEXT,
    }


# ───────────────────────────────────────────────────────────────────────────
# TASK 3: POST /diagnosis/run — 통합 진단 실행
# ───────────────────────────────────────────────────────────────────────────

class DiagnosisRunBody(BaseModel):
    auth_token:       str   = Field(..., description="본인인증 auth_token")
    disclaimer_log_id: str  = Field(..., description="면책 동의 ID (POST /diagnosis/disclaimer 반환값)")  # FIX-1
    sector:           str   = Field(..., description="BUILDING | INDUSTRY | CONSTRUCTION")
    # 가격 자동판정용
    floor_area:          Optional[float] = Field(None, description="바닥면적(㎡) — BUILDING")
    total_floor_area:    Optional[float] = Field(None, description="연면적(㎡)")
    contract_amount_eok: Optional[float] = Field(None, description="공사금액(억원) — CONSTRUCTION")
    user_tier:           Optional[str]   = Field(None, description="INDUSTRY 사용자 선택 티어")
    # 엔진 입력 필드
    direct_workers:    Optional[int]   = None
    subcon_workers:    Optional[int]   = None
    worker_count:      Optional[int]   = None
    employee_count:    Optional[int]   = None
    ksic_major:        Optional[str]   = None
    building_use_type: Optional[str]   = None
    construction_type: Optional[str]   = Field(None, description="음/토/건축/기능 등")
    region:            Optional[str]   = None
    # 유료 결제 정보
    payment_ref:       Optional[str]   = Field(None, description="유료 결제 참조 번호 (무료이면 생략)")


@router.post("/run")
async def run_diagnosis(body: DiagnosisRunBody):
    """
    TASK 3: 통합 진단 실행 — 무료/유료 동일 API.

    흐름:
      1. auth_token 검증
      2. 면책 동의 검증
      3. 섹터 정규화 + tier 자동 판정 (TASK 4 로직 재사용)
      4. 무료: 횟수 제한 확인
      5. 유료: payment_ref 존재 확인 (추후 KG이니시스 결제 실시간 검증로 교체)
      6. 엔진 실행 (legal_engine.diagnose_step1)
      7. anonymous_diagnosis_results 저장
      8. 무료면 free_count+1
    """
    from routers.legal_engine import DiagnoseStep1Body, diagnose_step1
    from routers.legal_engine import ENGINE_VERSION

    supabase = get_supabase()

    # 1. 인증 세션 검증
    auth_row = _resolve_auth_log(supabase, body.auth_token)

    # 2. 면책 동의 검증 (FIX-1)
    disc_res = (
        supabase.table("diagnosis_disclaimer_log")
        .select("id, ci_hash, agreed")
        .eq("id", body.disclaimer_log_id)
        .eq("ci_hash", auth_row["ci_hash"])
        .limit(1)
        .execute()
    )
    if not disc_res.data or not disc_res.data[0].get("agreed"):
        raise HTTPException(status_code=400, detail="면책 동의가 필요합니다.")  # FIX-1

    # 3. 섹터 + tier 판정
    sector = body.sector.strip().upper()
    # INDUSTRY 내부에서는 MANUFACTURING 사용
    engine_sector = "MANUFACTURING" if sector == "INDUSTRY" else sector
    tier_code = _auto_tier(
        sector,
        floor_area=body.floor_area or 0.0,
        contract_amount_eok=body.contract_amount_eok or 0.0,
        user_tier=body.user_tier,
    )
    is_free = tier_code in FREE_TIER_CODES

    # 4. 무료 횟수 제한
    if is_free:
        used  = auth_row.get("free_count") or 0
        limit_cnt = auth_row.get("free_limit") or 3
        if used >= limit_cnt:
            raise HTTPException(
                status_code=402,
                detail=f"무료 진단 횟수({limit_cnt}회)를 모두 사용하셨습니다. 유료 진단을 이용해 주세요."
            )
    else:
        # 유료: payment_ref 필수
        if not body.payment_ref:
            price = PAID_TIER_PRICES.get(tier_code, 0)
            raise HTTPException(
                status_code=402,
                detail=f"유료 진단입니다. 결제 완료 후 payment_ref를 포함해 주세요. (가격: {price:,}원)"
            )

    # 5. 엔진 입력 구성
    inp: dict = {
        "region":         body.region or "",
        "anonymous_flow": True,
        "tier_code":      tier_code,
    }
    workers = body.worker_count or body.direct_workers or 0
    employees = body.employee_count or workers
    floor_area = body.floor_area or 400.0
    total_floor_area = body.total_floor_area or floor_area
    contract_eok = body.contract_amount_eok or 1.0

    if engine_sector == "CONSTRUCTION":
        step1_body = DiagnoseStep1Body(
            factory_id=None,
            sector=engine_sector,
            input=inp,
            construction_type=body.construction_type or "건축",
            contract_amount_eok=float(contract_eok),
            direct_workers=body.direct_workers or workers,
            subcon_workers=body.subcon_workers or 0,
        )
    elif engine_sector == "BUILDING":
        step1_body = DiagnoseStep1Body(
            factory_id=None,
            sector=engine_sector,
            input=inp,
            building_use_type=body.building_use_type or "사무실",
            floor_area=float(floor_area),
            total_floor_area=float(total_floor_area),
            worker_count=workers,
            employee_count=employees,
            floor_count=5,
        )
    else:  # MANUFACTURING
        step1_body = DiagnoseStep1Body(
            factory_id=None,
            sector=engine_sector,
            input=inp,
            worker_count=workers,
            employee_count=employees,
            floor_area=float(floor_area),
            total_floor_area=float(total_floor_area),
            ksic_major=body.ksic_major or "",
        )

    # 6. 엔진 실행
    eng = await diagnose_step1(step1_body)
    if eng.get("status") != "success":
        raise HTTPException(status_code=500, detail="진단 실행에 실패했습니다.")

    full_result  = eng["data"]
    public_token = str(uuid.uuid4())
    expires_at   = None  # 유료는 만료 없음, 무료는 7일
    if is_free:
        from datetime import timedelta
        expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

    row = {
        "public_token":     public_token,
        "input_data": {
            "sector":              sector,
            "tier_code":           tier_code,
            "floor_area":          floor_area,
            "contract_amount_eok": contract_eok,
            "workers":             workers,
        },
        "partial_result":  _build_partial(full_result),
        "full_result":     full_result,
        "expires_at":      expires_at,
        "status":          "ACTIVE",
        "source_type":     "free_diag" if is_free else "paid_diag",
        "engine_version":  ENGINE_VERSION,
        "ci_hash":         auth_row["ci_hash"],
        "auth_log_id":     auth_row["id"],
        "disclaimer_log_id": body.disclaimer_log_id,
        "tier_code":       tier_code,
        "paid_amount":     0 if is_free else (PAID_TIER_PRICES.get(tier_code, 0)),
        "payment_ref":     body.payment_ref,
    }

    ins = supabase.table("anonymous_diagnosis_results").insert(row).execute()
    if not ins.data:
        raise HTTPException(status_code=500, detail="결과 저장에 실패했습니다.")

    # 8. 무료면 free_count+1
    if is_free:
        supabase.table("diagnosis_auth_log").update({
            "free_count": (auth_row.get("free_count") or 0) + 1,
            "last_free_at": _now(),
            "updated_at":   _now(),
        }).eq("id", auth_row["id"]).execute()

    remaining_after = 0
    if is_free:
        remaining_after = max(0, (auth_row.get("free_limit") or 3) - ((auth_row.get("free_count") or 0) + 1))

    return {
        "status":        "success",
        "public_token":  public_token,
        "tier_code":     tier_code,
        "is_free":       is_free,
        "expires_at":    expires_at,
        "free_remaining_after": remaining_after if is_free else None,
        "result":        full_result,
    }


def _build_partial(full: dict) -> dict:
    """full_result → 일부만 노출하는 partial."""
    return {
        "risk_level":        full.get("risk_level"),
        "summary":           full.get("summary"),
        "applicable_count":  full.get("applicable_count"),
        "sector":            full.get("sector"),
        "key_obligations":   (full.get("key_obligations") or [])[:6],
        "law_badges":        (full.get("law_badges") or [])[:18],
    }


# ───────────────────────────────────────────────────────────────────────────
# TASK 5: POST /diagnosis/upgrade — 업그레이드 차액 결제
# ───────────────────────────────────────────────────────────────────────────

class UpgradeBody(BaseModel):
    auth_token:       str = Field(..., description="본인인증 auth_token")
    public_token:     str = Field(..., description="기존 진단 public_token")
    target_tier_code: str = Field(..., description="업그레이드 목표 티어")
    payment_ref:      str = Field(..., description="결제 참조 번호")


@router.post("/upgrade")
async def upgrade_diagnosis(body: UpgradeBody):
    """
    TASK 5: 업그레이드 차액 결제 후 엔진 재실행.

    흐름:
      1. auth_token + public_token 지번 확인
      2. 기존 tier vs 목표 tier 차액 계산
      3. payment_ref 존재 확인 (실제 KG이니시스 연동 후 검증 교체)
      4. 엔진 재실행 — 같은 입력으로 tier만 변경
      5. 기존 레코드 업데이트 (full_result, tier_code, paid_amount)
    """
    from routers.legal_engine import DiagnoseStep1Body, diagnose_step1
    from routers.legal_engine import ENGINE_VERSION

    supabase  = get_supabase()
    auth_row  = _resolve_auth_log(supabase, body.auth_token)

    # 기존 진단 조회
    existing = (
        supabase.table("anonymous_diagnosis_results")
        .select("id, ci_hash, tier_code, input_data, paid_amount, status")
        .eq("public_token", body.public_token)
        .limit(1)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="진단 레코드를 찾을 수 없습니다.")

    rec = existing.data[0]
    if rec["ci_hash"] != auth_row["ci_hash"]:
        raise HTTPException(status_code=403, detail="자신의 진단만 업그레이드할 수 있습니다.")

    current_tier = rec.get("tier_code") or ""
    target_tier  = body.target_tier_code
    current_price = PAID_TIER_PRICES.get(current_tier, 0)
    target_price  = PAID_TIER_PRICES.get(target_tier)

    if target_price is None:
        raise HTTPException(status_code=422, detail=f"업그레이드 불가 티어: {target_tier}")
    if target_price <= current_price:
        raise HTTPException(status_code=422, detail="더 높은 등급으로만 업그레이드 가능합니다.")

    diff_price = target_price - current_price
    log.info("[UPGRADE] %s → %s, diff=%d, payment_ref=%s", current_tier, target_tier, diff_price, body.payment_ref)

    # 엔진 재실행 (동일 입력 데이터, tier만 변경)
    input_data = rec.get("input_data") or {}
    inp = {"tier_code": target_tier, "anonymous_flow": True, "upgrade": True}
    sector = (input_data.get("sector") or "").upper()
    engine_sector = "MANUFACTURING" if sector == "INDUSTRY" else sector
    workers = int(input_data.get("workers") or 0)
    floor_area = float(input_data.get("floor_area") or 400.0)
    contract_eok = float(input_data.get("contract_amount_eok") or 1.0)

    if engine_sector == "CONSTRUCTION":
        step1_body = DiagnoseStep1Body(
            factory_id=None, sector=engine_sector, input=inp,
            construction_type="건축",
            contract_amount_eok=contract_eok,
            direct_workers=workers, subcon_workers=0,
        )
    elif engine_sector == "BUILDING":
        step1_body = DiagnoseStep1Body(
            factory_id=None, sector=engine_sector, input=inp,
            building_use_type="사무실",
            floor_area=floor_area, total_floor_area=floor_area,
            worker_count=workers, employee_count=workers, floor_count=5,
        )
    else:
        step1_body = DiagnoseStep1Body(
            factory_id=None, sector=engine_sector, input=inp,
            worker_count=workers, employee_count=workers,
            floor_area=floor_area, total_floor_area=floor_area, ksic_major="",
        )

    eng = await diagnose_step1(step1_body)
    if eng.get("status") != "success":
        raise HTTPException(status_code=500, detail="엔진 재실행에 실패했습니다.")

    new_full = eng["data"]
    supabase.table("anonymous_diagnosis_results").update({
        "full_result":  new_full,
        "partial_result": _build_partial(new_full),
        "tier_code":    target_tier,
        "paid_amount":  int(rec.get("paid_amount") or 0) + diff_price,
        "payment_ref":  body.payment_ref,
        "status":       "ACTIVE",
        "expires_at":   None,   # 유료 전환 → 만료 없음
    }).eq("id", rec["id"]).execute()

    return {
        "status":           "success",
        "public_token":     body.public_token,
        "prev_tier":        current_tier,
        "new_tier":         target_tier,
        "diff_paid_krw":    diff_price,
        "result":           new_full,
    }
