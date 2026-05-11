# routers/pw_reset.py — v1.0.1
# v1.0.1: messaging import 호환 수정 (EDGE_SMS_URL, _call_edge_function)
# SMS OTP 기반 비밀번호 재설정
# POST /auth/pw-reset/request — OTP 생성 + SMS 발송
# POST /auth/pw-reset/confirm — OTP 검증 + 비밀번호 변경

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
import os, re, random, logging

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/pw-reset", tags=["비밀번호재설정"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def _get_supabase():
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _normalize_phone(phone: str) -> str:
    return re.sub(r'[^0-9]', '', phone)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _send_sms(receiver: str, message: str) -> dict:
    """messaging 모듈의 Edge Function 경유 SMS 발송"""
    try:
        from routers.messaging import _call_edge_function, _get_cfg
        import asyncio
        cfg = _get_cfg()
        if not cfg.get("edge_url"):
            log.error("[PW_RESET] EDGE_SMS_URL 미설정")
            return {"success": False, "reason": "SMS 설정 미완료"}
        payload = {"receiver": receiver, "message": message}
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(asyncio.run, _call_edge_function(payload)).result()
            else:
                result = loop.run_until_complete(_call_edge_function(payload))
        except RuntimeError:
            result = asyncio.run(_call_edge_function(payload))
        return result
    except Exception as e:
        log.error(f"[PW_RESET] SMS 발송 실패: {e}")
        return {"success": False, "reason": str(e)}


# ── 스키마 ────────────────────────────────────

class PwResetRequest(BaseModel):
    phone: str


class PwResetConfirm(BaseModel):
    phone: str
    otp: str
    new_password: str


# ── 1) OTP 발송 ──────────────────────────────

@router.post("/request")
def pw_reset_request(req: PwResetRequest):
    supabase = _get_supabase()
    phone = _normalize_phone(req.phone)
    if len(phone) < 10:
        raise HTTPException(status_code=400, detail="올바른 전화번호를 입력하세요.")

    # 사용자 존재 확인
    user_res = supabase.table("users").select("id, name").eq("phone", phone).limit(1).execute()
    if not user_res.data:
        raise HTTPException(status_code=404, detail="가입되지 않은 전화번호입니다.")

    # OTP 생성 + 저장
    otp_code = str(random.randint(100000, 999999))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    try:
        supabase.table("otp_store").upsert({
            "phone": phone,
            "otp": otp_code,
            "expires_at": expires_at.isoformat(),
            "created_at": _now_iso(),
        }, on_conflict="phone").execute()
    except Exception as e:
        log.error(f"[PW_RESET] OTP 저장 실패: {e}")
        raise HTTPException(status_code=500, detail="인증번호 생성에 실패했습니다.")

    # SMS 발송
    sms_msg = f"[TAI Safe] 비밀번호 재설정 인증번호: {otp_code} (5분 이내 입력)"
    sms_result = _send_sms(phone, sms_msg)

    if not sms_result.get("success"):
        log.warning(f"[PW_RESET] SMS 발송 실패 phone={phone} result={sms_result}")

    user_name = user_res.data[0].get("name", "")
    masked_phone = phone[:3] + "****" + phone[-4:] if len(phone) >= 8 else phone

    return {
        "status": "success",
        "message": f"인증번호를 {masked_phone}으로 발송했습니다.",
        "name": user_name,
        "sms_sent": sms_result.get("success", False),
    }


# ── 2) OTP 검증 + 비밀번호 변경 ───────────────

@router.post("/confirm")
def pw_reset_confirm(req: PwResetConfirm):
    supabase = _get_supabase()
    phone = _normalize_phone(req.phone)
    otp = req.otp.strip()
    new_pw = req.new_password

    if len(new_pw) < 6:
        raise HTTPException(status_code=400, detail="비밀번호는 6자 이상이어야 합니다.")

    # OTP 검증
    otp_valid = False
    try:
        otp_res = supabase.table("otp_store").select("otp, expires_at").eq("phone", phone).limit(1).execute()
        if otp_res.data:
            row = otp_res.data[0]
            if row["otp"] == otp:
                exp_str = str(row["expires_at"]).replace("Z", "+00:00")
                try:
                    exp = datetime.fromisoformat(exp_str)
                except ValueError:
                    exp = datetime.strptime(exp_str[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) <= exp:
                    otp_valid = True
                else:
                    raise HTTPException(status_code=400, detail="인증번호가 만료되었습니다. 다시 요청해주세요.")
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[PW_RESET] OTP 검증 오류: {e}")

    if not otp_valid:
        raise HTTPException(status_code=401, detail="인증번호가 올바르지 않습니다.")

    # 사용자 조회 → auth_id 확인
    user_res = supabase.table("users").select("id, auth_id, email").eq("phone", phone).limit(1).execute()
    if not user_res.data:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    user = user_res.data[0]
    auth_id = user.get("auth_id")
    if not auth_id:
        raise HTTPException(status_code=400, detail="인증 계정이 연결되지 않은 사용자입니다. 관리자에게 문의하세요.")

    # Supabase Auth 비밀번호 변경
    try:
        supabase.auth.admin.update_user_by_id(auth_id, {"password": new_pw})
    except Exception as e:
        log.error(f"[PW_RESET] 비밀번호 변경 실패: {e}")
        raise HTTPException(status_code=500, detail="비밀번호 변경에 실패했습니다. 잠시 후 다시 시도해주세요.")

    # OTP 삭제 (재사용 방지)
    try:
        supabase.table("otp_store").delete().eq("phone", phone).execute()
    except Exception:
        pass

    return {
        "status": "success",
        "message": "비밀번호가 변경되었습니다. 새 비밀번호로 로그인해주세요."
    }
