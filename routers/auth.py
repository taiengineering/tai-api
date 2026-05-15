# routers/auth.py — v3.7.0
# v3.7.0: #65 RLS bypass — get_supabase()를 service_role key로 변경 (모든 테이블 조작 정상화)
# v3.6.0: GET /auth/me 에 identity_verified + expert_status 포함
# v3.5.0: PWA 작업자 인증 — POST /auth/send-otp, POST /auth/verify-otp 추가
# v3.4.1: get_current_user() Depends 함수 추가
# v3.4.0: POST /auth/register — business_number, representative_name 필드 추가
# v3.3.0: /auth/seed-test-accounts 임시 엔드포인트 추가
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta
import os, re, random
from supabase import create_client
from services.health_registry import register_probe
from watch_engine import create_trace, emit_event
from watch_engine.trace import clear_trace

router = APIRouter(prefix="/auth", tags=["auth"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", SUPABASE_KEY)
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")

def get_supabase():
    """v3.7.0: auth.py는 백엔드 라우터 — service_role key로 RLS bypass"""
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

def get_supabase_admin():
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

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


# ════════════════════════════════════════════
# v3.4.1: FastAPI Depends용 인증 의존성 함수
# ════════════════════════════════════════════

def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="토큰이 없습니다")
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
    res = supabase.table("users").select("*").eq("auth_id", str(ur.user.id)).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    return res.data[0]


# ── 스키마 ─────────────────────────────────────────

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
    business_number:      Optional[str] = None
    representative_name:  Optional[str] = None
    ksic_code:            Optional[str] = None
    contact_phone:        Optional[str] = None

class FindPasswordRequest(BaseModel):
    phone: str

class UpdateMeRequest(BaseModel):
    name:              Optional[str] = None
    phone:             Optional[str] = None
    department:        Optional[str] = None
    position:          Optional[str] = None
    profile_image_url: Optional[str] = None
    allow_push:        Optional[bool] = None
    allow_sms:         Optional[bool] = None
    allow_email:       Optional[bool] = None
    allow_kakao:       Optional[bool] = None

class SendVerifyEmailRequest(BaseModel):
    email: str

class VerifyEmailRequest(BaseModel):
    email: str
    token: str

class SendOtpRequest(BaseModel):
    phone: str

class VerifyOtpRequest(BaseModel):
    phone: str
    otp:   str


# ── 테스트 ─────────────────────────────────────────

@router.get("/test")
def test():
    return {"message": "auth router alive", "version": "3.7.0"}


# ════════════════════════════════════════════
# v3.5.0: PWA 작업자 인증 — OTP 발송 / 검증
# ════════════════════════════════════════════

@router.post("/send-otp")
def send_otp(req: SendOtpRequest):
    supabase = get_supabase()
    phone = normalize_phone(req.phone)
    otp_code = str(random.randint(100000, 999999))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    try:
        supabase.table("otp_store").upsert({
            "phone":      phone,
            "otp":        otp_code,
            "expires_at": expires_at.isoformat(),
            "created_at": _now_iso(),
        }, on_conflict="phone").execute()
    except Exception:
        try:
            supabase.table("users").update({
                "raw_app_meta_data": {"otp": otp_code, "otp_exp": expires_at.isoformat()},
                "updated_at": _now_iso(),
            }).eq("phone", phone).execute()
        except Exception:
            pass
    return {
        "status":  "success",
        "message": f"인증번호를 발송했습니다 ({phone})",
        "dev_otp": otp_code,  # ⚠ 개발용 — 프로덕션 배포 시 제거
    }


@router.post("/verify-otp")
def verify_otp(req: VerifyOtpRequest):
    supabase = get_supabase()
    phone = normalize_phone(req.phone)
    otp   = req.otp.strip()
    otp_valid = False

    # Google Play 심사용 테스트 계정 (고정 OTP 우회)
    TEST_BYPASS = {"01047758888": "123456", "01083994168": "000000"}
    if phone in TEST_BYPASS and otp == TEST_BYPASS[phone]:
        otp_valid = True

    try:
        otp_res = supabase.table("otp_store").select("otp, expires_at").eq("phone", phone).limit(1).execute()
        if otp_res.data:
            row = otp_res.data[0]
            if row["otp"] == otp:
                exp = _parse_iso(str(row["expires_at"]))
                if datetime.now(timezone.utc) <= exp:
                    otp_valid = True
    except Exception:
        pass

    if not otp_valid:
        try:
            ur = supabase.table("users").select("raw_app_meta_data").eq("phone", phone).limit(1).execute()
            if ur.data:
                meta = ur.data[0].get("raw_app_meta_data") or {}
                if meta.get("otp") == otp:
                    exp_str = meta.get("otp_exp", "")
                    if exp_str:
                        exp = _parse_iso(exp_str)
                        if datetime.now(timezone.utc) <= exp:
                            otp_valid = True
        except Exception:
            pass

    if not otp_valid:
        raise HTTPException(status_code=401, detail="인증번호가 올바르지 않거나 만료되었습니다.")

    u_res = supabase.table("users").select(
        "id, phone, name, sector, factory_id, company_id, department, position, profile_image_url"
    ).eq("phone", phone).limit(1).execute()

    if not u_res.data:
        return {
            "id": None, "worker_id": None, "phone": phone, "name": phone,
            "sector": "INDUSTRIAL", "factory_id": None, "site_id": None,
            "company": "", "job_type": "",
        }

    user = u_res.data[0]
    sector     = user.get("sector") or "INDUSTRIAL"
    factory_id = user.get("factory_id")
    company_id = user.get("company_id")
    factory_name = ""
    if factory_id:
        try:
            f = supabase.table("factories").select("name, sector").eq("id", factory_id).limit(1).execute()
            if f.data:
                factory_name = f.data[0].get("name", "")
                if f.data[0].get("sector"):
                    sector = f.data[0]["sector"]
        except Exception:
            pass
    company_name = ""
    if company_id:
        try:
            c = supabase.table("companies").select("name").eq("id", company_id).limit(1).execute()
            if c.data:
                company_name = c.data[0].get("name", "")
        except Exception:
            pass
    site_id = None
    if sector == "CONSTRUCTION":
        try:
            s = supabase.table("construction_sites").select("id").eq("company_id", company_id).eq("is_active", True).limit(1).execute()
            if s.data:
                site_id = s.data[0]["id"]
        except Exception:
            pass
    try:
        supabase.table("otp_store").delete().eq("phone", phone).execute()
    except Exception:
        pass

    return {
        "id": user["id"], "worker_id": user["id"], "phone": phone,
        "name": user.get("name") or phone, "sector": sector,
        "factory_id": factory_id, "site_id": site_id,
        "company": company_name or factory_name,
        "job_type": user.get("position") or user.get("department") or "",
        "profile_image_url": user.get("profile_image_url"),
    }


# ── 테스트 계정 시드 ────────────────────────────────

@router.post("/seed-test-accounts")
def seed_test_accounts():
    supabase = get_supabase_admin()
    TEST_ACCOUNTS = [
        {"email": "admin@tai.com",                  "password": "tai1234!"},
        {"email": "safety-mgr@korean-safe.co.kr",   "password": "tai1234!"},
        {"email": "worker@tai.com",                 "password": "tai1234!"},
        {"email": "worker@korean-safe.co.kr",       "password": "tai1234!"},
    ]
    results = []
    for acct in TEST_ACCOUNTS:
        email = acct["email"]; password = acct["password"]
        u_res = supabase.table("users").select("id, auth_id").eq("email", email).limit(1).execute()
        if not u_res.data:
            results.append({"email": email, "status": "skipped", "reason": "users 테이블에 없음"}); continue
        user = u_res.data[0]
        if user.get("auth_id"):
            results.append({"email": email, "status": "skipped", "reason": "이미 auth_id 있음"}); continue
        try:
            auth_res = supabase.auth.admin.create_user({"email": email, "password": password, "email_confirm": True})
            auth_id = str(auth_res.user.id)
            supabase.table("users").update({"auth_id": auth_id, "updated_at": _now_iso()}).eq("id", user["id"]).execute()
            results.append({"email": email, "status": "created", "auth_id": auth_id})
        except Exception as e:
            err = str(e)
            if "already" in err.lower() or "exists" in err.lower() or "duplicate" in err.lower():
                try:
                    users_list = supabase.auth.admin.list_users()
                    matched = next((u for u in (users_list or []) if getattr(u, "email", None) == email), None)
                    if matched:
                        auth_id = str(matched.id)
                        supabase.table("users").update({"auth_id": auth_id, "updated_at": _now_iso()}).eq("id", user["id"]).execute()
                        results.append({"email": email, "status": "linked", "auth_id": auth_id})
                    else:
                        results.append({"email": email, "status": "error", "reason": err})
                except Exception as e2:
                    results.append({"email": email, "status": "error", "reason": str(e2)})
            else:
                results.append({"email": email, "status": "error", "reason": err})
    return {"status": "success", "data": results}


# ── 로그인 ─────────────────────────────────────────

@router.post("/login")
def login(req: LoginRequest):
    create_trace(flow_key="login", tenant_id="tai", actor_type="user")
    supabase = get_supabase()
    identifier = req.login_id or req.email or req.phone
    emit_event(
        step_key="submit_credentials",
        step_order=0,
        event_type="submit",
        result="success",
        connector_type="api",
        payload_summary={
            "has_identifier": bool(identifier),
            "has_password": bool((req.password or "").strip()),
        },
    )
    if not identifier:
        emit_event(
            step_key="validate_auth",
            step_order=1,
            event_type="validate",
            result="failure",
            connector_type="api",
            payload_summary={"auth_result": "failure"},
        )
        clear_trace()
        raise HTTPException(status_code=400, detail="login_id (이메일 또는 전화번호)가 필요합니다")
    try:
        if is_email(identifier):
            rows = supabase.table("users").select(
                "id, email, name, phone, role_code, company_id, factory_id, status_code, profile_image_url"
            ).eq("email", identifier).limit(1).execute()
            if not rows.data:
                emit_event(
                    step_key="validate_auth",
                    step_order=1,
                    event_type="validate",
                    result="failure",
                    connector_type="api",
                    payload_summary={"auth_result": "failure"},
                )
                clear_trace()
                raise HTTPException(status_code=401, detail="가입되지 않은 이메일입니다")
        else:
            phone_norm = normalize_phone(identifier)
            rows = supabase.table("users").select(
                "id, email, name, phone, role_code, company_id, factory_id, status_code, profile_image_url"
            ).eq("phone", phone_norm).limit(1).execute()
            if not rows.data:
                emit_event(
                    step_key="validate_auth",
                    step_order=1,
                    event_type="validate",
                    result="failure",
                    connector_type="api",
                    payload_summary={"auth_result": "failure"},
                )
                clear_trace()
                raise HTTPException(status_code=401, detail="가입되지 않은 전화번호입니다")
    except HTTPException:
        raise
    except Exception as e:
        emit_event(
            step_key="error",
            step_order=99,
            event_type="error",
            result="failure",
            connector_type="api",
        )
        clear_trace()
        raise HTTPException(status_code=500, detail=f"사용자 조회 오류: {str(e)}")
    user = rows.data[0]
    status = user.get("status_code", "ACTIVE")
    if status in ("SUSPENDED", "DELETED", "INACTIVE"):
        emit_event(
            step_key="validate_auth",
            step_order=1,
            event_type="validate",
            result="failure",
            connector_type="api",
            payload_summary={"auth_result": "failure"},
        )
        clear_trace()
        raise HTTPException(status_code=403, detail=f"접근 불가 계정입니다 ({status})")
    login_email = user.get("email")
    if not login_email:
        emit_event(
            step_key="validate_auth",
            step_order=1,
            event_type="validate",
            result="failure",
            connector_type="api",
            payload_summary={"auth_result": "failure"},
        )
        clear_trace()
        raise HTTPException(status_code=401, detail="이 계정은 이메일이 설정되어 있지 않습니다.")
    try:
        auth_res = supabase.auth.sign_in_with_password({"email": login_email, "password": req.password})
    except Exception:
        emit_event(
            step_key="validate_auth",
            step_order=1,
            event_type="validate",
            result="failure",
            connector_type="api",
            payload_summary={"auth_result": "failure"},
        )
        clear_trace()
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다")
    if not auth_res.user or not auth_res.session:
        emit_event(
            step_key="validate_auth",
            step_order=1,
            event_type="validate",
            result="failure",
            connector_type="api",
            payload_summary={"auth_result": "failure"},
        )
        clear_trace()
        raise HTTPException(status_code=401, detail="로그인 실패")
    emit_event(
        step_key="validate_auth",
        step_order=1,
        event_type="validate",
        result="success",
        connector_type="api",
        payload_summary={"auth_result": "success"},
    )
    try:
        supabase.table("users").update({"last_login_at": _now_iso()}).eq("id", user["id"]).execute()
    except Exception:
        pass
    emit_event(
        step_key="session_issued",
        step_order=2,
        event_type="read",
        result="success",
        connector_type="api",
        payload_summary={"has_token": True},
    )
    clear_trace()
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


# ── 회원가입 v3.4.0 ────────────────────────────────

@router.post("/register")
def register(req: RegisterRequest):
    supabase = get_supabase()
    phone_normalized = normalize_phone(req.phone)
    existing = supabase.table("users").select("id").eq("phone", phone_normalized).limit(1).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="이미 가입된 휴대폰 번호입니다")
    email_dup = supabase.table("users").select("id").eq("email", req.email).limit(1).execute()
    if email_dup.data:
        raise HTTPException(status_code=400, detail="이미 가입된 이메일입니다")
    try:
        auth_res = supabase.auth.sign_up(
            {
                "email": req.email,
                "password": req.password,
                "options": {
                    "data": {"name": req.name, "phone": phone_normalized, "role_code": req.role_code}
                },
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"계정 생성 실패: {str(e)}")
    if not auth_res.user:
        raise HTTPException(status_code=400, detail="회원가입 실패")
    auth_id = str(auth_res.user.id)
    company_id = None
    if req.company_name:
        if req.business_number:
            bn_clean = re.sub(r'[^0-9]', '', req.business_number)
            bn_dup = supabase.table("companies").select("id").eq("business_number", bn_clean).limit(1).execute()
            if bn_dup.data:
                company_id = bn_dup.data[0]["id"]
        if not company_id:
            try:
                cd = {"name": req.company_name, "company_type_code": req.company_type_code or "002",
                      "company_code": f"COM-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                      "status_code": "TRIAL", "is_active": True,
                      "created_at": _now_iso(), "updated_at": _now_iso()}
                if req.business_number: cd["business_number"] = re.sub(r'[^0-9]', '', req.business_number)
                if req.representative_name: cd["representative_name"] = req.representative_name
                if req.ksic_code: cd["ksic_code"] = req.ksic_code
                if req.contact_phone: cd["contact_phone"] = req.contact_phone
                cr = supabase.table("companies").insert(cd).execute()
                company_id = cr.data[0]["id"] if cr.data else None
            except Exception:
                pass
    import string
    user_code = "USR-" + datetime.now().strftime("%Y%m%d") + "-" + ''.join(random.choices(string.digits, k=4))
    try:
        ur = supabase.table("users").insert({
            "auth_id": auth_id, "email": req.email, "phone": phone_normalized,
            "name": req.name, "username": phone_normalized, "role_code": req.role_code,
            "company_id": company_id, "user_code": user_code, "status_code": "PENDING",
            "is_active": False, "allow_push": True, "allow_sms": True,
            "allow_email": True, "allow_kakao": False,
            "created_at": _now_iso(), "updated_at": _now_iso(),
        }).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"사용자 저장 실패: {str(e)}")
    return {"status": "success", "message": "회원가입이 완료되었습니다.",
            "data": {"user_id": ur.data[0]["id"], "phone": phone_normalized, "name": req.name, "company_id": company_id}}


# ── 로그아웃 ────────────────────────────────────────

@router.post("/logout")
def logout(authorization: Optional[str] = Header(None)):
    try: get_supabase().auth.sign_out()
    except Exception: pass
    return {"status": "success", "message": "로그아웃되었습니다"}


# ── 전화번호 중복 확인 ────────────────────────────

@router.post("/check-phone")
def check_phone(phone: str):
    supabase = get_supabase()
    pn = normalize_phone(phone)
    res = supabase.table("users").select("id").eq("phone", pn).limit(1).execute()
    return {"status": "success", "available": len(res.data) == 0,
            "message": "사용 가능" if not res.data else "이미 가입된 번호"}


# ── 비밀번호 재설정 ─────────────────────────────

@router.post("/reset-password")
def reset_password(req: FindPasswordRequest):
    supabase = get_supabase()
    pn = normalize_phone(req.phone)
    res = supabase.table("users").select("email").eq("phone", pn).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="가입되지 않은 전화번호입니다")
    email = res.data[0]["email"]
    try:
        get_supabase().auth.reset_password_email(email)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이메일 발송 실패: {str(e)}")
    parts = email.split("@")
    masked = parts[0][:2] + "**@" + parts[1] if len(parts) == 2 else email
    return {"status": "success", "message": f"재설정 링크를 {masked}로 발송했습니다"}


# ── 토큰 검증 ───────────────────────────────────────

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


# ── v3.6.0: GET /auth/me — identity_verified + expert_status 포함 ─────

@router.get("/me")
def get_me(authorization: Optional[str] = Header(None)):
    """
    내 정보 조회.

    v3.6.0: 응답에 identity_verified + expert_status 포함.
    expert_status 구조:
    ```json
    {
      "safety":  { "status": "pending", "application_id": "...", ... },
      "fix":     null,
      "consult": null
    }
    ```
    """
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
    user_data = res.data[0]

    # 전문가 등록 현황 조회
    expert_status: dict = {"safety": None, "fix": None, "consult": None}
    try:
        apps = supabase.table("expert_applications").select(
            "id, expert_type, status, created_at, reviewed_at, platform_fee_rate, review_note"
        ).eq("user_id", user_data["id"]).execute()
        for app in (apps.data or []):
            expert_status[app["expert_type"]] = {
                "status":           app["status"],
                "application_id":  app["id"],
                "applied_at":       app["created_at"],
                "reviewed_at":      app.get("reviewed_at"),
                "platform_fee_rate": float(app["platform_fee_rate"]) if app.get("platform_fee_rate") else None,
                "review_note":      app.get("review_note") if app["status"] == "rejected" else None,
            }
    except Exception:
        pass

    return {
        "status": "success",
        "data": {
            **user_data,
            "identity_verified": user_data.get("identity_verified") or False,
            "expert_status":     expert_status,
        }
    }


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


# ── 이메일 인증 ─────────────────────────────────────

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
            "email_verify_token": token, "email_verify_sent_at": now, "updated_at": now,
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
        user = res.data[0]
        if user.get("email_verify_token") != req.token:
            raise HTTPException(status_code=400, detail="인증 코드가 올바르지 않습니다.")
        sent_at_str = user.get("email_verify_sent_at")
        if sent_at_str:
            try:
                sent_at = _parse_iso(str(sent_at_str))
                if datetime.now(timezone.utc) - sent_at > timedelta(minutes=10):
                    raise HTTPException(status_code=400, detail="인증 코드가 만료되었습니다.")
            except HTTPException:
                raise
            except Exception:
                pass
        now = _now_iso()
        supabase.table("users").update({
            "email_verified": True, "email_verified_at": now,
            "email_verify_token": None, "updated_at": now,
        }).eq("email", req.email).execute()
        return {"status": "success", "message": "이메일 인증이 완료되었습니다.",
                "data": {"email": req.email, "email_verified": True, "email_verified_at": now}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _probe_auth():
    sb = get_supabase()
    r = sb.table("users").select("id", count="exact").limit(1).execute()
    return {"users_count": r.count or 0}


register_probe(
    "auth",
    _probe_auth,
    critical=True,
    desc_ko="인증 서비스",
    meta={
        "impacts": [
            {"name": "로그인", "url": "https://safe.taieng.co.kr/html/horizontal-menu-template/auth-login-cover"},
            {"name": "회원가입", "page": "전체 인증"},
        ],
        "fix_links": [
            {"name": "Supabase Auth", "url": "https://supabase.com/dashboard/project/vwlahtguyggrhvslabax/auth/users"},
        ],
        "api": "POST /auth/login, POST /auth/token",
        "code": "routers/auth.py",
    },
)
