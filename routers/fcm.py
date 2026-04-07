"""
Firebase FCM 토큰 등록 및 테스트 라우터 — v1.0.0

API:
  POST /workers/fcm-token    FCM 토큰 등록 (worker_registry 업데이트)
  POST /workers/push-test    FCM 단건 테스트 발송
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

router = APIRouter(prefix="/workers", tags=["FCM"])

VERSION = "1.0.0"


# ── Pydantic 모델 ─────────────────────────────────────────

class FcmTokenBody(BaseModel):
    fcm_token: str
    platform:  Optional[str] = None   # android | ios
    phone:     Optional[str] = None   # worker 조회용 (worker_id 없을 때)
    worker_id: Optional[str] = None   # 직접 worker_id 전달 시 사용


class PushTestBody(BaseModel):
    fcm_token: str
    title:     str
    body:      str
    data:      Optional[dict] = None


# ── 1. POST /workers/fcm-token ─────────────────────────

@router.post("/fcm-token")
def register_fcm_token(body: FcmTokenBody):
    """
    FCM 토큰 등록.
    worker_id 또는 phone으로 worker_registry 레코드 조회 후
    push_token 및 app_installed=True 업데이트.
    """
    supabase = get_supabase()

    worker_id = body.worker_id

    # worker_id 없으면 phone으로 추적
    if not worker_id and body.phone:
        wres = supabase.table("worker_registry").select("id") \
            .eq("phone", body.phone).limit(1).execute()
        if wres.data:
            worker_id = wres.data[0]["id"]

    if not worker_id:
        raise HTTPException(
            status_code=404,
            detail="worker_id 또는 phone으로 worker를 찾을 수 없습니다."
        )

    payload = {
        "push_token":    body.fcm_token,
        "app_installed": True,
    }

    res = supabase.table("worker_registry").update(payload) \
        .eq("id", worker_id).execute()

    if not res.data:
        raise HTTPException(status_code=500, detail="FCM 토큰 등록 실패")

    log.info(f"[FCM] 토큰 등록 worker_id={worker_id} platform={body.platform}")
    return {
        "status":    "success",
        "message":   "FCM 토큰이 등록되었습니다.",
        "worker_id": worker_id,
    }


# ── 2. POST /workers/push-test ──────────────────────────

@router.post("/push-test")
def push_test(body: PushTestBody):
    """
    FCM 단건 테스트 발송.
    """
    try:
        from utils.fcm_utils import send_push
        message_id = send_push(
            fcm_token=body.fcm_token,
            title=body.title,
            body=body.body,
            data=body.data,
        )
        return {"status": "success", "message_id": message_id}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"FCM 발송 실패: {e}")
