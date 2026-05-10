"""
OAuth 간편로그인/간편회원가입 라우터 — v1.1.0
지원: 네이버 / 카카오 / 구글

v1.1.0 변경:
- identity_verify_token 필수화 — 본인인증 없으면 가입 불가
- consume_verify_token() 호출하여 users.identity_* 필드 채움 (CI/이름/휴대폰/생년월일 등)
- 본인인증 이름/휴대폰을 OAuth 프로필 결과보다 우선 (명의 일치)

prefix: /auth/oauth (main.py에서 지정)
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
from routers.identity import consume_verify_token  # 본인인증 토큰 검증

log = logging.getLogger(__name__)
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
        "scope":         "",
    },
    "kakao": {
        "client_id":     os.getenv("KAKAO_REST_API_KEY",  ""),
        "client_secret": os.getenv("KAKAO_CLIENT_SECRET", ""),
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

_OAUTH_STATES: dict[str, dict] = {}
_TEMP_REGISTER_TOKENS: dict[str, dict] = {}


# ── 유틸 ───────────────────────────────────────────────────────
def _now_iso() -> str: return datetime.now(timezone.utc).isoformat()
def _now_ts() -> int:  return int(datetime.now(timezone.utc).timestamp())


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
    """TODO: utils/auth.py에서 JWT 발급 함수 재사용 (현재는 random token placeholder)"""
    return secrets.token_urlsafe(48)


# ── 1단계: OAuth 인증 시작 ───────────────────────────────────────────
@router.get("/{provider}")
def oauth_start(
    provider: str,
    redirect: Optional[str] = Query(None, description="로그인 후 돌아갈 프론트엔드 URL"),
):
    cfg   = _provider_config(provider)
    state = secrets.token_urlsafe(32)
    _OAUTH_STATES[state] = {
        "provider":   provider,
        "redirect":   redirect or OAUTH_FRONTEND_SUCCESS_URL,
        "expires_at": _now_ts() + 600,
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
    log.info(f"[OAUTH] {provider} start → {auth_url[:120]}...")
    return RedirectResponse(auth_url)


# ── 2단계: 콜백 ─────────────────────────────────────────────────────
@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    code:  Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    if error or not code:
        sep = "&" if "?" in OAUTH_FRONTEND_ERROR_URL else "?"
        return RedirectResponse(f"{OAUTH_FRONTEND_ERROR_URL}{sep}reason={error or 'no_code'}")

    state_data = _OAUTH_STATES.pop(state, None) if state else None
    if not state_data:
        return RedirectResponse(f"{OAUTH_FRONTEND_ERROR_URL}&reason=invalid_state")
    if state_data["expires_at"] < _now_ts():
        return RedirectResponse(f"{OAUTH_FRONTEND_ERROR_URL}&reason=expired_state")

    cfg = _provider_config(provider)

    async with httpx.AsyncClient(timeout=15.0) as client:
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
        access_token = token_res.json().get("access_token")
        if not access_token:
            return RedirectResponse(f"{OAUTH_FRONTEND_ERROR_URL}&reason=no_token")

        userinfo_res = await client.get(
            cfg["userinfo_url"],
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_res.status_code != 200:
            log.error(f"[OAUTH] {provider} userinfo error: {userinfo_res.text}")
            return RedirectResponse(f"{OAUTH_FRONTEND_ERROR_URL}&reason=userinfo_error")
        userinfo = userinfo_res.json()

    profile = _normalize_userinfo(provider, userinfo)
    if not profile.get("provider_user_id"):
        return RedirectResponse(f"{OAUTH_FRONTEND_ERROR_URL}&reason=no_user_id")

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
        # 기존 OAuth 사용자 — 즉시 로그인 (본인인증은 이미 가입 시 완료됨)
        user          = existing.data[0]
        session_token = _create_session_token(user["id"])
        sep = "&" if "?" in front_url else "?"
        return RedirectResponse(
            f"{front_url}{sep}oauth=success#token={session_token}&user_id={user['id']}"
        )

    # 신규 OAuth — 임시 토큰 발급 후 sign-up-oauth.html로 이동 (본인인증 필요)
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


# ── 3단계: 신규 OAuth 회원가입 완료 — 본인인증 필수 ─────────────────────
class OAuthRegisterBody(BaseModel):
    register_token:        str
    identity_verify_token: str   # ✅ v1.1.0: 필수 (본인인증 없으면 가입 불가)
    email:                 str
    agree_terms:           bool
    # name, phone은 본인인증 결과에서 가져오므로 클라이언트 입력값 무시 가능
    # (필요 시 입력함 모드에서 편집 허용 — 일단 존재하면 참고)
    name:                  Optional[str] = None
    phone:                 Optional[str] = None


@router.post("/register")
async def oauth_register(body: OAuthRegisterBody):
    """
    OAuth로 시작한 회원가입 완료 — 본인인증 필수.

    flow:
    1. OAuth 프로바이더에서 email/name 받음 (provider 단계)
    2. sign-up-oauth.html에서 본인인증 수행 (identity 모듈 → verify_token)
    3. 이 엔드포인트로 register_token + verify_token + email + agree_terms POST
    4. 서버에서 둘 다 검증 후 users 테이블에 삽입 (identity_* 최종 값 주입)
    """
    if not body.agree_terms:
        raise HTTPException(status_code=400, detail="이용약관·개인정보처리방침에 동의해 주세요.")

    # 1. register_token 검증 (provider 정보 복원)
    profile = _consume_temp_register_token(body.register_token)
    if not profile:
        raise HTTPException(status_code=400, detail="OAuth 세션이 만료되었습니다. 다시 시도해 주세요.")

    # 2. 본인인증 토큰 검증 (필수)
    verify_data = consume_verify_token(body.identity_verify_token)
    if not verify_data:
        raise HTTPException(status_code=400, detail="본인인증 토큰이 유효하지 않거나 만료되었습니다. 재인증해 주세요.")

    provider         = profile["provider"]
    provider_user_id = profile["provider_user_id"]
    supabase         = get_supabase()
    email            = (body.email or "").strip().lower()

    # 3. CI 중복 체크 (본인인증 명의가 이미 가입되어 있으면 차단)
    ci_check = (
        supabase.table("users")
        .select("id, email, oauth_provider")
        .eq("identity_ci", verify_data["ci"])
        .limit(1)
        .execute()
    )
    if ci_check.data:
        existing = ci_check.data[0]
        login_hint = (
            f"{existing['oauth_provider']}로 간편 로그인"
            if existing.get("oauth_provider")
            else "이메일/비밀번호로 로그인"
        )
        raise HTTPException(
            status_code=409,
            detail=f"이미 가입된 명의입니다. {login_hint}을 이용해 주세요.",
        )

    # 4. 이메일 중복 체크
    existing_email = (
        supabase.table("users")
        .select("id, oauth_provider, identity_ci")
        .eq("email", email)
        .limit(1)
        .execute()
    )

    now = _now_iso()
    identity_fields = {
        "identity_ci":          verify_data["ci"],
        "identity_di":          verify_data["di"],
        "identity_name":        verify_data["name"],
        "identity_birth":       verify_data["birth"],
        "identity_gender":      verify_data["gender"],
        "identity_nation":      verify_data["nation"],
        "identity_phone":       verify_data["phone"],
        "identity_carrier":     verify_data["carrier"],
        "identity_method":      verify_data["method"],
        "identity_verified":    True,
        "identity_verified_at": now,
    }

    if existing_email.data:
        existing = existing_email.data[0]
        if existing.get("oauth_provider") and existing["oauth_provider"] != provider:
            raise HTTPException(
                status_code=409,
                detail=f"이미 {existing['oauth_provider']}로 가입된 이메일입니다.",
            )
        # 기존 일반 가입자 — OAuth + 본인인증 연동
        supabase.table("users").update({
            "oauth_provider":         provider,
            "oauth_provider_user_id": provider_user_id,
            **identity_fields,
            "updated_at":             now,
        }).eq("id", existing["id"]).execute()
        user_id = existing["id"]
    else:
        # 신규 가입 — 본인인증 이름/휴대폰을 OAuth 프로필보다 우선
        new_user = {
            "email":                  email,
            "name":                   verify_data["name"],            # 본인인증 이름 우선
            "phone":                  verify_data["phone"].replace("-", ""),
            "password_hash":          None,                            # OAuth 사용자는 비밀번호 없음
            "oauth_provider":         provider,
            "oauth_provider_user_id": provider_user_id,
            **identity_fields,
            "created_at":             now,
            "updated_at":             now,
        }
        ins = supabase.table("users").insert(new_user).execute()
        user_id = ins.data[0]["id"] if ins.data else None
        if not user_id:
            raise HTTPException(status_code=500, detail="회원가입에 실패했습니다.")

    session_token = _create_session_token(user_id)
    log.info(f"[OAUTH] register 완료 — user_id={user_id}, provider={provider}, ci={verify_data['ci'][:8]}...")
    return {
        "status": "success",
        "data": {
            "access_token": session_token,
            "user_id":      user_id,
            "provider":     provider,
            "name":         verify_data["name"],
        },
    }


# ── 연동 관리 ───────────────────────────────────────────────────────
class OAuthLinkBody(BaseModel):
    user_id:  str
    provider: str
    code:     str


@router.post("/link")
async def oauth_link(body: OAuthLinkBody):
    """기존 계정에 OAuth 연동 추가 (마이페이지)."""
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
    dup = (
        supabase.table("users").select("id")
        .eq("oauth_provider", body.provider)
        .eq("oauth_provider_user_id", profile["provider_user_id"])
        .neq("id", body.user_id).limit(1).execute()
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
    """OAuth 연동 해제 — 비밀번호 설정되어 있어야 해제 가능."""
    supabase = get_supabase()
    res = supabase.table("users").select("id, password_hash").eq("id", user_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다.")
    if not res.data[0].get("password_hash"):
        raise HTTPException(
            status_code=400,
            detail="비밀번호를 먼저 설정해 주세요.",
        )
    supabase.table("users").update({
        "oauth_provider":         None,
        "oauth_provider_user_id": None,
        "updated_at":             _now_iso(),
    }).eq("id", user_id).execute()
    return {"status": "success"}


@router.get("/links/{user_id}")
def get_oauth_links(user_id: str):
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
    if provider == "naver":
        r = raw.get("response", {})
        return {
            "provider_user_id": r.get("id", ""),
            "email":            r.get("email", ""),
            "name":             r.get("name", "") or r.get("nickname", ""),
            "phone":            (r.get("mobile", "") or "").replace("-", ""),
            "raw":              r,
        }
    elif provider == "kakao":
        kakao_account = raw.get("kakao_account", {})
        profile_data  = kakao_account.get("profile", {})
        phone_raw     = kakao_account.get("phone_number", "")
        phone_clean   = phone_raw.replace("+82 ", "0").replace("-", "").replace(" ", "") if phone_raw else ""
        return {
            "provider_user_id": str(raw.get("id", "")),
            "email":            kakao_account.get("email", ""),
            "name":             profile_data.get("nickname", ""),
            "phone":            phone_clean,
            "raw":              raw,
        }
    elif provider == "google":
        return {
            "provider_user_id": raw.get("sub", ""),
            "email":            raw.get("email", ""),
            "name":             raw.get("name", ""),
            "phone":            "",
            "raw":              raw,
        }
    return {}


# ── 임시 토큰 헬퍼 ───────────────────────────────────────────────────────
def _issue_temp_register_token(provider: str, profile: dict) -> str:
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
