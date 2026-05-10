"""
OAuth 간편로그인/간편회원가입 라우터 — v1.0.0
지원: 네이버 / 카카오 / 구글

prefix: /auth/oauth (main.py에서 지정)

엔드포인트:
- GET  /auth/oauth/{provider}                    — OAuth 인증 시작 (브라우저 redirect)
- GET  /auth/oauth/{provider}/callback           — OAuth provider 콜백 처리
- POST /auth/oauth/register                      — 신규 OAuth 회원가입 완료 (폼 제출)
- POST /auth/oauth/link                          — 기존 계정에 OAuth 연동
- POST /auth/oauth/unlink                        — OAuth 연동 해제
- GET  /auth/oauth/links/{user_id}               — OAuth 연동 현황 조회

환경변수 (.env에 입력 시 즉시 작동):
  NAVER_CLIENT_ID, NAVER_CLIENT_SECRET
  KAKAO_REST_API_KEY, KAKAO_CLIENT_SECRET (선택)
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
  OAUTH_REDIRECT_BASE                  — 기본: https://api.taieng.co.kr
  OAUTH_FRONTEND_SUCCESS_URL           — 기본: https://taieng.co.kr/log-in.html
  OAUTH_FRONTEND_REGISTER_URL          — 기본: https://taieng.co.kr/sign-up-oauth.html
  OAUTH_FRONTEND_ERROR_URL             — 기본: https://taieng.co.kr/log-in.html?error=oauth

DB 스키마 추가 필요:
  ALTER TABLE users ADD COLUMN oauth_provider VARCHAR(20);
  ALTER TABLE users ADD COLUMN oauth_provider_user_id VARCHAR(100);
  CREATE INDEX idx_users_oauth ON users(oauth_provider, oauth_provider_user_id);

main.py에 추가 필요:
  from routers import oauth
  app.include_router(oauth.router, prefix="/auth/oauth", tags=["oauth"])
"""
from __future__ import annotations

import logging
import os
import secrets
import urllib.parse
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

# prefix는 main.py에서 지정 — 여기서는 절대 넣지 않음
router = APIRouter()


# ── Provider Config ─────────────────────────────────────────────────
OAUTH_REDIRECT_BASE         = os.getenv("OAUTH_REDIRECT_BASE",         "https://api.taieng.co.kr")
OAUTH_FRONTEND_SUCCESS_URL  = os.getenv("OAUTH_FRONTEND_SUCCESS_URL",  "https://taieng.co.kr/log-in.html")
OAUTH_FRONTEND_REGISTER_URL = os.getenv("OAUTH_FRONTEND_REGISTER_URL", "https://taieng.co.kr/sign-up-oauth.html")
OAUTH_FRONTEND_ERROR_URL    = os.getenv("OAUTH_FRONTEND_ERROR_URL",    "https://taieng.co.kr/log-in.html?error=oauth")

PROVIDERS = {
    "naver": {
        "client_id":     os.getenv("NAVER_CLIENT_ID",     ""),
        "client_secret": os.getenv("NAVER_CLIENT_SECRET", ""),
        "auth_url":      "https://nid.naver.com/oauth2.0/authorize",
        "token_url":     "https://nid.naver.com/oauth2.0/token",
        "userinfo_url":  "https://openapi.naver.com/v1/nid/me",
        "scope":         "",  # 네이버는 관리자 콘솔에서 제공항목 설정
    },
    "kakao": {
        "client_id":     os.getenv("KAKAO_REST_API_KEY",  ""),
        "client_secret": os.getenv("KAKAO_CLIENT_SECRET", ""),  # 선택 (카카오 디벨로퍼스에서 on/off)
        "auth_url":      "https://kauth.kakao.com/oauth/authorize",
        "token_url":     "https://kauth.kakao.com/oauth/token",
        "userinfo_url":  "https://kapi.kakao.com/v2/user/me",
        "scope":         "profile_nickname account_email",
    },
    "google": {
        "client_id":     os.getenv("GOOGLE_CLIENT_ID",     ""),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
        "auth_url":      "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url":     "https://oauth2.googleapis.com/token",
        "userinfo_url":  "https://www.googleapis.com/oauth2/v3/userinfo",
        "scope":         "openid email profile",
    },
}

# CSRF 방지용 state 저장 — 운영에서는 Redis/DB 권장 (간단히 in-memory)
# TODO: production-grade state storage
_OAUTH_STATES: dict[str, dict] = {}

# OAuth 후 신규 회원가입 페이지 이동 시 임시 토큰 (30분 유효) — 동일하게 Redis 권장
_TEMP_REGISTER_TOKENS: dict[str, dict] = {}


# ── 유틸 ─────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _provider_config(provider: str) -> dict:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 provider: {provider}")
    cfg = PROVIDERS[provider]
    if not cfg["client_id"]:
        raise HTTPException(
            status_code=503,
            detail=f"{provider} OAuth 키가 설정되지 않았습니다. 관리자에게 문의해 주세요.",
        )
    return cfg


def _redirect_uri(provider: str) -> str:
    return f"{OAUTH_REDIRECT_BASE}/auth/oauth/{provider}/callback"


def _create_session_token(user_id: str) -> str:
    """
    세션 토큰 발급.
    TODO: routers/auth.py의 JWT 발급 함수 재사용 (utils/auth.py로 분리 권장).
          임시로 random token 발급 — 실제 운영 전 반드시 JWT로 교체.
    """
    return secrets.token_urlsafe(48)


# ── 1단계: OAuth 인증 시작 ───────────────────────────────────────────
@router.get("/{provider}")
def oauth_start(
    provider: str,
    redirect: Optional[str] = Query(None, description="로그인 후 돌아갈 프론트엔드 URL"),
):
    """OAuth provider 로그인 페이지로 redirect."""
    cfg   = _provider_config(provider)
    state = secrets.token_urlsafe(32)

    _OAUTH_STATES[state] = {
        "provider":   provider,
        "redirect":   redirect or OAUTH_FRONTEND_SUCCESS_URL,
        "expires_at": _now_ts() + 600,  # 10분
    }

    params = {
        "client_id":     cfg["client_id"],
        "redirect_uri":  _redirect_uri(provider),
        "response_type": "code",
        "state":         state,
    }
    if cfg["scope"]:
        params["scope"] = cfg["scope"]

    auth_url = f"{cfg['auth_url']}?{urllib.parse.urlencode(params)}"
    log.info(f"[OAUTH] {provider} start → {auth_url}")
    return RedirectResponse(auth_url)


# ── 2단계: 콜백 처리 ────────────────────────────────────────────────
@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    code:  Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    """
    provider가 호출하는 콜백
    → code → access_token 교환
    → userinfo 조회
    → 기존 회원이면 즉시 로그인, 신규면 가입 페이지로 이동
    """
    if error or not code:
        log.warning(f"[OAUTH] {provider} callback error: {error}")
        sep = "&" if "?" in OAUTH_FRONTEND_ERROR_URL else "?"
        return RedirectResponse(f"{OAUTH_FRONTEND_ERROR_URL}{sep}reason={error or 'no_code'}")

    state_data = _OAUTH_STATES.pop(state, None) if state else None
    if not state_data:
        return RedirectResponse(f"{OAUTH_FRONTEND_ERROR_URL}&reason=invalid_state")
    if state_data["expires_at"] < _now_ts():
        return RedirectResponse(f"{OAUTH_FRONTEND_ERROR_URL}&reason=expired_state")

    cfg = _provider_config(provider)

    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. code → access_token 교환
        token_data = {
            "grant_type":    "authorization_code",
            "client_id":     cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "code":          code,
            "redirect_uri":  _redirect_uri(provider),
            "state":         state,
        }
        if provider == "kakao" and not cfg["client_secret"]:
            token_data.pop("client_secret")

        token_res = await client.post(cfg["token_url"], data=token_data)
        if token_res.status_code != 200:
            log.error(f"[OAUTH] {provider} token error: {token_res.text}")
            return RedirectResponse(f"{OAUTH_FRONTEND_ERROR_URL}&reason=token_error")

        token_json   = token_res.json()
        access_token = token_json.get("access_token")
        if not access_token:
            return RedirectResponse(f"{OAUTH_FRONTEND_ERROR_URL}&reason=no_token")

        # 2. userinfo 조회
        userinfo_res = await client.get(
            cfg["userinfo_url"],
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_res.status_code != 200:
            log.error(f"[OAUTH] {provider} userinfo error: {userinfo_res.text}")
            return RedirectResponse(f"{OAUTH_FRONTEND_ERROR_URL}&reason=userinfo_error")

        userinfo = userinfo_res.json()

    # 3. provider별 userinfo 정규화
    profile = _normalize_userinfo(provider, userinfo)
    if not profile.get("provider_user_id"):
        return RedirectResponse(f"{OAUTH_FRONTEND_ERROR_URL}&reason=no_user_id")

    # 4. DB 조회 — 기존 OAuth 연동 사용자?
    supabase = get_supabase()
    existing = (
        supabase.table("users")
        .select("id, email, name, phone, role_code, company_id, company_name, identity_verified")
        .eq("oauth_provider", provider)
        .eq("oauth_provider_user_id", profile["provider_user_id"])
        .limit(1)
        .execute()
    )

    front_url = state_data["redirect"]

    if existing.data:
        # ── 기존 OAuth 사용자 — 즉시 로그인 ─────────────────────────────
        user          = existing.data[0]
        session_token = _create_session_token(user["id"])
        sep = "&" if "?" in front_url else "?"
        # URL fragment(#)으로 전달 — 서버 로그에 남지 않음
        return RedirectResponse(
            f"{front_url}{sep}oauth=success#token={session_token}&user_id={user['id']}"
        )

    # ── 신규 OAuth — 회원가입 페이지로 이동 (이메일/이름/provider 정보 prefill) ──
    register_token = _issue_temp_register_token(provider, profile)
    register_url = (
        f"{OAUTH_FRONTEND_REGISTER_URL}"
        f"?provider={provider}"
        f"&register_token={register_token}"
        f"&email={urllib.parse.quote(profile.get('email') or '')}"
        f"&name={urllib.parse.quote(profile.get('name') or '')}"
        f"&phone={urllib.parse.quote(profile.get('phone') or '')}"
    )
    return RedirectResponse(register_url)


# ── 3단계: 신규 OAuth 회원가입 완료 ─────────────────────────────────────
class OAuthRegisterBody(BaseModel):
    register_token: str
    name:           str
    phone:          str
    email:          str
    agree_terms:    bool                  # 이용약관 + 개인정보처리방침
    # 선택: 본인인증 완료 토큰 (방식 B — 가입 중 본인인증)
    identity_verify_token: Optional[str] = None


@router.post("/register")
async def oauth_register(body: OAuthRegisterBody):
    """
    OAuth로 시작한 회원가입 완료 — 폼 정보 + (선택) 본인인증 토큰 합쳐서 가입
    """
    if not body.agree_terms:
        raise HTTPException(status_code=400, detail="이용약관·개인정보처리방침에 동의해 주세요.")
    phone_clean = (body.phone or "").replace("-", "").strip()
    if len(phone_clean) < 10:
        raise HTTPException(status_code=400, detail="올바른 휴대폰 번호를 입력해 주세요.")

    profile = _consume_temp_register_token(body.register_token)
    if not profile:
        raise HTTPException(status_code=400, detail="유효하지 않거나 만료된 토큰입니다. 다시 시도해 주세요.")

    provider         = profile["provider"]
    provider_user_id = profile["provider_user_id"]

    supabase = get_supabase()
    email    = (body.email or "").strip().lower()

    # 이메일 중복 체크
    existing_email = (
        supabase.table("users")
        .select("id, oauth_provider")
        .eq("email", email)
        .limit(1)
        .execute()
    )

    if existing_email.data:
        existing = existing_email.data[0]
        if existing.get("oauth_provider") and existing["oauth_provider"] != provider:
            raise HTTPException(
                status_code=409,
                detail=f"이미 {existing['oauth_provider']}로 가입된 이메일입니다. 해당 로그인을 이용해 주세요.",
            )
        # 기존 일반 가입자 — OAuth 연동 추가
        supabase.table("users").update({
            "oauth_provider":         provider,
            "oauth_provider_user_id": provider_user_id,
            "updated_at":             _now_iso(),
        }).eq("id", existing["id"]).execute()
        user_id = existing["id"]
    else:
        new_user = {
            "email":                  email,
            "name":                   (body.name or "").strip(),
            "phone":                  phone_clean,
            "password_hash":          None,            # OAuth 사용자는 비밀번호 없음
            "oauth_provider":         provider,
            "oauth_provider_user_id": provider_user_id,
            "created_at":             _now_iso(),
            "updated_at":             _now_iso(),
        }
        ins = supabase.table("users").insert(new_user).execute()
        user_id = ins.data[0]["id"] if ins.data else None
        if not user_id:
            raise HTTPException(status_code=500, detail="회원가입에 실패했습니다.")

    # 본인인증 토큰 처리 (있으면) — identity 모듈과 연결
    if body.identity_verify_token:
        # TODO: identity.py에서 검증 함수 추가 후 import
        # from routers.identity import consume_verify_token
        # consume_verify_token(body.identity_verify_token, user_id)
        log.info(f"[OAUTH] register identity_verify_token 수신 — user_id={user_id}")

    session_token = _create_session_token(user_id)
    return {
        "status": "success",
        "data": {
            "access_token": session_token,
            "user_id":      user_id,
            "provider":     provider,
        },
    }


# ── OAuth 연동 관리 ─────────────────────────────────────────────────
class OAuthLinkBody(BaseModel):
    user_id:  str
    provider: str
    code:     str   # OAuth code (provider 파판에서 받은 code)


@router.post("/link")
async def oauth_link(body: OAuthLinkBody):
    """기존 계정에 OAuth 연동 추가 (로그인한 사용자가 마이페이지에서 연동)."""
    cfg = _provider_config(body.provider)

    async with httpx.AsyncClient(timeout=15.0) as client:
        token_data = {
            "grant_type":    "authorization_code",
            "client_id":     cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "code":          body.code,
            "redirect_uri":  _redirect_uri(body.provider),
        }
        if body.provider == "kakao" and not cfg["client_secret"]:
            token_data.pop("client_secret")
        token_res = await client.post(cfg["token_url"], data=token_data)
        if token_res.status_code != 200:
            raise HTTPException(status_code=400, detail="OAuth 토큰 교환에 실패했습니다.")
        access_token = token_res.json().get("access_token")
        userinfo = (await client.get(cfg["userinfo_url"], headers={"Authorization": f"Bearer {access_token}"})).json()

    profile = _normalize_userinfo(body.provider, userinfo)
    if not profile.get("provider_user_id"):
        raise HTTPException(status_code=400, detail="OAuth 사용자 정보 조회에 실패했습니다.")

    supabase = get_supabase()

    # 해당 OAuth로 이미 연동된 다른 계정이 있는지 체크
    dup = (
        supabase.table("users")
        .select("id")
        .eq("oauth_provider", body.provider)
        .eq("oauth_provider_user_id", profile["provider_user_id"])
        .neq("id", body.user_id)
        .limit(1)
        .execute()
    )
    if dup.data:
        raise HTTPException(status_code=409, detail="이 OAuth 계정은 이미 다른 회원에게 연동되어 있습니다.")

    supabase.table("users").update({
        "oauth_provider":         body.provider,
        "oauth_provider_user_id": profile["provider_user_id"],
        "updated_at":             _now_iso(),
    }).eq("id", body.user_id).execute()

    return {"status": "success", "data": {"provider": body.provider}}


@router.post("/unlink")
def oauth_unlink(user_id: str):
    """OAuth 연동 해제 — 비밀번호가 설정되어 있어야 해제 가능."""
    supabase = get_supabase()
    res = supabase.table("users").select("id, password_hash").eq("id", user_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다.")
    if not res.data[0].get("password_hash"):
        raise HTTPException(
            status_code=400,
            detail="비밀번호를 먼저 설정해 주세요. (OAuth만으로 가입된 계정은 바로 해제할 수 없습니다.)",
        )
    supabase.table("users").update({
        "oauth_provider":         None,
        "oauth_provider_user_id": None,
        "updated_at":             _now_iso(),
    }).eq("id", user_id).execute()
    return {"status": "success"}


@router.get("/links/{user_id}")
def get_oauth_links(user_id: str):
    """사용자의 OAuth 연동 현황 조회."""
    supabase = get_supabase()
    res = supabase.table("users").select("id, email, oauth_provider, oauth_provider_user_id").eq("id", user_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다.")
    user = res.data[0]
    return {
        "status": "success",
        "data": {
            "provider":         user.get("oauth_provider"),
            "provider_user_id": user.get("oauth_provider_user_id"),
        },
    }


# ── userinfo 정규화 ───────────────────────────────────────────────────
def _normalize_userinfo(provider: str, raw: dict) -> dict:
    """provider별 userinfo를 표준 형식으로 변환."""
    if provider == "naver":
        # 응답: { resultcode, message, response: { id, email, name, nickname, mobile, ... } }
        r = raw.get("response", {})
        return {
            "provider_user_id": r.get("id", ""),
            "email":            r.get("email", ""),
            "name":             r.get("name", "") or r.get("nickname", ""),
            "phone":            (r.get("mobile", "") or "").replace("-", ""),
            "raw":              r,
        }
    elif provider == "kakao":
        # 응답: { id, kakao_account: { email, profile: {nickname}, phone_number, ... } }
        kakao_account = raw.get("kakao_account", {})
        profile_data  = kakao_account.get("profile", {})
        phone_raw     = kakao_account.get("phone_number", "")
        # 카카오 phone 형식: "+82 10-1234-5678" → "01012345678"
        phone_clean   = phone_raw.replace("+82 ", "0").replace("-", "").replace(" ", "") if phone_raw else ""
        return {
            "provider_user_id": str(raw.get("id", "")),
            "email":            kakao_account.get("email", ""),
            "name":             profile_data.get("nickname", ""),
            "phone":            phone_clean,
            "raw":              raw,
        }
    elif provider == "google":
        # 응답: { sub, email, name, given_name, family_name, picture, email_verified }
        return {
            "provider_user_id": raw.get("sub", ""),
            "email":            raw.get("email", ""),
            "name":             raw.get("name", ""),
            "phone":            "",  # Google은 phone 미제공
            "raw":              raw,
        }
    return {}


# ── 임시 토큰 헬퍼 ───────────────────────────────────────────────────────
def _issue_temp_register_token(provider: str, profile: dict) -> str:
    """OAuth 후 신규 회원가입 페이지로 보낼 때 임시 토큰 발급 (30분 유효)."""
    token = secrets.token_urlsafe(32)
    _TEMP_REGISTER_TOKENS[token] = {
        "provider":         provider,
        "provider_user_id": profile["provider_user_id"],
        "email":            profile.get("email", ""),
        "name":             profile.get("name", ""),
        "phone":            profile.get("phone", ""),
        "expires_at":       _now_ts() + 1800,
    }
    return token


def _consume_temp_register_token(token: str) -> Optional[dict]:
    data = _TEMP_REGISTER_TOKENS.pop(token, None)
    if not data:
        return None
    if data["expires_at"] < _now_ts():
        return None
    return data
