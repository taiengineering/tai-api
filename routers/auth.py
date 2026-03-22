# routers/auth.py
# 휴대폰 번호 기반 로그인
# - phone + password → users 테이블에서 email 조회 → Supabase Auth 로그인

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
    phone:        str                    # 휴대폰 번호 (로그인 아이디)
    email:        str                    # 이메일 (Supabase Auth용)
    password:     str
    name:         str
    role_code:    str = "002"
    company_name: Optional[str] = None
    company_type_code: Optional[str] = None

class LoginRequest(BaseModel):
    phone:    str                        # 휴대폰 번호로 로그인
    password: str

class FindPasswordRequest(BaseModel):
    phone: str                           # 휴대폰 번호로 비밀번호 찾기

class ResetPasswordRequest(BaseModel):
    email: str

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
# 헬퍼 함수
# ============================================================

def normalize_phone(phone: str) -> str:
    """휴대폰 번호 정규화 — 하이픈 제거, 숫자만"""
    return re.sub(r'[^0-9]', '', phone)

def get_user_from_token(token: str, supabase) -> dict:
    try:
        user_res = supabase.auth.get_user(token)
        if not user_res or not user_res.user:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다")
        return user_res.user
    except Exception:
        raise HTTPException(status_code=401, detail="토큰 검증 실패")

def get_users_row(auth_id: str, supabase) -> dict:
    res = supabase.table("users")\
        .select("*")\
        .eq("auth_id", auth_id)\
        .limit(1).execute()
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
    """
    회원가입
    - phone: 로그인 아이디 (중복 체크)
    - email: Supabase Auth 계정용 (내부 사용)
    """
    supabase = get_supabase()

    phone_normalized = normalize_phone(req.phone)

    # 휴대폰 번호 중복 체크
    existing = supabase.table("users")\
        .select("id")\
        .eq("phone", phone_normalized)\
        .limit(1).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="이미 가입된 휴대폰 번호입니다")

    # Supabase Auth 계정 생성 (이메일 기반 — 내부용)
    try:
        auth_res = supabase.auth.admin.create_user({
            "email":         req.email,
            "password":      req.password,
            "email_confirm": True,
            "user_metadata": {
                "name":      req.name,
                "phone":     phone_normalized,
                "role_code": req.role_code,
            }
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"계정 생성 실패: {str(e)}")

    if not auth_res.user:
        raise HTTPException(status_code=400, detail="회원가입 실패")

    auth_id = str(auth_res.user.id)

    # 회사 생성
    company_id = None
    if req.company_name:
        try:
            company_res = supabase.table("companies").insert({
                "name":              req.company_name,
                "company_type_code": req.company_type_code or "002",
                "status_code":       "TRIAL",
                "is_active":         True,
                "created_at":        datetime.now().isoformat(),
                "updated_at":        datetime.now().isoformat(),
            }).execute()
            company_id = company_res.data[0]["id"] if company_res.data else None
        except Exception:
            pass

    # users 테이블 생성
    try:
        user_res = supabase.table("users").insert({
            "auth_id":     auth_id,
            "email":       req.email,
            "phone":       phone_normalized,
            "name":        req.name,
            "username":    phone_normalized,   # username = 폰번호
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
        "status":  "success",
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
# 2. 로그인 (휴대폰 번호 기반)
# ============================================================

@router.post("/login")
def login(req: LoginRequest):
    """
    휴대폰 번호 + 비밀번호 로그인
    1. phone → users 테이블에서 email 조회
    2. email + password → Supabase Auth 로그인
    3. JWT 토큰 반환
    """
    supabase = get_supabase()

    phone_normalized = normalize_phone(req.phone)

    # 1. phone → email 조회
    user_row = supabase.table("users")\
        .select("id, email, name, phone, role_code, company_id, factory_id, status_code, profile_image_url")\
        .eq("phone", phone_normalized)\
        .limit(1).execute()

    if not user_row.data:
        raise HTTPException(status_code=401, detail="가입되지 않은 휴대폰 번호입니다")

    user = user_row.data[0]

    # 상태 체크
    status = user.get("status_code", "ACTIVE")
    if status == "SUSPENDED":
        raise HTTPException(status_code=403, detail="정지된 계정입니다. 관리자에게 문의해주세요")
    if status == "DELETED":
        raise HTTPException(status_code=403, detail="삭제된 계정입니다")
    if status == "INACTIVE":
        raise HTTPException(status_code=403, detail="비활성화된 계정입니다")

    # 2. Supabase Auth 로그인 (내부적으로 email 사용)
    try:
        auth_res = supabase.auth.sign_in_with_password({
            "email":    user["email"],
            "password": req.password,
        })
    except Exception:
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다")

    if not auth_res.user or not auth_res.session:
        raise HTTPException(status_code=401, detail="로그인 실패")

    # last_login_at 업데이트
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
                "phone":       user["phone"],
                "email":       user["email"],
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
# 4. 휴대폰 번호 중복 확인
# ============================================================

@router.post("/check-phone")
def check_phone(phone: str):
    """휴대폰 번호 중복 확인"""
    supabase = get_supabase()
    phone_normalized = normalize_phone(phone)

    res = supabase.table("users")\
        .select("id")\
        .eq("phone", phone_normalized)\
        .limit(1).execute()

    return {
        "status":    "success",
        "available": len(res.data) == 0,
        "message":   "사용 가능한 번호입니다" if not res.data else "이미 가입된 번호입니다"
    }


# ============================================================
# 5. 비밀번호 재설정 (휴대폰 번호로 이메일 찾아서 발송)
# ============================================================

@router.post("/reset-password")
def reset_password(req: FindPasswordRequest):
    """휴대폰 번호로 비밀번호 재설정 이메일 발송"""
    supabase = get_supabase()
    phone_normalized = normalize_phone(req.phone)

    res = supabase.table("users")\
        .select("email")\
        .eq("phone", phone_normalized)\
        .limit(1).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="가입되지 않은 휴대폰 번호입니다")

    email = res.data[0]["email"]

    try:
        supabase.auth.reset_password_email(email)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이메일 발송 실패: {str(e)}")

    # 이메일 마스킹
    parts = email.split("@")
    masked = parts[0][:2] + "**@" + parts[1] if len(parts) == 2 else email

    return {
        "status":  "success",
        "message": f"비밀번호 재설정 링크를 {masked}로 발송했습니다",
    }


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
            "email":       user["email"],
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

    res = supabase.table("users")\
        .update(update_data)\
        .eq("id", user["id"])\
        .execute()

    return {"status": "success", "data": res.data[0] if res.data else {}}


# ============================================================
# 9. 테스트
# ============================================================

@router.get("/test")
def test():
    return {"message": "auth router alive", "login_type": "phone"}
