"""
Firebase FCM 토큰 등록 / 푸시 발송 라우터 — v1.1.0

v1.1.0:
  - FCM 토큰 등록: worker_registry 없으면 users 테이블로 fallback
  - POST /workers/send-push  전화번호로 직접 알림 발송
  - POST /workers/push-test  토큰 직접 지정 테스트 (기존 유지)

API:
  POST /workers/fcm-token    FCM 토큰 등록 / 갱신
  POST /workers/send-push    전화번호로 알림 발송
  POST /workers/push-test    토큰 직접 지정 테스트
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

router = APIRouter(prefix="/workers", tags=["FCM"])

VERSION = "1.1.0"


# ── Pydantic 모델 ────────────────────────────────────────

class FcmTokenBody(BaseModel):
    fcm_token: str
    platform:  Optional[str] = None   # ios / android / web
    phone:     Optional[str] = None
    worker_id: Optional[str] = None   # worker_registry.id


class SendPushBody(BaseModel):
    phone:    str
    title:    str = "TAI Safe 점검 알림"
    body:     str = "배정된 점검이 있습니다. 확인해주세요."
    url:      Optional[str] = None    # 클릭 시 이동할 URL
    type:     Optional[str] = "inspection"


class PushTestBody(BaseModel):
    fcm_token: str
    title:     str = "TAI Safe 테스트"
    body:      str = "푸시 알림 테스트입니다."


# ── 공통: 전화번호로 FCM 토큰 조회 ──────────────────────

def _find_token_by_phone(supabase, phone: str) -> Optional[str]:
    """
    전화번호로 FCM 토큰 조회.
    1. worker_registry.push_token
    2. users.push_token
    """
    clean = phone.replace("-", "").replace(" ", "")

    # worker_registry 먼저
    wr = supabase.table("worker_registry").select("push_token") \
        .eq("phone", clean).limit(1).execute()
    if wr.data and wr.data[0].get("push_token"):
        return wr.data[0]["push_token"]

    # users 테이블 fallback
    u = supabase.table("users").select("push_token") \
        .eq("phone", clean).limit(1).execute()
    if not u.data:
        u = supabase.table("users").select("push_token") \
            .eq("phone", f"{clean[:3]}-{clean[3:7]}-{clean[7:]}").limit(1).execute()
    if u.data and u.data[0].get("push_token"):
        return u.data[0]["push_token"]

    return None


# ── POST /workers/fcm-token ─────────────────────────────

def _optional_fcm_auth(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """Authorization이 있으면 검증, 없으면 None (하위호환)."""
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
def register_fcm_token(
    body: FcmTokenBody,
    _auth: Optional[dict] = Depends(_optional_fcm_auth),
):
    """
    FCM 토큰 등록 / 갱신. v1.2.0: Authorization 검증 추가 (Optional).
    1. worker_id 직접 지정 → worker_registry UPDATE
    2. phone → worker_registry 검색 → 없으면 users 검색
    3. 모두 없으면 422
    """
    supabase = get_supabase()
    clean_phone = (body.phone or "").replace("-", "").replace(" ", "")

    # ① worker_id 직접 지정
    if body.worker_id:
        chk = supabase.table("worker_registry").select("id") \
            .eq("id", body.worker_id).limit(1).execute()
        if not chk.data:
            raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")
        supabase.table("worker_registry").update({
            "push_token": body.fcm_token, "app_installed": True,
        }).eq("id", body.worker_id).execute()
        log.info(f"[FCM] 토큰 등록 worker_id={body.worker_id}")
        return {"status": "success", "message": "FCM 토큰이 등록됐습니다.", "table": "worker_registry"}

    # ② phone → worker_registry
    if clean_phone:
        wr = supabase.table("worker_registry").select("id") \
            .eq("phone", clean_phone).limit(1).execute()
        if wr.data:
            supabase.table("worker_registry").update({
                "push_token": body.fcm_token, "app_installed": True,
            }).eq("id", wr.data[0]["id"]).execute()
            log.info(f"[FCM] 토큰 등록 (worker) phone={clean_phone}")
            return {"status": "success", "message": "FCM 토큰이 등록됐습니다.", "table": "worker_registry"}

        # ③ phone → users 테이블 fallback
        u = supabase.table("users").select("id").eq("phone", clean_phone).limit(1).execute()
        if not u.data:
            # 하이픈 포맷으로도 시도
            fmt = f"{clean_phone[:3]}-{clean_phone[3:7]}-{clean_phone[7:]}"
            u = supabase.table("users").select("id").eq("phone", fmt).limit(1).execute()

        if u.data:
            supabase.table("users").update({
                "push_token": body.fcm_token,
                "push_platform": body.platform or "web",
            }).eq("id", u.data[0]["id"]).execute()
            log.info(f"[FCM] 토큰 등록 (user) phone={clean_phone}")
            return {"status": "success", "message": "FCM 토큰이 등록됐습니다.", "table": "users"}

    raise HTTPException(status_code=422, detail="worker_id 또는 phone 중 하나는 필수입니다.")


# ── POST /workers/send-push ──────────────────────────────

@router.post("/send-push")
def send_push_by_phone(body: SendPushBody):
    """
    전화번호로 FCM 알림 발송.
    worker_registry → users 순서로 토큰 조회 후 발송.
    """
    supabase = get_supabase()

    token = _find_token_by_phone(supabase, body.phone)
    if not token:
        raise HTTPException(
            status_code=404,
            detail=f"해당 번호의 FCM 토큰이 없습니다. 앱에서 알림을 먼저 허용해주세요. ({body.phone})"
        )

    try:
        from utils.fcm_utils import send_push
        data = {"type": body.type or "inspection"}
        if body.url:
            data["url"] = body.url

        message_id = send_push(
            fcm_token=token,
            title=body.title,
            body=body.body,
            data=data,
        )
        log.info(f"[FCM] 발송 완료 phone={body.phone} message_id={message_id}")
        return {
            "status":     "success",
            "message":    f"알림을 발송했습니다.",
            "phone":      body.phone,
            "message_id": message_id,
        }
    except Exception as e:
        log.error(f"[FCM] 발송 실패 phone={body.phone}: {e}")
        raise HTTPException(status_code=502, detail=f"FCM 발송 실패: {e}")


# ── POST /workers/push-test ──────────────────────────────

@router.post("/push-test")
def push_test(body: PushTestBody):
    """FCM 단건 테스트 (토큰 직접 지정)."""
    try:
        from utils.fcm_utils import send_push
        message_id = send_push(
            fcm_token=body.fcm_token,
            title=body.title,
            body=body.body,
            data={"type": "test"},
        )
        return {"status": "success", "message": "푸시 알림을 발송했습니다.", "message_id": message_id}
    except Exception as e:
        log.error(f"[FCM] push-test 실패: {e}")
        raise HTTPException(status_code=502, detail=f"FCM 발송 실패: {e}")
