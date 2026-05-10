"""
본인인증(이니시스 간편인증) 라우터 — v1.1.0

v1.1.0 변경점:
- prepare에 이니시스 SHA256 signature 생성 활성화 (TODO 채움)
- callback 성공 시 회원가입 전 verify_token 발급 (oauth/auth register에서 소비)
- consume_verify_token() 함수 공개 — 회원가입 시 본인인증 필수 강제
- CI 중복 체크 강화 — 신규 가입 시 이미 다른 계정에 CI있으면 경고

prefix: /identity (main.py에서 지정)

DB schema:
  identity_logs.user_id — NULL 허용 필요 (신규 가입 전 인증):
    ALTER TABLE identity_logs ALTER COLUMN user_id DROP NOT NULL;
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)
router = APIRouter()

# ── 환경변수 (이니시스 API 키 수령 후 Railway에 등록) ─────────────────
INICIS_VERIFY_MID      = os.getenv("INICIS_VERIFY_MID", "")
INICIS_VERIFY_SITE_CD  = os.getenv("INICIS_VERIFY_SITE_CD", "")
INICIS_VERIFY_SITE_KEY = os.getenv("INICIS_VERIFY_SITE_KEY", "")

# 이니시스 간편인증 팝업 URL — 운영/테스트 분리
# ❗ 이니시스 공식 문서 확인 후 교체 필요 (대략적 예시 URL)
INICIS_POPUP_URL_PROD = os.getenv("INICIS_POPUP_URL_PROD", "https://kssa.inicis.com/idauth/auth")
INICIS_POPUP_URL_TEST = os.getenv("INICIS_POPUP_URL_TEST", "https://kssa-test.inicis.com/idauth/auth")
INICIS_POPUP_URL      = INICIS_POPUP_URL_PROD if os.getenv("ENV") == "production" else INICIS_POPUP_URL_TEST

VERIFY_RETURN_URL = os.getenv("INICIS_VERIFY_RETURN_URL", "https://api.taieng.co.kr/identity/callback")

# 회원가입 전 본인인증용 임시 토큰 (in-memory, 30분 유효)
# TODO: production 시 Redis로 migration
_VERIFY_TOKENS: dict[str, dict] = {}


# ── 유틸 ───────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _make_signature(timestamp: str) -> str:
    """이니시스 SHA256 서명 생성 — site_key + timestamp + mid"""
    return _sha256(INICIS_VERIFY_SITE_KEY + timestamp + INICIS_VERIFY_MID)


# ── Pydantic 모델 ───────────────────────────────────────────────────
class PrepareBody(BaseModel):
    user_id: Optional[str] = None  # 있으면 기존 회원 / 없으면 신규 가입 전 인증
    method:  str = "PHONE"          # PHONE / KAKAO / PASS


# ── /status ───────────────────────────────────────────────────────
@router.get("/status")
def get_verify_status(user_id: str = Query(..., description="회원 UUID")):
    """본인인증 상태 조회"""
    supabase = get_supabase()
    res = supabase.table("users").select(
        "id, identity_verified, identity_verified_at, "
        "identity_name, identity_phone, identity_method, "
        "identity_gender, identity_birth, identity_nation"
    ).eq("id", user_id).limit(1).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다.")

    user = res.data[0]
    return {
        "status": "success",
        "data": {
            "is_verified":  user.get("identity_verified", False),
            "verified_at":  user.get("identity_verified_at"),
            "name":         user.get("identity_name"),
            "phone":        user.get("identity_phone"),
            "method":       user.get("identity_method"),
            "gender":       user.get("identity_gender"),
            "birth":        user.get("identity_birth"),
            "nation":       user.get("identity_nation"),
        },
    }


# ── /prepare ──────────────────────────────────────────────────────
@router.post("/prepare")
def prepare_verify(body: PrepareBody):
    """
    본인인증 준비 — 이니시스 팝업 파라미터 생성

    두 시나리오:
    - 방식 A (가입 전 인증): user_id 없음 → 콜백에서 verify_token 발급
    - 기존 회원 인증:        user_id 있음 → 콜백에서 users 테이블 즉시 업데이트
    """
    if not INICIS_VERIFY_MID:
        raise HTTPException(
            status_code=503,
            detail="본인인증 서비스 준비 중입니다. 잠시 후 이용해 주세요.",
        )

    supabase  = get_supabase()
    timestamp = str(int(time.time() * 1000))

    # identity_logs에 PENDING 기록 (user_id NULL 가능)
    log_res = supabase.table("identity_logs").insert({
        "user_id":    body.user_id,
        "method":     body.method,
        "status":     "PENDING",
        "created_at": _now_iso(),
    }).execute()

    request_id = log_res.data[0]["id"] if log_res.data else ""

    return {
        "status": "success",
        "data": {
            "request_id": request_id,
            "mid":        INICIS_VERIFY_MID,
            "site_cd":    INICIS_VERIFY_SITE_CD,
            "timestamp":  timestamp,
            "return_url": VERIFY_RETURN_URL,
            "signature":  _make_signature(timestamp),
            "method":     body.method,
            "popup_url":  INICIS_POPUP_URL,
            # 프론트엔드가 이니시스 팝업에 form POST로 전달할 필드:
            #   mid, site_cd, timestamp, signature, return_url, request_id (state로 사용)
        },
    }


# ── /callback ────────────────────────────────────────────────────
@router.post("/callback")
async def verify_callback(request: Request):
    """
    이니시스 콜백
    - user_id 있으면: 즉시 users 테이블 업데이트
    - user_id 없으면: verify_token 발급 → 회원가입 폼으로 전달
    """
    try:
        form = await request.form()
        data = dict(form)
    except Exception:
        try:
            data = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="요청 파싱 실패")

    log.info(f"[IDENTITY CALLBACK] received keys: {list(data.keys())}")

    result_code = data.get("resultCode", "")
    request_id  = data.get("requestId", "") or data.get("mid", "")

    supabase = get_supabase()
    now      = _now_iso()

    # ── 인증 실패 ───────────────────────────────────────
    if result_code != "0000":
        fail_msg = data.get("resultMsg", "인증 실패")
        if request_id:
            supabase.table("identity_logs").update({
                "status":       "FAILED",
                "fail_reason":  fail_msg,
                "completed_at": now,
            }).eq("id", request_id).execute()

        return HTMLResponse(
            f"<script>"
            f"window.opener?.onVerifyComplete({{success:false,message:'{fail_msg}'}});"
            f"window.close();"
            f"</script>"
        )

    # ── 인증 성공 ───────────────────────────────────────
    # ⚠  실제 필드명은 이니시스 간편인증 API 문서 기준으로 수정 필요
    ci      = data.get("ci",        data.get("CI", ""))
    di      = data.get("di",        data.get("DI", ""))
    name    = data.get("name",      data.get("userName", ""))
    birth   = data.get("birthDate", data.get("userBirthday", ""))
    gender  = data.get("gender",    data.get("userGender", ""))
    nation  = data.get("nation",    "KOREAN")
    phone   = data.get("phoneNo",   data.get("userPhone", ""))
    carrier = data.get("telecom",   data.get("userTelecom", ""))

    # 로그에서 user_id 조회
    log_res = (
        supabase.table("identity_logs")
        .select("user_id, method")
        .eq("id", request_id)
        .limit(1)
        .execute()
    )
    if not log_res.data:
        return HTMLResponse(
            "<script>"
            "window.opener?.onVerifyComplete({success:false,message:'요청을 찾을 수 없습니다.'});"
            "window.close();"
            "</script>"
        )

    user_id = log_res.data[0]["user_id"]
    method  = log_res.data[0]["method"]

    # CI 중복 체크
    if user_id:
        # 기존 회원 인증 — 다른 계정이 동일 CI를 가진 경우
        ci_check = (
            supabase.table("users")
            .select("id")
            .eq("identity_ci", ci)
            .neq("id", user_id)
            .limit(1)
            .execute()
        )
        if ci_check.data:
            supabase.table("identity_logs").update({
                "status":       "FAILED",
                "fail_reason":  "이미 다른 계정에서 인증된 CI",
                "completed_at": now,
            }).eq("id", request_id).execute()
            return HTMLResponse(
                "<script>"
                "window.opener?.onVerifyComplete({success:false,message:'이미 인증된 계정이 있습니다.'});"
                "window.close();"
                "</script>"
            )
    else:
        # 신규 가입 전 인증 — CI로 이미 가입된 회원이 있는지
        ci_existing = (
            supabase.table("users")
            .select("id, email, oauth_provider")
            .eq("identity_ci", ci)
            .limit(1)
            .execute()
        )
        if ci_existing.data:
            existing = ci_existing.data[0]
            login_hint = (
                f"{existing['oauth_provider']}로 간편 로그인"
                if existing.get("oauth_provider")
                else "이메일/비밀번호로 로그인"
            )
            supabase.table("identity_logs").update({
                "status":       "FAILED",
                "fail_reason":  "이미 가입된 명의",
                "completed_at": now,
            }).eq("id", request_id).execute()
            return HTMLResponse(
                f"<script>"
                f"window.opener?.onVerifyComplete({{"
                f"success:false,"
                f"message:'이미 가입된 명의입니다. {login_hint}을 이용해 주세요.',"
                f"already_registered:true"
                f"}});"
                f"window.close();"
                f"</script>"
            )

    # 기존 회원 — users 테이블 즉시 업데이트
    if user_id:
        supabase.table("users").update({
            "identity_ci":          ci,
            "identity_di":          di,
            "identity_name":        name,
            "identity_birth":       birth,
            "identity_gender":      gender,
            "identity_nation":      nation,
            "identity_phone":       phone,
            "identity_carrier":     carrier,
            "identity_method":      method,
            "identity_verified":    True,
            "identity_verified_at": now,
            "updated_at":           now,
        }).eq("id", user_id).execute()

    # 로그 완료 처리
    supabase.table("identity_logs").update({
        "status":       "SUCCESS",
        "ci":           ci,
        "di":           di,
        "completed_at": now,
    }).eq("id", request_id).execute()

    # 신규 가입 전 인증 — verify_token 발급
    verify_token = None
    if not user_id:
        verify_token = _issue_verify_token({
            "ci":      ci,
            "di":      di,
            "name":    name,
            "birth":   birth,
            "gender":  gender,
            "nation":  nation,
            "phone":   phone,
            "carrier": carrier,
            "method":  method,
        })

    # postMessage로 결과 전달 (verify_token 있으면 포함)
    payload_parts = [
        "success:true",
        f"name:'{name}'",
        f"phone:'{phone}'",
    ]
    if verify_token:
        payload_parts.append(f"verify_token:'{verify_token}'")
    payload_js = "{" + ",".join(payload_parts) + "}"

    return HTMLResponse(
        f"<script>"
        f"window.opener?.onVerifyComplete({payload_js});"
        f"window.close();"
        f"</script>"
    )


# ── verify_token 헬퍼 (oauth.py / auth.py register에서 import 사용) ───────
def _issue_verify_token(payload: dict) -> str:
    """본인인증 성공 후 회원가입 단계로 넘길 임시 토큰 (30분 유효)"""
    token = secrets.token_urlsafe(32)
    _VERIFY_TOKENS[token] = {
        **payload,
        "expires_at": _now_ts() + 1800,
    }
    log.info(f"[IDENTITY] verify_token 발급 — method={payload.get('method')}, expires_at={_VERIFY_TOKENS[token]['expires_at']}")
    return token


def consume_verify_token(token: str) -> Optional[dict]:
    """
    회원가입 시 호출 — 토큰을 검증하고 본인인증 정보 반환.
    한 번 사용하면 삭제 (재사용 불가).

    반환 dict의 키: ci, di, name, birth, gender, nation, phone, carrier, method
    """
    data = _VERIFY_TOKENS.pop(token, None)
    if not data:
        return None
    if data["expires_at"] < _now_ts():
        return None
    return data


# ── 어드민 목록 ────────────────────────────────────────────────────
@router.get("/admin/list")
def admin_list_verified(
    is_verified: Optional[bool] = Query(None, description="인증 완료 여부"),
    method:      Optional[str]  = Query(None, description="PHONE / KAKAO / PASS"),
    keyword:     Optional[str]  = Query(None, description="이름 또는 연락처 검색"),
    page: int = Query(1,  ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """어드민용 — 본인인증 현황 목록"""
    supabase = get_supabase()
    q = supabase.table("users").select(
        "id, name, email, phone, "
        "identity_verified, identity_verified_at, identity_method, "
        "identity_name, identity_phone, identity_birth, identity_gender",
        count="exact",
    )

    if is_verified is not None:
        q = q.eq("identity_verified", is_verified)
    if method:
        q = q.eq("identity_method", method)
    if keyword:
        q = q.or_(f"name.ilike.%{keyword}%,identity_phone.ilike.%{keyword}%")

    offset = (page - 1) * size
    res    = q.order("identity_verified_at", desc=True).range(offset, offset + size - 1).execute()
    total  = res.count or 0

    return {
        "status": "success",
        "data": {
            "items": res.data or [],
            "total": total,
            "page":  page,
            "size":  size,
        },
    }
