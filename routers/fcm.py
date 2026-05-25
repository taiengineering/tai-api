"""
Firebase FCM 토큰 등록 / 푸시 발송 라우터 — v3.0.0 (Capability Consume)

Wrapper: transport only (request parse, auth, token resolve → adapter, response format)
Capability: capabilities.fcm.core.send_push (firebase_admin, framework/DB 모름)
Adapter: capabilities.fcm.adapters (DB token lookup/save)

v3.0.0 (2026-05-25): Phase 2 capability consume — inline 제거, capabilities.fcm import
v2.0.0 (2026-05-25): Phase 2 thin wrapper migration
v1.1.0: worker_registry + users fallback, send-push, push-test

API:
  POST /workers/fcm-token    FCM 토큰 등록 / 갱신
  POST /workers/send-push    전화번호로 알림 발송
  POST /workers/push-test    토큰 직접 지정 테스트
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from capabilities.fcm.core import send_push as _cap_send_push
from capabilities.fcm.adapters import (
    find_token_by_phone as _adapter_find_token,
    save_token_worker as _adapter_save_worker,
    save_token_by_phone as _adapter_save_phone,
)
from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

router = APIRouter(prefix="/workers", tags=["FCM"])

VERSION = "3.0.0"


# ═══════════════════════════════════════════════════════
# Pydantic 모델
# ═══════════════════════════════════════════════════════

class FcmTokenBody(BaseModel):
    fcm_token: str
    platform:  Optional[str] = None
    phone:     Optional[str] = None
    worker_id: Optional[str] = None

class SendPushBody(BaseModel):
    phone:    str
    title:    str = "TAI Safe 점검 알림"
    body:     str = "배정된 점검이 있습니다. 확인해주세요."
    url:      Optional[str] = None
    type:     Optional[str] = "inspection"

class PushTestBody(BaseModel):
    fcm_token: str
    title:     str = "TAI Safe 테스트"
    body:      str = "푸시 알림 테스트입니다."


# ═══════════════════════════════════════════════════════
# Wrapper (transport only)
# ═══════════════════════════════════════════════════════

def _optional_fcm_auth(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """Authorization 검증 (선택). wrapper 전용."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.replace("Bearer ", "")
    supabase = get_supabase()
    try:
        ur = supabase.auth.get_user(token)
        if not ur or not ur.user:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="토큰 검증 실패")
    return {"auth_id": str(ur.user.id)}


@router.post("/fcm-token")
def register_fcm_token(body: FcmTokenBody, _auth: Optional[dict] = Depends(_optional_fcm_auth)):
    """FCM 토큰 등록/갱신. wrapper → adapter 호출. API 응답 100% 기존 호환."""
    supabase = get_supabase()

    # ① worker_id 직접 지정 → adapter
    if body.worker_id:
        ok = _adapter_save_worker(supabase, body.worker_id, body.fcm_token)
        if not ok:
            raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")
        log.info(f"[FCM] 토큰 등록 worker_id={body.worker_id}")
        return {"status": "success", "message": "FCM 토큰이 등록됐습니다.", "table": "worker_registry"}

    # ② phone → adapter
    clean_phone = (body.phone or "").replace("-", "").replace(" ", "")
    if clean_phone:
        table = _adapter_save_phone(supabase, clean_phone, body.fcm_token, body.platform or "web")
        if table:
            log.info(f"[FCM] 토큰 등록 ({table}) phone={clean_phone}")
            return {"status": "success", "message": "FCM 토큰이 등록됐습니다.", "table": table}

    raise HTTPException(status_code=422, detail="worker_id 또는 phone 중 하나는 필수입니다.")


@router.post("/send-push")
def send_push_by_phone(body: SendPushBody):
    """전화번호로 FCM 발송. wrapper → adapter(token resolve) → capability(push send)."""
    supabase = get_supabase()

    # Adapter: token resolve
    token = _adapter_find_token(supabase, body.phone)
    if not token:
        raise HTTPException(status_code=404, detail=f"해당 번호의 FCM 토큰이 없습니다. 앱에서 알림을 먼저 허용해주세요. ({body.phone})")

    # Capability: push dispatch
    try:
        data = {"type": body.type or "inspection"}
        if body.url:
            data["url"] = body.url
        message_id = _cap_send_push(fcm_token=token, title=body.title, body=body.body, data=data)
        log.info(f"[FCM] 발송 완료 phone={body.phone} message_id={message_id}")
        return {"status": "success", "message": "알림을 발송했습니다.", "phone": body.phone, "message_id": message_id}
    except Exception as e:
        log.error(f"[FCM] 발송 실패 phone={body.phone}: {e}")
        raise HTTPException(status_code=502, detail=f"FCM 발송 실패: {e}")


@router.post("/push-test")
def push_test(body: PushTestBody):
    """FCM 단건 테스트. wrapper → capability 호출."""
    try:
        message_id = _cap_send_push(fcm_token=body.fcm_token, title=body.title, body=body.body, data={"type": "test"})
        return {"status": "success", "message": "푸시 알림을 발송했습니다.", "message_id": message_id}
    except Exception as e:
        log.error(f"[FCM] push-test 실패: {e}")
        raise HTTPException(status_code=502, detail=f"FCM 발송 실패: {e}")
