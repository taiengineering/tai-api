"""
본인인증(이니시스 간편인증) 라우터 — v1.0.0

이니시스 간편인증 API 문서 기반으로 구현.
현재는 구조 설계 단계 — 이니시스 API 키 수령 후 실제 연동.

prefix: /identity (main.py에서 지정)
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

# prefix는 main.py에서 지정 — 여기서는 절대 넣지 않음
router = APIRouter()

# ── 환경변수 (이니시스 API 키 수령 후 Railway에 등록) ─────────────────
INICIS_VERIFY_MID      = os.getenv("INICIS_VERIFY_MID", "")
INICIS_VERIFY_SITE_CD  = os.getenv("INICIS_VERIFY_SITE_CD", "")
INICIS_VERIFY_SITE_KEY = os.getenv("INICIS_VERIFY_SITE_KEY", "")

FRONT_CALLBACK_URL = "https://tadmin.taieng.co.kr/html/horizontal-menu-template/identity-verify.html"
VERIFY_RETURN_URL  = "https://api.taieng.co.kr/identity/callback"


# ── 유틸 ────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


# ── Pydantic 모델 ────────────────────────────────────────────────────────

class PrepareBody(BaseModel):
    user_id: str             # 로그인 회원 UUID (필수)
    method:  str = "PHONE"  # PHONE / KAKAO / PASS


# ── 엔드포인트 ───────────────────────────────────────────────────────────

@router.get("/status")
def get_verify_status(user_id: str = Query(..., description="회원 UUID")):
    """
    본인인증 상태 조회
    GET /identity/status?user_id={uuid}
    """
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


@router.post("/prepare")
def prepare_verify(body: PrepareBody):
    """
    본인인증 준비 — 이니시스 팝업 파라미터 생성
    POST /identity/prepare

    ⚠️  이니시스 API 키 수령 후 실제 구현 필요.
        현재는 구조만 반환 (플레이스홀더).
    """
    if not INICIS_VERIFY_MID:
        raise HTTPException(
            status_code=503,
            detail="본인인증 서비스 준비 중입니다. 잠시 후 이용해 주세요.",
        )

    supabase  = get_supabase()
    timestamp = str(int(time.time() * 1000))

    # identity_logs에 PENDING 기록
    log_res = supabase.table("identity_logs").insert({
        "user_id":    body.user_id,
        "method":     body.method,
        "status":     "PENDING",
        "created_at": _now_iso(),
    }).execute()

    request_id = log_res.data[0]["id"] if log_res.data else ""

    # TODO: 이니시스 간편인증 파라미터 생성
    #       실제 구현 시 이니시스 문서의 signature 생성 방식 적용
    #       signature = _sha256(INICIS_VERIFY_SITE_KEY + timestamp + INICIS_VERIFY_MID)
    return {
        "status": "success",
        "data": {
            "request_id": request_id,
            "mid":        INICIS_VERIFY_MID,
            "site_cd":    INICIS_VERIFY_SITE_CD,
            "timestamp":  timestamp,
            "return_url": VERIFY_RETURN_URL,
            "signature":  "",   # SHA256 서명 (TODO: 이니시스 키 수령 후)
            "method":     body.method,
            "popup_url":  "",   # 이니시스 팝업 URL (TODO)
        },
    }


@router.post("/callback")
async def verify_callback(request: Request):
    """
    이니시스 본인인증 콜백
    POST /identity/callback

    인증 완료 후 이니시스가 이 URL로 결과 전송.
    성공/실패 여부를 opener(프론트)로 postMessage 후 팝업 닫기.

    ⚠️  실제 필드명은 이니시스 간편인증 API 문서 기준으로 수정 필요.
    """
    # form-data 또는 JSON 모두 허용
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

    # ── 인증 실패 ─────────────────────────────────────────────
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

    # ── 인증 성공 ─────────────────────────────────────────────
    # ⚠️  실제 필드명은 이니시스 문서 확인 후 수정
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

    # CI 중복 체크 — 동일인이 다른 계정에서 이미 인증된 경우 차단
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

    # users 테이블 업데이트
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

    return HTMLResponse(
        f"<script>"
        f"window.opener?.onVerifyComplete({{success:true,name:'{name}',phone:'{phone}'}});"
        f"window.close();"
        f"</script>"
    )


@router.get("/admin/list")
def admin_list_verified(
    is_verified: Optional[bool] = Query(None, description="인증 완료 여부"),
    method:      Optional[str]  = Query(None, description="PHONE / KAKAO / PASS"),
    keyword:     Optional[str]  = Query(None, description="이름 또는 연락처 검색"),
    page: int = Query(1,  ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """
    어드민용 — 본인인증 현황 목록
    GET /identity/admin/list
    """
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
