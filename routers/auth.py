#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAI Auth 라우터
- Supabase Auth 기반 인증
- users 테이블 동기화
- 전역변수: user_status / user_role / service_site

엔드포인트:
POST /auth/register         회원가입
POST /auth/login            로그인
POST /auth/logout           로그아웃
POST /auth/find-id          아이디 찾기
POST /auth/reset-password   비밀번호 재설정 이메일 발송
POST /auth/verify-token     토큰 검증
GET  /auth/me               내 정보 조회
PATCH /auth/me              내 정보 수정
"""

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from db.supabase_client import get_supabase

router = APIRouter(prefix="/auth", tags=["auth"])


# ============================================================
# 요청/응답 스키마
# ============================================================

class RegisterRequest(BaseModel):
    email:        str
    password:     str
    name:         str
    phone:        Optional[str] = None
    username:     Optional[str] = None     # 로그인 아이디
    role_code:    str = "002"              # 기본: 관리자
    company_name: Optional[str] = None    # 회사명 (회원가입 시 회사 생성)
    company_type_code: Optional[str] = None  # company_type 전역변수

class LoginRequest(BaseModel):
    email:    str
    password: str

class FindIdRequest(BaseModel):
    name:  str
    phone: str

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
    # 주소
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

def get_user_from_token(token: str, supabase) -> dict:
    """토큰으로 Supabase Auth 사용자 조회"""
    try:
        user_res = supabase.auth.get_user(token)
        if not user_res or not user_res.user:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다")
        return user_res.user
    except Exception:
        raise HTTPException(status_code=401, detail="토큰 검증 실패")

def get_users_row(auth_id: str, supabase) -> dict:
    """auth_id로 users 테이블 조회"""
    res = supabase.table("users")\
        .select("*")\
        .eq("auth_id", auth_id)\
        .limit(1).execute()
    return res.data[0] if res.data else None

def generate_user_code() -> str:
    """사용자 코드 생성: USR-YYYYMMDD-XXXX"""
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
    1. Supabase Auth 계정 생성
    2. users 테이블 생성
    3. 회사명 있으면 companies 테이블 생성
    """
    supabase = get_supabase()

    # 1. Supabase Auth 계정 생성
    try:
        auth_res = supabase.auth.admin.create_user({
            "email":         req.email,
            "password":      req.password,
            "email_confirm": True,
            "user_metadata": {
                "name":      req.name,
                "role_code": req.role_code,
            }
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"계정 생성 실패: {str(e)}")

    if not auth_res.user:
        raise HTTPException(status_code=400, detail="회원가입 실패")

    auth_id = str(auth_res.user.id)

    # 2. 회사 생성 (회사명 있는 경우)
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
            pass  # 회사 생성 실패해도 계속 진행

    # 3. users 테이블 생성
    try:
        user_res = supabase.table("users").insert({
            "auth_id":     auth_id,
            "email":       req.email,
            "name":        req.name,
            "phone":       req.phone,
            "username":    req.username or req.email,
            "role_code":   req.role_code,
            "company_id":  company_id,
            "user_code":   generate_user_code(),
            "status_code": "PENDING",   # user_status: 승인대기
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
        "message": "회원가입이 완료됐습니다. 이메일 인증 후 로그인해주세요.",
        "data": {
            "user_id":    user_res.data[0]["id"],
            "email":      req.email,
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
    로그인
    1. Supabase Auth 로그인
    2. users 테이블 last_login_at 업데이트
    3. JWT 토큰 반환
    """
    supabase = get_supabase()

    # Supabase Auth 로그인
    try:
        auth_res = supabase.auth.sign_in_with_password({
            "email":    req.email,
            "password": req.password,
        })
    except Exception as e:
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다")

    if not auth_res.user or not auth_res.session:
        raise HTTPException(status_code=401, detail="로그인 실패")

    auth_id = str(auth_res.user.id)

    # users 테이블 조회
    user = get_users_row(auth_id, supabase)
    if not user:
        raise HTTPException(status_code=404, detail="사용자 정보를 찾을 수 없습니다")

    # 상태 체크 (user_status 전역변수)
    status = user.get("status_code", "ACTIVE")
    if status == "SUSPENDED":
        raise HTTPException(status_code=403, detail="정지된 계정입니다. 관리자에게 문의해주세요")
    if status == "DELETED":
        raise HTTPException(status_code=403, detail="삭제된 계정입니다")
    if status == "INACTIVE":
        raise HTTPException(status_code=403, detail="비활성화된 계정입니다")

    # last_login_at 업데이트
    supabase.table("users")\
        .update({"last_login_at": datetime.now().isoformat()})\
        .eq("auth_id", auth_id)\
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
    """로그아웃 — Supabase Auth 세션 종료"""
    supabase = get_supabase()
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    return {"status": "success", "message": "로그아웃됐습니다"}


# ============================================================
# 4. 아이디 찾기
# ============================================================

@router.post("/find-id")
def find_id(req: FindIdRequest):
    """이름 + 전화번호로 이메일 찾기"""
    supabase = get_supabase()

    res = supabase.table("users")\
        .select("email, name, created_at")\
        .eq("name", req.name)\
        .eq("phone", req.phone)\
        .execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="일치하는 회원 정보를 찾을 수 없습니다")

    user = res.data[0]
    email = user["email"]

    # 이메일 마스킹: test@example.com → te**@example.com
    parts = email.split("@")
    masked = parts[0][:2] + "**" + "@" + parts[1] if len(parts) == 2 else email

    return {
        "status": "success",
        "data": {
            "email_masked": masked,
            "name":         user["name"],
            "created_at":   user["created_at"],
        }
    }


# ============================================================
# 5. 비밀번호 재설정 이메일 발송
# ============================================================

@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest):
    """비밀번호 재설정 이메일 발송"""
    supabase = get_supabase()

    # 이메일 존재 여부 확인
    res = supabase.table("users")\
        .select("id")\
        .eq("email", req.email)\
        .limit(1).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="등록된 이메일이 없습니다")

    # Supabase Auth 비밀번호 재설정 이메일 발송
    try:
        supabase.auth.reset_password_email(req.email)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이메일 발송 실패: {str(e)}")

    return {
        "status":  "success",
        "message": f"비밀번호 재설정 링크를 {req.email}로 발송했습니다",
    }


# ============================================================
# 6. 토큰 검증
# ============================================================

@router.post("/verify-token")
def verify_token(authorization: Optional[str] = Header(None)):
    """JWT 토큰 검증 및 사용자 정보 반환"""
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
    """내 정보 조회"""
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
def update_me(req: UpdateMeRequest,
              authorization: Optional[str] = Header(None)):
    """내 정보 수정"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="토큰이 없습니다")

    token = authorization.replace("Bearer ", "")
    supabase = get_supabase()

    auth_user = get_user_from_token(token, supabase)
    user = get_users_row(str(auth_user.id), supabase)

    if not user:
        raise HTTPException(status_code=404, detail="사용자 정보를 찾을 수 없습니다")

    # 변경된 필드만 업데이트
    update_data = {k: v for k, v in req.dict().items() if v is not None}
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
    return {"message": "auth router alive"}
