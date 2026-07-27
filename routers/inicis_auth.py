"""
inicis_auth.py — KG이니시스 통합인증서비스(SA) 연동  v1.1.0

v1.1.0 (2026-05-28):
  [FIX] callback/success, callback/fail: GET → POST 변경
        이니시스가 콜백을 POST form data로 전송

API:
  POST /auth/inicis/request           인증요청 파라미터 생성
  POST /auth/inicis/callback/success  성공 콜백 + S2S 결과조회 + DB 저장
  POST /auth/inicis/callback/fail     실패 콜백
  GET  /auth/inicis/result/{mtx_id}   인증결과 조회
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from html import escape
from typing import Any, Optional
from urllib.parse import unquote

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from db.supabase_client import get_supabase
from services.diagnosis_integrated_svc import sync_diagnosis_auth_log_from_inicis
from utils.seed_cipher import seed_cbc_decrypt

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/inicis", tags=["inicis_auth"])

SA_MID = os.getenv("INICIS_SA_MID", "INIiasTest")
SA_API_KEY = os.getenv("INICIS_SA_API_KEY", "TGdxb2l3enJDWFRTbTgvREU3MGYwUT09")
SA_SEED_IV = os.getenv("INICIS_SA_SEED_IV", "SASKGINICIS00000")
SA_MODE = os.getenv("INICIS_SA_MODE", "test")

SA_AUTH_URL = "https://sa.inicis.com/auth"
SA_ID_AUTH_URL = "https://sa.inicis.com/id/auth"

BASE_URL = os.getenv("API_BASE_URL", "https://api.taieng.co.kr").rstrip("/")
SUCCESS_URL = f"{BASE_URL}/auth/inicis/callback/success"
FAIL_URL = f"{BASE_URL}/auth/inicis/callback/fail"

def _generate_mtx_id() -> str:
    """가맹점 트랜잭션 ID (20바이트 이내)."""
    return ("TAI" + datetime.now().strftime("%y%m%d%H%M%S") + uuid.uuid4().hex[:5]).upper()[:20]


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _seed_key_bytes() -> bytes:
    raw = base64.b64decode(SA_API_KEY)
    if len(raw) == 16:
        return raw
    try:
        inner = base64.b64decode(raw)
        if len(inner) == 16:
            return inner
    except Exception:
        pass
    if len(raw) >= 16:
        return raw[:16]
    raise ValueError("INICIS_SA_API_KEY must decode to a 16-byte SEED key")


def _seed_decrypt(encrypted_b64: str) -> str:
    key = _seed_key_bytes()
    iv = SA_SEED_IV.encode("utf-8")
    if len(iv) != 16:
        raise ValueError("INICIS_SA_SEED_IV must be 16 bytes")
    encrypted = base64.b64decode(encrypted_b64)
    decrypted = seed_cbc_decrypt(key, iv, encrypted)
    for _enc in ("utf-8", "cp949"):
        try:
            return decrypted.decode(_enc)
        except UnicodeDecodeError:
            continue
    return decrypted.decode("utf-8", errors="replace")


def _is_allowed_auth_url(url: str) -> bool:
    if not url:
        return False
    try:
        from urllib.parse import urlparse

        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host.endswith("inicis.com")


class AuthRequestBody(BaseModel):
    svc_code: str = Field(default="01", description="01:간편인증, 02:전자서명, 03:본인확인")
    fixed_user: bool = False
    user_name: Optional[str] = None
    user_phone: Optional[str] = None
    user_birth: Optional[str] = None
    identifier: Optional[str] = None
    user_id: Optional[str] = None
    company_id: Optional[str] = None


@router.post("/request")
def create_auth_request(body: AuthRequestBody):
    """STEP1 — 프론트가 팝업 폼으로 제출할 파라미터 생성."""
    if body.svc_code not in ("01", "02", "03"):
        raise HTTPException(400, "svc_code는 01, 02, 03 중 하나여야 합니다.")

    mtx_id = _generate_mtx_id()
    auth_hash = _sha256(SA_MID + mtx_id + SA_API_KEY)
    form_action = SA_ID_AUTH_URL if body.svc_code == "03" else SA_AUTH_URL

    params: dict[str, str] = {
        "mid": SA_MID,
        "reqSvcCd": body.svc_code,
        "mTxId": mtx_id,
        "successUrl": SUCCESS_URL,
        "failUrl": FAIL_URL,
        "authHash": auth_hash,
        "flgFixedUser": "Y" if body.fixed_user else "N",
        "reservedMsg": "isUseToken=Y",
    }

    if body.fixed_user:
        if not all([body.user_name, body.user_phone, body.user_birth]):
            raise HTTPException(400, "fixed_user=true 시 user_name, user_phone, user_birth 필수")
        params["userName"] = body.user_name
        params["userPhone"] = body.user_phone
        params["userBirth"] = body.user_birth
        params["userHash"] = _sha256(
            body.user_name + SA_MID + body.user_phone + mtx_id + body.user_birth + body.svc_code
        )

    if body.svc_code == "02" and body.identifier:
        params["identifier"] = body.identifier

    row: dict[str, Any] = {
        "mtx_id": mtx_id,
        "svc_code": body.svc_code,
        "status": "REQUESTED",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if body.user_id:
        row["user_id"] = body.user_id
    if body.company_id:
        row["company_id"] = body.company_id

    try:
        get_supabase().table("inicis_auth_requests").insert(row).execute()
    except Exception as e:
        log.exception("[inicis_auth] insert failed mtx_id=%s", mtx_id)
        raise HTTPException(500, f"인증 요청 저장 실패: {e}") from e

    return {
        "status": "success",
        "data": {
            "form_action": form_action,
            "form_params": params,
            "mtx_id": mtx_id,
            "popup_width": 400,
            "popup_height": 640,
            "mode": SA_MODE,
        },
    }


@router.post("/callback/success")
async def callback_success(request: Request):
    """STEP2 콜백 (POST form data) → STEP3 S2S 결과조회 → STEP4 복호화·저장."""
    # 이니시스는 POST form data로 콜백 전송
    form = await request.form()
    params = dict(form)

    result_code = str(params.get("resultCode", ""))
    result_msg = unquote(str(params.get("resultMsg", "") or ""))
    auth_request_url = str(params.get("authRequestUrl", ""))
    tx_id = str(params.get("txId", ""))

    if result_code != "0000":
        return HTMLResponse(_popup_result_html(False, result_msg or "인증 실패"))

    if not _is_allowed_auth_url(auth_request_url):
        return HTMLResponse(_popup_result_html(False, "유효하지 않은 결과조회 URL"))

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                auth_request_url,
                json={"mid": SA_MID, "txId": tx_id},
                headers={"Content-Type": "application/json;charset=utf-8"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        log.exception("[inicis_auth] S2S result fetch failed tx_id=%s", tx_id)
        return HTMLResponse(_popup_result_html(False, f"결과조회 실패: {e}"))

    if data.get("resultCode") != "0000":
        return HTMLResponse(_popup_result_html(False, data.get("resultMsg", "인증 실패")))

    mtx_id = data.get("mTxId", "")
    svc_cd = data.get("svcCd", "")

    try:
        user_name = _seed_decrypt(data["userName"]) if data.get("userName") else None
        user_phone = _seed_decrypt(data["userPhone"]) if data.get("userPhone") else None
        user_birthday = _seed_decrypt(data["userBirthday"]) if data.get("userBirthday") else None
        user_ci = _seed_decrypt(data["userCi"]) if data.get("userCi") else None
        user_di = _seed_decrypt(data["userDi"]) if data.get("userDi") else None
        user_gender = _seed_decrypt(data["userGender"]) if data.get("userGender") else None
    except Exception as e:
        log.exception("[inicis_auth] SEED decrypt failed mtx_id=%s", mtx_id)
        return HTMLResponse(_popup_result_html(False, f"복호화 실패: {e}"))

    try:
        get_supabase().table("inicis_auth_requests").update({
            "status": "SUCCESS",
            "tx_id": tx_id,
            "svc_cd": svc_cd,
            "provider_dev_cd": data.get("providerDevCd"),
            "user_name": user_name,
            "user_phone": user_phone,
            "user_birthday": user_birthday,
            "user_ci": user_ci,
            "user_di": user_di,
            "user_gender": user_gender,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }).eq("mtx_id", mtx_id).execute()
    except Exception as e:
        log.exception("[inicis_auth] update failed mtx_id=%s", mtx_id)
        return HTMLResponse(_popup_result_html(False, f"저장 실패: {e}"))

    try:
        sync_diagnosis_auth_log_from_inicis(get_supabase(), mtx_id)
    except Exception as e:
        log.warning("[inicis_auth] diagnosis_auth_log sync mtx_id=%s: %s", mtx_id, e)

    return HTMLResponse(_popup_result_html(True, "본인인증이 완료되었습니다.", mtx_id))


@router.post("/callback/fail")
async def callback_fail(request: Request):
    """실패 콜백 (POST form data)."""
    form = await request.form()
    params = dict(form)

    result_msg = unquote(str(params.get("resultMsg", "") or "인증 실패"))
    mtx_id = str(params.get("mTxId", ""))

    if mtx_id:
        try:
            get_supabase().table("inicis_auth_requests").update({
                "status": "FAILED",
                "result_msg": result_msg,
            }).eq("mtx_id", mtx_id).execute()
        except Exception as e:
            log.warning("[inicis_auth] fail update mtx_id=%s: %s", mtx_id, e)

    return HTMLResponse(_popup_result_html(False, result_msg))


@router.get("/result/{mtx_id}")
def get_auth_result(mtx_id: str):
    """프론트 — 인증 완료 후 결과 조회 (민감 필드 CI/DI 제외)."""
    result = (
        get_supabase()
        .table("inicis_auth_requests")
        .select(
            "mtx_id, status, user_name, user_phone, user_birthday, svc_cd, verified_at, result_msg"
        )
        .eq("mtx_id", mtx_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(404, "인증 요청을 찾을 수 없습니다.")

    row = result.data[0]
    if row.get("status") == "SUCCESS":
        try:
            sync_diagnosis_auth_log_from_inicis(get_supabase(), mtx_id)
        except Exception as e:
            log.warning("[inicis_auth] diagnosis sync on result mtx_id=%s: %s", mtx_id, e)

    return {"status": "success", "data": row}


def _popup_result_html(success: bool, message: str, mtx_id: str = "") -> str:
    payload = json.dumps({
        "type": "INICIS_AUTH_RESULT",
        "success": success,
        "message": message,
        "mtxId": mtx_id,
    }, ensure_ascii=False)
    title = "인증 완료" if success else "인증 실패"
    icon = "✅" if success else "❌"
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>본인인증 결과</title></head>
<body>
<script>
try {{
  if (window.opener) window.opener.postMessage({payload}, '*');
}} catch (e) {{}}
setTimeout(function() {{ window.close(); }}, 1500);
</script>
<div style="text-align:center;padding:40px;font-family:sans-serif;">
  <h2>{icon} {escape(title)}</h2>
  <p>{escape(message)}</p>
  <p style="color:#999;font-size:13px;">이 창은 자동으로 닫힙니다.</p>
</div>
</body></html>"""
