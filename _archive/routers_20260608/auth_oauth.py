"""
POST /auth/oauth-login — Supabase OAuth 세션 토큰으로 public.users 동기화.

프론트엔드가 signInWithOAuth 이후 받은 access_token을 전달하면,
토큰 검증 → 이메일로 users 조회/생성 → /auth/login 과 동일 형식으로 응답합니다.
"""
from __future__ import annotations

import base64
import json
import logging
import random
import re
import string
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth-oauth"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_phone(phone: str) -> str:
    return re.sub(r"[^0-9]", "", phone or "")


def _expires_in_from_jwt(access_token: str) -> int:
    try:
        parts = access_token.split(".")
        if len(parts) < 2:
            return 3600
        payload_part = parts[1]
        padding = "=" * (-len(payload_part) % 4)
        decoded = base64.urlsafe_b64decode((payload_part + padding).encode("ascii"))
        payload = json.loads(decoded)
        exp = payload.get("exp")
        if isinstance(exp, (int, float)):
            return max(0, int(exp - time.time()))
    except Exception:
        pass
    return 3600


_USER_FIELDS = (
    "id, email, name, phone, role_code, company_id, factory_id, status_code, profile_image_url, auth_id"
)


class OAuthLoginRequest(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    provider: str = Field(default="kakao", description="kakao, naver, google")


def _build_login_response(
    *,
    access_token: str,
    refresh_token: str,
    expires_in: int,
    user: dict,
) -> dict:
    return {
        "status": "success",
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "user": {
                "id": user["id"],
                "phone": user.get("phone"),
                "email": user.get("email"),
                "name": user.get("name") or "",
                "role_code": user.get("role_code"),
                "company_id": user.get("company_id"),
                "factory_id": user.get("factory_id"),
                "status_code": user.get("status_code"),
                "profile_image_url": user.get("profile_image_url"),
            },
        },
    }


@router.post("/oauth-login")
def oauth_login(body: OAuthLoginRequest):
    sb = get_supabase()

    try:
        user_response = sb.auth.get_user(body.access_token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
        auth_user = user_response.user
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("oauth-login: 토큰 검증 실패 — %s", e)
        raise HTTPException(status_code=401, detail="토큰 검증에 실패했습니다.") from e

    auth_uid = str(auth_user.id)
    email = (auth_user.email or "").strip()
    if not email:
        raise HTTPException(
            status_code=400,
            detail="이메일 정보가 없습니다. 소셜 계정에 이메일이 등록되어 있는지 확인해 주세요.",
        )

    meta = auth_user.user_metadata or {}
    name = (
        meta.get("name")
        or meta.get("full_name")
        or meta.get("nickname")
        or meta.get("preferred_username")
        or ""
    )
    provider = (body.provider or "kakao").lower()
    refresh = body.refresh_token if body.refresh_token is not None else ""
    expires_in = _expires_in_from_jwt(body.access_token)

    try:
        rows = sb.table("users").select(_USER_FIELDS).eq("email", email).limit(1).execute()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"사용자 조회 중 오류가 발생했습니다: {str(e)}",
        ) from e

    now = _now_iso()

    if rows.data:
        user = rows.data[0]
        status = user.get("status_code", "ACTIVE")
        if status in ("SUSPENDED", "DELETED", "INACTIVE"):
            raise HTTPException(status_code=403, detail=f"접근 불가 계정입니다 ({status})")

        update_payload: dict = {"last_login_at": now, "updated_at": now}
        if user.get("auth_id") != auth_uid:
            update_payload["auth_id"] = auth_uid
        if not user.get("oauth_provider"):
            update_payload["oauth_provider"] = provider
            update_payload["oauth_linked_at"] = now

        try:
            sb.table("users").update(update_payload).eq("id", user["id"]).execute()
        except Exception:
            pass

        refreshed = (
            sb.table("users")
            .select(_USER_FIELDS)
            .eq("id", user["id"])
            .limit(1)
            .execute()
        )
        user = refreshed.data[0] if refreshed.data else user

        return _build_login_response(
            access_token=body.access_token,
            refresh_token=refresh,
            expires_in=expires_in,
            user=user,
        )

    # 신규 — Supabase Auth 에는 이미 OAuth 사용자가 있으므로 public.users 만 생성
    phone_guess = _normalize_phone(
        str(meta.get("phone") or meta.get("phone_number") or "")
    )
    user_code = (
        "USR-"
        + datetime.now(timezone.utc).strftime("%Y%m%d")
        + "-"
        + "".join(random.choices(string.digits, k=4))
    )
    display_name = name.strip() if name else email.split("@")[0]

    insert_row: dict = {
        "auth_id": auth_uid,
        "email": email,
        "name": display_name,
        "username": phone_guess or email.split("@")[0],
        "role_code": "010",
        "oauth_provider": provider,
        "oauth_linked_at": now,
        "user_code": user_code,
        "status_code": "ACTIVE",
        "is_active": True,
        "allow_push": True,
        "allow_sms": True,
        "allow_email": True,
        "allow_kakao": True,
        "created_at": now,
        "updated_at": now,
    }
    if phone_guess:
        insert_row["phone"] = phone_guess

    try:
        ins = sb.table("users").insert(insert_row).execute()
    except Exception as e:
        logger.exception("oauth-login: 사용자 생성 실패")
        raise HTTPException(
            status_code=500,
            detail=f"사용자 생성에 실패했습니다: {str(e)}",
        ) from e

    if not ins.data:
        raise HTTPException(status_code=500, detail="사용자 생성에 실패했습니다.")

    created = ins.data[0]
    created_id = created.get("id")
    if not created_id:
        raise HTTPException(status_code=500, detail="사용자 생성에 실패했습니다.")

    out = (
        sb.table("users").select(_USER_FIELDS).eq("id", created_id).limit(1).execute()
    )
    user = out.data[0] if out.data else created

    return _build_login_response(
        access_token=body.access_token,
        refresh_token=refresh,
        expires_in=expires_in,
        user=user,
    )
