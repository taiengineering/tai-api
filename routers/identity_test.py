"""본인인증 Mock 테스트 라우터.

이니시스 실키 발급 전 전체 플로우 테스트용.
Mock 모드에서도 실제 콜백 로직(CI 저장, 중복체크, verify_token 발급)을
동일하게 실행한다.

prefix: /identity/test
"""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from db.supabase_client import get_supabase
from services.payment_helpers import load_template

# 실제 identity.py의 verify_token 함수 재사용
from routers.identity import (
    consume_verify_token,
    _issue_verify_token,
    _now_iso,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/identity/test", tags=["본인인증-테스트"])


def _mock_ci(name: str, phone: str) -> str:
    """테스트용 가짜 CI 생성 (동일 이름+번호 → 동일 CI)."""
    raw = f"MOCK_CI:{name}:{phone}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _mock_di(name: str, phone: str) -> str:
    """테스트용 가짜 DI 생성."""
    raw = f"MOCK_DI:{name}:{phone}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ── 테스트 페이지 ──────────────────────────────────────────────

@router.get("/page", response_class=HTMLResponse)
def identity_test_page():
    """본인인증 테스트 UI 페이지."""
    return HTMLResponse(content=load_template("identity_test.html"), status_code=200)


# ── Mock 시나리오 ──────────────────────────────────────────────

class MockVerifyBody(BaseModel):
    """Mock 본인인증 요청."""
    user_id: Optional[str] = None  # 있으면 기존회원, 없으면 신규가입전
    name: str = "홍길동"
    phone: str = "01012345678"
    birth: str = "19900101"
    gender: str = "M"
    method: str = "PASS"  # PASS / KAKAO / NAVER / TOSS


@router.post("/simulate")
def simulate_verify(body: MockVerifyBody):
    """Mock 본인인증 실행.

    이니시스 팝업 없이 실제 콜백 로직을 동일하게 실행:
    1) identity_logs PENDING → SUCCESS
    2) CI/DI 중복 체크
    3) 기존회원: users 테이블 업데이트
    4) 신규: verify_token 발급
    """
    sb = get_supabase()
    now = _now_iso()

    ci = _mock_ci(body.name, body.phone)
    di = _mock_di(body.name, body.phone)

    # 1) identity_logs PENDING 기록
    log_res = sb.table("identity_logs").insert({
        "user_id": body.user_id,
        "method": body.method,
        "status": "PENDING",
        "created_at": now,
    }).execute()
    request_id = log_res.data[0]["id"] if log_res.data else None

    # 2) CI 중복 체크
    if body.user_id:
        # 기존 회원 — 다른 계정이 동일 CI?
        ci_check = (
            sb.table("users")
            .select("id, email")
            .eq("identity_ci", ci)
            .neq("id", body.user_id)
            .limit(1)
            .execute()
        )
        if ci_check.data:
            sb.table("identity_logs").update({
                "status": "FAILED",
                "fail_reason": "이미 다른 계정에서 인증된 CI (Mock)",
                "completed_at": now,
            }).eq("id", request_id).execute()
            return {
                "ok": False,
                "error": "CI_DUPLICATE",
                "message": f"이미 인증된 계정이 있습니다: {ci_check.data[0]['email']}",
            }
    else:
        # 신규 가입 전 — CI로 이미 가입된 회원?
        ci_existing = (
            sb.table("users")
            .select("id, email, oauth_provider")
            .eq("identity_ci", ci)
            .limit(1)
            .execute()
        )
        if ci_existing.data:
            existing = ci_existing.data[0]
            sb.table("identity_logs").update({
                "status": "FAILED",
                "fail_reason": "이미 가입된 명의 (Mock)",
                "completed_at": now,
            }).eq("id", request_id).execute()
            return {
                "ok": False,
                "error": "ALREADY_REGISTERED",
                "message": f"이미 가입된 명의입니다: {existing['email']}",
                "existing_email": existing["email"],
            }

    # 3) 기존 회원 → users 테이블 업데이트
    if body.user_id:
        sb.table("users").update({
            "identity_ci": ci,
            "identity_di": di,
            "identity_name": body.name,
            "identity_birth": body.birth,
            "identity_gender": body.gender,
            "identity_nation": "KOREAN",
            "identity_phone": body.phone,
            "identity_carrier": "",
            "identity_method": body.method,
            "identity_verified": True,
            "identity_verified_at": now,
            "updated_at": now,
        }).eq("id", body.user_id).execute()

    # 4) identity_logs 완료
    sb.table("identity_logs").update({
        "status": "SUCCESS",
        "ci": ci,
        "di": di,
        "completed_at": now,
    }).eq("id", request_id).execute()

    # 5) 신규 가입 전 → verify_token 발급
    verify_token = None
    if not body.user_id:
        verify_token = _issue_verify_token({
            "ci": ci,
            "di": di,
            "name": body.name,
            "birth": body.birth,
            "gender": body.gender,
            "nation": "KOREAN",
            "phone": body.phone,
            "carrier": "",
            "method": body.method,
        })

    log.info(
        "[MOCK_VERIFY] user_id=%s name=%s ci=%s...%s token=%s",
        body.user_id, body.name, ci[:8], ci[-4:],
        verify_token[:16] if verify_token else "N/A",
    )

    result = {
        "ok": True,
        "data": {
            "request_id": request_id,
            "mock": True,
            "ci": ci,
            "di": di,
            "name": body.name,
            "phone": body.phone,
            "birth": body.birth,
            "gender": body.gender,
            "method": body.method,
        },
    }

    if body.user_id:
        result["data"]["user_updated"] = True
        result["data"]["user_id"] = body.user_id
    else:
        result["data"]["verify_token"] = verify_token
        result["data"]["message"] = "verify_token으로 회원가입 API 호출 가능"

    return result


# ── verify_token 확인 ──────────────────────────────────────────

@router.post("/consume-token")
def test_consume_token(token: str = Query(..., description="verify_token")):
    """verify_token 소비 테스트.

    회원가입 시 실제로 호출되는 consume_verify_token()을 테스트.
    한 번 사용하면 소멸.
    """
    data = consume_verify_token(token)
    if not data:
        return {"ok": False, "error": "INVALID_TOKEN", "message": "토큰이 유효하지 않거나 만료됨"}
    return {
        "ok": True,
        "data": data,
        "message": "토큰 소비 완료 — 이 정보로 회원가입 진행 가능",
    }


# ── Mock 인증 실패 시뮬레이션 ──────────────────────────────────

@router.post("/simulate-fail")
def simulate_verify_fail(
    user_id: Optional[str] = None,
    fail_reason: str = "사용자 인증 취소",
    method: str = "PASS",
):
    """Mock 인증 실패 시뮬레이션."""
    sb = get_supabase()
    now = _now_iso()

    log_res = sb.table("identity_logs").insert({
        "user_id": user_id,
        "method": method,
        "status": "FAILED",
        "fail_reason": f"[Mock] {fail_reason}",
        "created_at": now,
        "completed_at": now,
    }).execute()

    return {
        "ok": True,
        "data": {
            "request_id": log_res.data[0]["id"] if log_res.data else None,
            "status": "FAILED",
            "fail_reason": fail_reason,
            "mock": True,
        },
    }


# ── 테스트 데이터 조회 ─────────────────────────────────────────

@router.get("/logs")
def test_logs(limit: int = Query(20, ge=1, le=100)):
    """최근 인증 로그 조회."""
    sb = get_supabase()
    resp = (
        sb.table("identity_logs")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return {"ok": True, "data": resp.data or []}


@router.get("/verified-users")
def test_verified_users(limit: int = Query(20, ge=1, le=100)):
    """본인인증 완료된 사용자 조회."""
    sb = get_supabase()
    resp = (
        sb.table("users")
        .select("id, name, email, identity_verified, identity_verified_at, identity_name, identity_phone, identity_method, identity_ci")
        .eq("identity_verified", True)
        .order("identity_verified_at", desc=True)
        .limit(limit)
        .execute()
    )
    return {"ok": True, "data": resp.data or []}


# ── 테스트 데이터 초기화 ───────────────────────────────────────

@router.post("/reset/{user_id}")
def test_reset_user(user_id: str):
    """특정 사용자의 본인인증 정보 초기화 (테스트용)."""
    sb = get_supabase()
    sb.table("users").update({
        "identity_ci": None,
        "identity_di": None,
        "identity_name": None,
        "identity_birth": None,
        "identity_gender": None,
        "identity_nation": None,
        "identity_phone": None,
        "identity_carrier": None,
        "identity_method": None,
        "identity_verified": False,
        "identity_verified_at": None,
        "updated_at": _now_iso(),
    }).eq("id", user_id).execute()

    return {"ok": True, "message": f"사용자 {user_id} 본인인증 초기화 완료"}
