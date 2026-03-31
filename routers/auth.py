# routers/auth.py — v3.4.0
# v3.4.0: POST /auth/register — business_number, representative_name 필드 추가
#          companies INSERT 시 사업자번호/대표자명 포함
# v3.3.0: /auth/seed-test-accounts 임시 엔드포인트 추가
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
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        dt = datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ── 스키마 ──────────────────────────────────

class LoginRequest(BaseModel):
    login_id: Optional[str] = None
    email:    Optional[str] = None
    phone:    Optional[str] = None
    password: str

class RegisterRequest(BaseModel):
    phone:                str
    email:                str
    password:             str
    name:                 str
    role_code:            str = "002"
    company_name:         Optional[str] = None
    company_type_code:    Optional[str] = None
    # v3.4.0: 신규 필드
    business_number:      Optional[str] = None   # 사업자등록번호
    representative_name:  Optional[str] = None   # 대표자명
    ksic_code:            Optional[str] = None   # 업종코드
    contact_phone:        Optional[str] = None   # 회사 연락처

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


# ── 테스트 ──────────────────────────────────

@router.get("/test")
def test():
    return {"message": "auth router alive", "version": "3.4"}


# ── 테스트 계정 시드 (임시) ────────────────────

@router.post("/seed-test-accounts")
def seed_test_accounts():
    """
    테스트 계정 Supabase Auth 등록 + users.auth_id 업데이트.
    auth_id가 없는 계정만 처리. 비밀번호: tai1234!
    """
    supabase = get_supabase()

    TEST_ACCOUNTS = [
        {"email": "admin@tai.com",                  "password": "tai1234!"},
        {"email": "safety-mgr@korean-safe.co.kr",   "password": "tai1234!"},
        {"email": "worker@tai.com",                 "password": "tai1234!"},
        {"email": "worker@korean-safe.co.kr",       "password": "tai1234!"},
    ]

    results = []
    for acct in TEST_ACCOUNTS:
        email    = acct["email"]
        password = acct["password"]

        u_res = supabase.table("users").select("id, auth_id").eq("email", email).limit(1).execute()
        if not u_res.data:
            results.append({"email": email, "status": "skipped", "reason": "users 테이블에 없음"})
            continue

        user    = u_res.data[0]
        user_id = user["id"]

        if user.get("auth_id"):
            results.append({"email": email, "status": "skipped", "reason": "이미 auth_id 있음"})
            continue

        try:
            auth_res = supabase.auth.admin.create_user({
                "email":         email,
                "password":      password,
                "email_confirm": True,
            })
            auth_id = str(auth_res.user.id)
            supabase.table("users").update({
                "auth_id":    auth_id,
                "updated_at": _now_iso(),
            }).eq("id", user_id).execute()
            results.append({"email": email, "status": "created", "auth_id": auth_id})

        except Exception as e:
            err = str(e)
            if "already" in err.lower() or "exists" in err.lower() or "duplicate" in err.lower():
                try:
                    users_list = supabase.auth.admin.list_users()
                    matched = next(
                        (u for u in (users_list or []) if getattr(u, "email", None) == email),
                        None
                    )
                    if matched:
                        auth_id = str(matched.id)
                        supabase.table("users").update({
                            "auth_id":    auth_id,
                            "updated_at": _now_iso(),
                        }).eq("id", user_id).execute()
                        results.append({"email": email, "status": "linked", "auth_id": auth_id})
                    else:
                        results.append({"email": email, "status": "error", "reason": f"Auth 존재하나 목록 조회 실패: {err}"})
                except Exception as e2:
                    results.append({"email": email, "status": "error", "reason": str(e2)})
            else:
                results.append({"email": email, "status": "error", "reason": err})

    return {"status": "success", "data": results}


# ── 로그인 ──────────────────────────────────

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


# ── 회원가입 v3.4.0 ───────────────────────────

@router.post("/register")
def register(req: RegisterRequest):
    """
    v3.4.0: business_number, representative_name 필드 추가.
    company_name 입력 시 companies 테이블에 사업자번호/대표자명도 함께 저장.
    """
    supabase = get_supabase()
    phone_normalized = normalize_phone(req.phone)

    existing = supabase.table("users").select("id").eq("phone", phone_normalized).limit(1).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="이미 가입된 휴대폰 번호입니다")

    # 이메일 중복 확인
    email_dup = supabase.table("users").select("id").eq("email", req.email).limit(1).execute()
    if email_dup.data:
        raise HTTPException(status_code=400, detail="이미 가입된 이메일입니다")

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

    auth_id    = str(auth_res.user.id)
    company_id = None

    # 회사명 입력된 경우 companies 테이블에 등록
    if req.company_name:
        # 사업자번호 중복 선확인
        if req.business_number:
            bn_clean = re.sub(r'[^0-9]', '', req.business_number)
            bn_dup = supabase.table("companies").select("id").eq(
                "business_number", bn_clean
            ).limit(1).execute()
            if bn_dup.data:
                company_id = bn_dup.data[0]["id"]  # 이미 등록된 회사 연결

        if not company_id:
            try:
                company_data = {
                    "name":              req.company_name,
                    "company_type_code": req.company_type_code or "002",
                    "company_code":      f"COM-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    "status_code":       "TRIAL",
                    "is_active":         True,
                    "created_at":        _now_iso(),
                    "updated_at":        _now_iso(),
                }
                # v3.4.0: 사업자번호 / 대표자명 / 업종 / 연락처 포함
                if req.business_number:
                    company_data["business_number"] = re.sub(r'[^0-9]', '', req.business_number)
                if req.representative_name:
                    company_data["representative_name"] = req.representative_name
                if req.ksic_code:
                    company_data["ksic_code"] = req.ksic_code
                if req.contact_phone:
                    company_data["contact_phone"] = req.contact_phone

                cr = supabase.table("companies").insert(company_data).execute()
                company_id = cr.data[0]["id"] if cr.data else None
            except Exception:
                pass  # 회사 등록 실패 시 유저 등록만 진행

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
        "status":  "success",
        "message": "회원가입이 완료됐습니다.",
        "data": {
            "user_id":    ur.data[0]["id"],
            "phone":      phone_normalized,
            "name":       req.name,
            "company_id": company_id,
        }
    }


# ── 로그아웃 ──────────────────────────────────

@router.post("/logout")
def logout(authorization: Optional[str] = Header(None)):
    supabase = get_supabase()
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    return {"status": "success", "message": "로그아웃됐습니다"}


# ── 전화번호 중복 확인 ────────────────────────

@router.post("/check-phone")
def check_phone(phone: str):
    supabase = get_supabase()
    pn = normalize_phone(phone)
    res = supabase.table("users").select("id").eq("phone", pn).limit(1).execute()
    return {
        "status":    "success",
        "available": len(res.data) == 0,
        "message":   "사용 가능" if not res.data else "이미 가입된 번호"
    }


# ── 비밀번호 재설정 ────────────────────────

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


# ── 토큰 검증 ────────────────────────────────

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


# ── 내 정보 ──────────────────────────────────

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


# ──────────────────────────────────────────────
# S06 이메일 인증
# ──────────────────────────────────────────────

@router.post("/send-verify-email")
async def send_verify_email(body: SendVerifyEmailRequest):
    import resend as resend_client
    supabase = get_supabase()
    try:
        res = supabase.table("users").select("id, email, name").eq("email", body.email).limit(1).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="가입되지 않은 이메일입니다.")
        user  = res.data[0]
        token = str(random.randint(100000, 999999))
        now   = _now_iso()
        supabase.table("users").update({
            "email_verify_token":   token,
            "email_verify_sent_at": now,
            "updated_at":           now,
        }).eq("id", user["id"]).execute()
        if not RESEND_API_KEY:
            raise HTTPException(status_code=500, detail="RESEND_API_KEY 미설정")
        resend_client.api_key = RESEND_API_KEY
        resend_client.Emails.send({
            "from":    "TAI Engineering <noreply@taieng.co.kr>",
            "to":      [body.email],
            "subject": f"[TAI] 이메일 인증 코드: {token}",
            "text":    f"인증 코드: {token}\n이 코드는 10분간 유효합니다.\n\nTAI Engineering",
        })
        return {"status": "success", "message": f"인증 코드를 {body.email}로 발송했습니다."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verify-email")
async def verify_email(req: VerifyEmailRequest):
    supabase = get_supabase()
    try:
        res = supabase.table("users").select(
            "id, email_verify_token, email_verify_sent_at, email_verified"
        ).eq("email", req.email).limit(1).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="가입되지 않은 이메일입니다.")
        user         = res.data[0]
        stored_token = user.get("email_verify_token")
        sent_at_str  = user.get("email_verify_sent_at")
        if stored_token != req.token:
            raise HTTPException(status_code=400, detail="인증 코드가 올바르지 않습니다.")
        if sent_at_str:
            try:
                sent_at = _parse_iso(str(sent_at_str))
                if datetime.now(timezone.utc) - sent_at > timedelta(minutes=10):
                    raise HTTPException(status_code=400, detail="인증 코드가 만료됐습니다.")
            except HTTPException:
                raise
            except Exception:
                pass
        now = _now_iso()
        supabase.table("users").update({
            "email_verified":     True,
            "email_verified_at":  now,
            "email_verify_token": None,
            "updated_at":         now,
        }).eq("email", req.email).execute()
        return {
            "status":  "success",
            "message": "이메일 인증이 완료됐습니다.",
            "data":    {"email": req.email, "email_verified": True, "email_verified_at": now},
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
