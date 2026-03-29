# routers/auth.py — v3.2.0 (이메일 인증 버그수정: dateutil 제거)
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta
import os, re, random
from supabase import create_client

router = APIRouter(prefix="/auth", tags=["auth"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")

def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def normalize_phone(phone: str) -> str:
    return re.sub(r'[^0-9]', '', phone)

def is_email(value: str) -> bool:
    return "@" in value

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _parse_iso(s: str) -> datetime:
    """ISO8601 문자열 파싱 — 표준 라이브러리만 사용 (dateutil 불필요)"""
    # +00:00 또는 Z 처리
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # 마이크로초 없는 경우 fallback
        dt = datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ── 스키마 ──────────────────────────────────────

class LoginRequest(BaseModel):
    login_id: Optional[str] = None
    email:    Optional[str] = None
    phone:    Optional[str] = None
    password: str

class RegisterRequest(BaseModel):
    phone:        str
    email:        str
    password:     str
    name:         str
    role_code:    str = "002"
    company_name: Optional[str] = None
    company_type_code: Optional[str] = None

class FindPasswordRequest(BaseModel):
    phone: str

class UpdateMeRequest(BaseModel):
    name:            Optional[str] = None
    phone:           Optional[str] = None
    department:      Optional[str] = None
    position:        Optional[str] = None
    profile_image_url: Optional[str] = None
    allow_push:      Optional[bool] = None
    allow_sms:       Optional[bool] = None
    allow_email:     Optional[bool] = None
    allow_kakao:     Optional[bool] = None

class SendVerifyEmailRequest(BaseModel):
    email: str

class VerifyEmailRequest(BaseModel):
    email: str
    token: str


# ── 테스트 ──────────────────────────────────────

@router.get("/test")
def test():
    return {"message": "auth router alive", "version": "3.2"}


# ── 로그인 ──────────────────────────────────────

@router.post("/login")
def login(req: LoginRequest):
    supabase = get_supabase()

    identifier = req.login_id or req.email or req.phone
    if not identifier:
        raise HTTPException(status_code=400, detail="login_id (이메일 또는 전화번호)가 필요합니다")

    try:
        if is_email(identifier):
            rows = supabase.table("users").select(
                "id, email, name, phone, role_code, company_id, factory_id, status_code, profile_image_url"
            ).eq("email", identifier).limit(1).execute()
            if not rows.data:
                raise HTTPException(status_code=401, detail="가입되지 않은 이메일입니다")
        else:
            phone_norm = normalize_phone(identifier)
            rows = supabase.table("users").select(
                "id, email, name, phone, role_code, company_id, factory_id, status_code, profile_image_url"
            ).eq("phone", phone_norm).limit(1).execute()
            if not rows.data:
                raise HTTPException(status_code=401, detail="가입되지 않은 전화번호입니다")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"사용자 조회 오류: {str(e)}")

    user = rows.data[0]
    status = user.get("status_code", "ACTIVE")
    if status in ("SUSPENDED", "DELETED", "INACTIVE"):
        raise HTTPException(status_code=403, detail=f"접근 불가 계정입니다 ({status})")

    login_email = user.get("email")
    if not login_email:
        raise HTTPException(status_code=401, detail="이 계정은 이메일이 설정되어 있지 않습니다.")

    try:
        auth_res = supabase.auth.sign_in_with_password({
            "email":    login_email,
            "password": req.password,
        })
    except Exception:
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다")

    if not auth_res.user or not auth_res.session:
        raise HTTPException(status_code=401, detail="로그인 실패")

    try:
        supabase.table("users").update(
            {"last_login_at": _now_iso()}
        ).eq("id", user["id"]).execute()
    except Exception:
        pass

    return {
        "status": "success",
        "data": {
            "access_token":  auth_res.session.access_token,
            "refresh_token": auth_res.session.refresh_token,
            "token_type":    "Bearer",
            "expires_in":    auth_res.session.expires_in,
            "user": {
                "id":          user["id"],
                "phone":       user.get("phone"),
                "email":       user.get("email"),
                "name":        user["name"],
                "role_code":   user["role_code"],
                "company_id":  user.get("company_id"),
                "factory_id":  user.get("factory_id"),
                "status_code": user.get("status_code"),
                "profile_image_url": user.get("profile_image_url"),
            }
        }
    }


# ── 회원가입 ─────────────────────────────────────

@router.post("/register")
def register(req: RegisterRequest):
    supabase = get_supabase()
    phone_normalized = normalize_phone(req.phone)

    existing = supabase.table("users").select("id").eq("phone", phone_normalized).limit(1).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="이미 가입된 휴대폰 번호입니다")

    try:
        auth_res = supabase.auth.admin.create_user({
            "email":         req.email,
            "password":      req.password,
            "email_confirm": True,
            "user_metadata": {"name": req.name, "phone": phone_normalized, "role_code": req.role_code}
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"계정 생성 실패: {str(e)}")

    if not auth_res.user:
        raise HTTPException(status_code=400, detail="회원가입 실패")

    auth_id = str(auth_res.user.id)
    company_id = None

    if req.company_name:
        try:
            cr = supabase.table("companies").insert({
                "name": req.company_name,
                "company_type_code": req.company_type_code or "002",
                "status_code": "TRIAL",
                "is_active": True,
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
            }).execute()
            company_id = cr.data[0]["id"] if cr.data else None
        except Exception:
            pass

    import string
    user_code = "USR-" + datetime.now().strftime("%Y%m%d") + "-" + ''.join(random.choices(string.digits, k=4))

    try:
        ur = supabase.table("users").insert({
            "auth_id":     auth_id,
            "email":       req.email,
            "phone":       phone_normalized,
            "name":        req.name,
            "username":    phone_normalized,
            "role_code":   req.role_code,
            "company_id":  company_id,
            "user_code":   user_code,
            "status_code": "PENDING",
            "is_active":   False,
            "allow_push":  True,
            "allow_sms":   True,
            "allow_email": True,
            "allow_kakao": False,
            "created_at":  _now_iso(),
            "updated_at":  _now_iso(),
        }).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"사용자 저장 실패: {str(e)}")

    return {
        "status": "success",
        "message": "회원가입이 완료됐습니다.",
        "data": {"user_id": ur.data[0]["id"], "phone": phone_normalized, "name": req.name}
    }


# ── 로그아웃 ─────────────────────────────────────

@router.post("/logout")
def logout(authorization: Optional[str] = Header(None)):
    supabase = get_supabase()
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    return {"status": "success", "message": "로그아웃됐습니다"}


# ── 전화번호 중복 확인 ───────────────────────────

@router.post("/check-phone")
def check_phone(phone: str):
    supabase = get_supabase()
    pn = normalize_phone(phone)
    res = supabase.table("users").select("id").eq("phone", pn).limit(1).execute()
    return {
        "status": "success",
        "available": len(res.data) == 0,
        "message": "사용 가능" if not res.data else "이미 가입된 번호"
    }


# ── 비밀번호 재설정 ──────────────────────────────

@router.post("/reset-password")
def reset_password(req: FindPasswordRequest):
    supabase = get_supabase()
    pn = normalize_phone(req.phone)
    res = supabase.table("users").select("email").eq("phone", pn).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="가입되지 않은 전화번호입니다")
    email = res.data[0]["email"]
    try:
        supabase.auth.reset_password_email(email)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이메일 발송 실패: {str(e)}")
    parts = email.split("@")
    masked = parts[0][:2] + "**@" + parts[1] if len(parts) == 2 else email
    return {"status": "success", "message": f"재설정 링크를 {masked}로 발송했습니다"}


# ── 토큰 검증 ────────────────────────────────────

@router.post("/verify-token")
def verify_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="토큰이 없습니다")
    token = authorization.replace("Bearer ", "")
    supabase = get_supabase()
    try:
        ur = supabase.auth.get_user(token)
        if not ur or not ur.user:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰")
    except Exception:
        raise HTTPException(status_code=401, detail="토큰 검증 실패")
    res = supabase.table("users").select("*").eq("auth_id", str(ur.user.id)).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    return {"status": "success", "data": res.data[0]}


# ── 내 정보 ──────────────────────────────────────

@router.get("/me")
def get_me(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="토큰이 없습니다")
    token = authorization.replace("Bearer ", "")
    supabase = get_supabase()
    try:
        ur = supabase.auth.get_user(token)
        if not ur or not ur.user:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰")
    except Exception:
        raise HTTPException(status_code=401, detail="토큰 검증 실패")
    res = supabase.table("users").select("*").eq("auth_id", str(ur.user.id)).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    return {"status": "success", "data": res.data[0]}


@router.patch("/me")
def update_me(req: UpdateMeRequest, authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="토큰이 없습니다")
    token = authorization.replace("Bearer ", "")
    supabase = get_supabase()
    try:
        ur = supabase.auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="토큰 검증 실패")
    res = supabase.table("users").select("id").eq("auth_id", str(ur.user.id)).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    uid = res.data[0]["id"]
    update_data = {k: v for k, v in req.dict().items() if v is not None}
    if "phone" in update_data:
        update_data["phone"] = normalize_phone(update_data["phone"])
    update_data["updated_at"] = _now_iso()
    result = supabase.table("users").update(update_data).eq("id", uid).execute()
    return {"status": "success", "data": result.data[0] if result.data else {}}


# ────────────────────────────────────────────────
# S06 이메일 인증
# ────────────────────────────────────────────────

@router.post("/send-verify-email")
async def send_verify_email(req: SendVerifyEmailRequest):
    """
    이메일 인증 코드 발송.
    - 6자리 숫자 토큰 생성 → DB 저장 → Resend 발송
    """
    import resend as resend_client

    supabase = get_supabase()
    try:
        # 1. 사용자 조회
        res = supabase.table("users").select(
            "id, email, name"
        ).eq("email", req.email).limit(1).execute()

        if not res.data:
            raise HTTPException(status_code=404, detail="가입되지 않은 이메일입니다.")

        user = res.data[0]

        # 2. 6자리 토큰 생성
        token = str(random.randint(100000, 999999))
        now = _now_iso()

        # 3. DB 저장
        supabase.table("users").update({
            "email_verify_token":   token,
            "email_verify_sent_at": now,
            "updated_at":           now,
        }).eq("id", user["id"]).execute()

        # 4. Resend 발송
        if not RESEND_API_KEY:
            raise HTTPException(status_code=500, detail="RESEND_API_KEY 미설정")

        resend_client.api_key = RESEND_API_KEY
        resend_client.Emails.send({
            "from":    "TAI Engineering <noreply@taieng.co.kr>",
            "to":      [req.email],
            "subject": f"[TAI] 이메일 인증 코드: {token}",
            "text": (
                f"인증 코드: {token}\n"
                f"이 코드는 10분간 유효합니다.\n\n"
                f"TAI Engineering"
            ),
        })

        print(f"[AUTH] 인증 이메일 발송 → {req.email}")

        return {
            "status": "success",
            "message": f"인증 코드를 {req.email}로 발송했습니다. 10분 이내에 입력해 주세요.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verify-email")
async def verify_email(req: VerifyEmailRequest):
    """
    이메일 인증 토큰 검증.
    - dateutil 미사용 → fromisoformat 표준 라이브러리 사용 (v3.2.0 수정)
    """
    supabase = get_supabase()
    try:
        res = supabase.table("users").select(
            "id, email_verify_token, email_verify_sent_at, email_verified"
        ).eq("email", req.email).limit(1).execute()

        if not res.data:
            raise HTTPException(status_code=404, detail="가입되지 않은 이메일입니다.")

        user = res.data[0]
        stored_token = user.get("email_verify_token")
        sent_at_str  = user.get("email_verify_sent_at")

        # 토큰 일치 확인
        if stored_token != req.token:
            raise HTTPException(status_code=400, detail="인증 코드가 올바르지 않습니다.")

        # 10분 만료 확인 — 표준 라이브러리만 사용
        if sent_at_str:
            try:
                sent_at = _parse_iso(str(sent_at_str))
                elapsed = datetime.now(timezone.utc) - sent_at
                if elapsed > timedelta(minutes=10):
                    raise HTTPException(
                        status_code=400,
                        detail="인증 코드가 만료됐습니다. 다시 요청해 주세요."
                    )
            except HTTPException:
                raise
            except Exception:
                pass  # 파싱 오류는 통과

        # 인증 성공 — DB 업데이트
        now = _now_iso()
        supabase.table("users").update({
            "email_verified":     True,
            "email_verified_at":  now,
            "email_verify_token": None,
            "updated_at":         now,
        }).eq("email", req.email).execute()

        print(f"[AUTH] 이메일 인증 성공 → {req.email}")

        return {
            "status": "success",
            "message": "이메일 인증이 완료됐습니다.",
            "data": {
                "email":             req.email,
                "email_verified":    True,
                "email_verified_at": now,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
