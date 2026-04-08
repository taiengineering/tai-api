"""
Firebase FCM 토큰 등록 / 푸시 테스트 라우터 — v1.0.0

API:
  POST /workers/fcm-token    FCM 토큰 등록 / 갱신
  POST /workers/push-test    프네 복다식 학니가 FCM 테스트
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

router = APIRouter(prefix="/workers", tags=["FCM"])

VERSION = "1.0.0"


# ── Pydantic 모델 ────────────────────────────────────────

class FcmTokenBody(BaseModel):
    fcm_token: str
    platform:  Optional[str] = None    # ios / android / web
    phone:     Optional[str] = None    # 토큰 소유자 전화번호 (없으면 헤더에서 유저 연결 불가)
    worker_id: Optional[str] = None    # worker_registry.id 직접 지정 시 연결


class PushTestBody(BaseModel):
    fcm_token: str
    title:     str = "TAI Safe 테스트"
    body:      str = "푸시 알림 테스트입니다."


# ── POST /workers/fcm-token ─────────────────────────────

@router.post("/fcm-token")
def register_fcm_token(body: FcmTokenBody):
    """
    FCM 토큰 등록 / 갱신.

    연결 우선순위:
    1. worker_id 직접 지정 시 해당 레코드 UPDATE
    2. phone 제공 시 worker_registry에서 phone 기준 조회
    3. 둘 다 없으면 404
    """
    supabase = get_supabase()

    # 대상 레코드 찾기
    if body.worker_id:
        chk = supabase.table("worker_registry").select("id") \
            .eq("id", body.worker_id).limit(1).execute()
        if not chk.data:
            raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")
        target_id = body.worker_id

    elif body.phone:
        phone_clean = body.phone.replace("-", "").replace(" ", "")
        chk = supabase.table("worker_registry").select("id") \
            .eq("phone", phone_clean).limit(1).execute()
        if not chk.data:
            raise HTTPException(
                status_code=404,
                detail=f"해당 전화번호로 등록된 작업자를 찾을 수 없습니다. ({phone_clean})"
            )
        target_id = chk.data[0]["id"]

    else:
        raise HTTPException(
            status_code=422,
            detail="worker_id 또는 phone 중 하나는 필수입니다."
        )

    # push_token + app_installed 갱신
    res = supabase.table("worker_registry").update({
        "push_token":    body.fcm_token,
        "app_installed": True,
    }).eq("id", target_id).execute()

    log.info(f"[FCM] 토큰 등록 worker_id={target_id} platform={body.platform}")

    return {
        "status":  "success",
        "message": "FCM 토큰이 등록되었습니다.",
        "data":    {"worker_id": target_id},
    }


# ── POST /workers/push-test ──────────────────────────────

@router.post("/push-test")
def push_test(body: PushTestBody):
    """
    FCM 단건 테스트 발송 (관리용).
    """
    try:
        from utils.fcm_utils import send_push
        message_id = send_push(
            fcm_token=body.fcm_token,
            title=body.title,
            body=body.body,
            data={"type": "test"},
        )
        return {
            "status":     "success",
            "message":    "푸시 알림을 발송했습니다.",
            "message_id": message_id,
        }
    except Exception as e:
        log.error(f"[FCM] push-test 실패: {e}")
        raise HTTPException(status_code=502, detail=f"FCM 발송 실패: {e}")
