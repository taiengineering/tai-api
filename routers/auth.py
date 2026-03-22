# routers/auth.py
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from db.supabase_client import get_supabase
import re

router = APIRouter(prefix="/auth", tags=["auth"])


# ============================================================
# 요청 스키마
# ============================================================

class RegisterRequest(BaseModel):
    phone:        str
    email:        str
    password:     str
    name:         str
    role_code:    str = "002"
    company_name: Optional[str] = None
    company_type_code: Optional[str] = None

class LoginRequest(BaseModel):
    """
    login_id: 이메일 또는 전화번호 (통합 필드)
    password: 비밀번호
    ---
    phone / email 개별 필드도 하위 호환으로 지원
    """
    login_id:  Optional[str] = None   # 이메일 또는 전화번호 통합
    phone:     Optional[str] = None   # 하위 호환
    email:     Optional[str] = None   # 하위 호환
    password:  str

class FindPasswordRequest(BaseModel):
    phone: str

class UpdateMeRequest(BaseModel):
    name:           Optional[str] = None
    phone:          Optional[str] = None
    department:     Optional[str] = None
    position:       Optional[str] = None
    profile_image_url: Optional[str] = None
    allow_push:     Optional[bool] = None
    allow_sms:      Optional[bool] = None
    allow_email:    Optional[bool] = None
    allow_kakao:    Optional[bool] = None
    zipcode:        Optional[str] = None
    address_road:   Optional[str] = None
    address_jibun:  Optional[str] = None
    address_detail: Optional[str] = None
    address_sido:   Optional[str] = None
    address_sigungu: Optional[str] = None
    address_dong:   Optional[str] = None


# ============================================================
# 헬퍼
# ============================================================

def normalize_phone(phone: str) -> str:
    return re.sub(r'[^0-9]', '', phone)

def is_email(value: str) -> bool:
    return "@" in value

def get_user_from_token(token: str, supabase):
    try:
        user_res = supabase.auth.get_user(token)
        if not user_res or not user_res.user:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다")
        return user_res.user
    except Exception:
        raise HTTPException(status_code=401, detail="토큰 검증 실패")

def get_users_row(auth_id: str, supabase):
    res = supabase.table("users").select("*").eq("auth_id", auth_id).limit(1).execute()
    return res.data[0] if res.data else None

def generate_user_code() -> str:
    now = datetime.now().strftime("%Y%m%d")
    import random, string
    suffix = ''.join(random.choices(string.digits, k=4))
    return f"USR-{now}-{suffix}"


# ============================================================
# 1. 회원가입
# ============================================================

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
            company_res = supabase.table("companies").insert({
                "name": req.company_name,
                "company_type_code": req.company_type_code or "002",
                "status_code": "TRIAL",
                "is_active": True,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }).execute()
            company_id = company_res.data[0]["id"] if company_res.data else None
        except Exception:
            pass

    try:
        user_res = supabase.table("users").insert({
            "auth_id":     auth_id,
            "email":       req.email,
            "phone":       phone_normalized,
            "name":        req.name,
            "username":    phone_normalized,
            "role_code":   req.role_code,
            "company_id":  company_id,
            "user_code":   generate_user_code(),
            "status_code": "PENDING",
            "is_active":   False,
            "allow_push":  True,
            "allow_sms":   True,
            "allow_email": True,
            "allow_kakao": False,
            "created_at":  datetime.now().isoformat(),
            "updated_at":  datetime.now().isoformat(),
        }).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"사용자 정보 저장 실패: {str(e)}")

    return {
        "status": "success",
        "message": "회원가입이 완료됐습니다.",
        "data": {
            "user_id":    user_res.data[0]["id"],
            "phone":      phone_normalized,
            "name":       req.name,
            "role_code":  req.role_code,
            "company_id": company_id,
        }
    }


# ============================================================
# 2. 로그인
# ============================================================

@router.post("/login")
def login(req: LoginRequest):
    """
    로그인 — 아래 중 하나로 요청:

    방법1) login_id 통합 필드 사용 (권장):
      { "login_id": "hetto@kakao.com", "password": "..." }
      { "login_id": "01047758888",     "password": "..." }

    방법2) 개별 필드 사용 (하위 호환):
      { "email": "hetto@kakao.com", "password": "..." }
      { "phone": "01047758888",     "password": "..." }
    """
    supabase = get_supabase()

    # login_id 통합 처리
    identifier = req.login_id or req.email or req.phone
    if not identifier:
        raise HTTPException(status_code=400, detail="login_id (이메일 또는 전화번호)가 필요합니다")

    # 이메일 vs 전화번호 판별
    if is_email(identifier):
        user_row = supabase.table("users")\
            .select("id, email, name, phone, role_code, company_id, factory_id, status_code, profile_image_url, auth_id")\
            .eq("email", identifier)\
            .eq("status_code", "ACTIVE")\
            .limit(1).execute()
        if not user_row.data:
            raise HTTPException(status_code=401, detail="가입되지 않은 이메일입니다")
    else:
        phone_normalized = normalize_phone(identifier)
        user_row = supabase.table("users")\
            .select("id, email, name, phone, role_code, company_id, factory_id, status_code, profile_image_url, auth_id")\
            .eq("phone", phone_normalized)\
            .eq("status_code", "ACTIVE")\
            .limit(1).execute()
        if not user_row.data:
            raise HTTPException(status_code=401, detail="가입되지 않은 휴대폰 번호입니다")

    user = user_row.data[0]

    status = user.get("status_code", "ACTIVE")
    if status == "SUSPENDED":
        raise HTTPException(status_code=403, detail="정지된 계정입니다")
    if status == "DELETED":
        raise HTTPException(status_code=403, detail="삭제된 계정입니다")
    if status == "INACTIVE":
        raise HTTPException(status_code=403, detail="비활성화된 계정입니다")

    login_email = user.get("email")

    if login_email:
        # 이메일 기반 Supabase Auth 로그인
        try:
            auth_res = supabase.auth.sign_in_with_password({
                "email":    login_email,
                "password": req.password,
            })
        except Exception:
            raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다")
    else:
        # 전화번호 전용 계정 — phone sign_in 시도
        try:
            phone_val = user.get("phone", "")
            if not phone_val.startswith("+"):
                phone_val = "+82" + phone_val.lstrip("0")
            auth_res = supabase.auth.sign_in_with_password({
                "phone":    phone_val,
                "password": req.password,
            })
        except Exception:
            raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다")

    if not auth_res.user or not auth_res.session:
        raise HTTPException(status_code=401, detail="로그인 실패")

    supabase.table("users")\
        .update({"last_login_at": datetime.now().isoformat()})\
        .eq("id", user["id"])\
        .execute()

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


# ============================================================
# 3. 로그아웃
# ============================================================

@router.post("/logout")
def logout(authorization: Optional[str] = Header(None)):
    supabase = get_supabase()
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    return {"status": "success", "message": "로그아웃됐습니다"}


# ============================================================
# 4. 전화번호 중복 확인
# ============================================================

@router.post("/check-phone")
def check_phone(phone: str):
    supabase = get_supabase()
    phone_normalized = normalize_phone(phone)
    res = supabase.table("users").select("id").eq("phone", phone_normalized).limit(1).execute()
    return {
        "status":    "success",
        "available": len(res.data) == 0,
        "message":   "사용 가능한 번호입니다" if not res.data else "이미 가입된 번호입니다"
    }


# ============================================================
# 5. 비밀번호 재설정
# ============================================================

@router.post("/reset-password")
def reset_password(req: FindPasswordRequest):
    supabase = get_supabase()
    phone_normalized = normalize_phone(req.phone)
    res = supabase.table("users").select("email").eq("phone", phone_normalized).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="가입되지 않은 휴대폰 번호입니다")
    email = res.data[0]["email"]
    try:
        supabase.auth.reset_password_email(email)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이메일 발송 실패: {str(e)}")
    parts = email.split("@")
    masked = parts[0][:2] + "**@" + parts[1] if len(parts) == 2 else email
    return {"status": "success", "message": f"재설정 링크를 {masked}로 발송했습니다"}


# ============================================================
# 6. 토큰 검증
# ============================================================

@router.post("/verify-token")
def verify_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="토큰이 없습니다")
    token = authorization.replace("Bearer ", "")
    supabase = get_supabase()
    auth_user = get_user_from_token(token, supabase)
    user = get_users_row(str(auth_user.id), supabase)
    if not user:
        raise HTTPException(status_code=404, detail="사용자 정보를 찾을 수 없습니다")
    return {
        "status": "success",
        "data": {
            "id":          user["id"],
            "phone":       user.get("phone"),
            "email":       user.get("email"),
            "name":        user["name"],
            "role_code":   user["role_code"],
            "company_id":  user.get("company_id"),
            "factory_id":  user.get("factory_id"),
            "status_code": user.get("status_code"),
        }
    }


# ============================================================
# 7. 내 정보 조회
# ============================================================

@router.get("/me")
def get_me(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="토큰이 없습니다")
    token = authorization.replace("Bearer ", "")
    supabase = get_supabase()
    auth_user = get_user_from_token(token, supabase)
    user = get_users_row(str(auth_user.id), supabase)
    if not user:
        raise HTTPException(status_code=404, detail="사용자 정보를 찾을 수 없습니다")
    return {"status": "success", "data": user}


# ============================================================
# 8. 내 정보 수정
# ============================================================

@router.patch("/me")
def update_me(req: UpdateMeRequest, authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="토큰이 없습니다")
    token = authorization.replace("Bearer ", "")
    supabase = get_supabase()
    auth_user = get_user_from_token(token, supabase)
    user = get_users_row(str(auth_user.id), supabase)
    if not user:
        raise HTTPException(status_code=404, detail="사용자 정보를 찾을 수 없습니다")
    update_data = {k: v for k, v in req.dict().items() if v is not None}
    if "phone" in update_data:
        update_data["phone"] = normalize_phone(update_data["phone"])
    update_data["updated_at"] = datetime.now().isoformat()
    res = supabase.table("users").update(update_data).eq("id", user["id"]).execute()
    return {"status": "success", "data": res.data[0] if res.data else {}}


# ============================================================
# 9. 테스트
# ============================================================

@router.get("/test")
def test():
    return {"message": "auth router alive", "login_type": "login_id (email or phone)"}
