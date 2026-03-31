#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAI Users 라우터 - 회원 관리
전역변수: user_role / user_status / service_site

엔드포인트:
GET    /users                회원 목록 조회
POST   /users                회원 등록 (어드민용)
GET    /users/{id}           회원 상세 조회
PATCH  /users/{id}           회원 정보 수정
DELETE /users/{id}           회원 비활성화 + 담당 일정 미배정 처리 (v2.0.0)
PATCH  /users/{id}/status    회원 상태 변경 + 비활성화 시 일정 미배정 처리 (v2.0.0)
PATCH  /users/{id}/role      회원 역할 변경
GET    /users/{id}/factories 담당 시설 목록
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from db.supabase_client import get_supabase

router = APIRouter(prefix="/users", tags=["users"])

VERSION = "2.0.0"

# 비활성화 상태 코드: 이 상태로 변경 시 work_schedules 미배정 처리
DEACTIVATE_STATUSES = {"INACTIVE", "DELETED", "SUSPENDED"}


# ============================================================
# 스키마
# ============================================================

class UserCreate(BaseModel):
    email:      str
    name:       str
    role_code:  str = "004"
    company_id: Optional[str] = None
    factory_id: Optional[str] = None
    team_id:    Optional[str] = None
    phone:          Optional[str] = None
    username:       Optional[str] = None
    department:     Optional[str] = None
    position:       Optional[str] = None
    profile_image_url: Optional[str] = None
    zipcode:        Optional[str] = None
    address_road:   Optional[str] = None
    address_jibun:  Optional[str] = None
    address_detail: Optional[str] = None
    address_sido:   Optional[str] = None
    address_sigungu: Optional[str] = None
    address_dong:   Optional[str] = None
    allow_push:  bool = True
    allow_sms:   bool = True
    allow_email: bool = True
    allow_kakao: bool = False


class UserUpdate(BaseModel):
    name:           Optional[str] = None
    phone:          Optional[str] = None
    username:       Optional[str] = None
    department:     Optional[str] = None
    position:       Optional[str] = None
    profile_image_url: Optional[str] = None
    company_id:     Optional[str] = None
    factory_id:     Optional[str] = None
    team_id:        Optional[str] = None
    zipcode:        Optional[str] = None
    address_road:   Optional[str] = None
    address_jibun:  Optional[str] = None
    address_detail: Optional[str] = None
    address_sido:   Optional[str] = None
    address_sigungu: Optional[str] = None
    address_dong:   Optional[str] = None
    allow_push:     Optional[bool] = None
    allow_sms:      Optional[bool] = None
    allow_email:    Optional[bool] = None
    allow_kakao:    Optional[bool] = None


class StatusUpdate(BaseModel):
    status_code: str  # user_status: ACTIVE/INACTIVE/SUSPENDED/DELETED/PENDING


class RoleUpdate(BaseModel):
    role_code: str


# ============================================================
# 내부 헬퍼: 퇴사 후 work_schedules 미배정 처리
# ============================================================

def _unassign_user_schedules(supabase, user_id: str) -> int:
    """
    해당 유저의 SCHEDULED 상태 일정을 assigned_user_id=NULL로 일괄 업데이트.
    일정 자체는 SCHEDULED 유지 (삭제 금지).
    반환: 미배정 처리된 일정 수
    """
    try:
        res = supabase.table("work_schedules").update(
            {"assigned_user_id": None}
        ).eq("assigned_user_id", user_id).eq(
            "status_code", "SCHEDULED"
        ).execute()
        return len(res.data or [])
    except Exception as e:
        print(f"[USERS] work_schedules 미배정 처리 실패 (user_id={user_id}): {e}")
        return 0


# ============================================================
# 1. 회원 목록 조회
# ============================================================

@router.get("")
def get_users(
    page:        int  = Query(default=1, ge=1),
    size:        int  = Query(default=20, ge=1, le=100),
    search:      Optional[str] = Query(default=None),
    company_id:  Optional[str] = Query(default=None),
    factory_id:  Optional[str] = Query(default=None),
    role_code:   Optional[str] = Query(default=None),
    status_code: Optional[str] = Query(default=None),
):
    supabase = get_supabase()
    query = supabase.table("users").select("*", count="exact")

    if search:      query = query.or_(f"name.ilike.%{search}%,email.ilike.%{search}%")
    if company_id:  query = query.eq("company_id", company_id)
    if factory_id:  query = query.eq("factory_id", factory_id)
    if role_code:   query = query.eq("role_code", role_code)
    if status_code: query = query.eq("status_code", status_code)

    offset = (page - 1) * size
    res = query.order("created_at", desc=True).range(offset, offset + size - 1).execute()

    return {
        "status": "success",
        "data": {
            "items":       res.data,
            "total":       res.count,
            "page":        page,
            "size":        size,
            "total_pages": -(-res.count // size) if res.count else 0,
        }
    }


# ============================================================
# 2. 회원 등록 (어드민용)
# ============================================================

@router.post("")
def create_user(req: UserCreate):
    supabase = get_supabase()

    dup = supabase.table("users").select("id").eq("email", req.email).limit(1).execute()
    if dup.data:
        raise HTTPException(status_code=400, detail="이미 등록된 이메일입니다")

    if req.username:
        dup = supabase.table("users").select("id").eq("username", req.username).limit(1).execute()
        if dup.data:
            raise HTTPException(status_code=400, detail="이미 사용 중인 아이디입니다")

    now = datetime.now()
    user_code = f"USR-{now.strftime('%Y%m%d%H%M%S')}"

    data = {
        **req.dict(exclude_none=True),
        "user_code":   user_code,
        "status_code": "PENDING",
        "is_active":   False,
        "created_at":  now.isoformat(),
        "updated_at":  now.isoformat(),
    }

    res = supabase.table("users").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="회원 등록 실패")

    return {"status": "success", "message": "회원이 등록됐습니다", "data": res.data[0]}


# ============================================================
# 3. 회원 상세 조회
# ============================================================

@router.get("/{user_id}")
def get_user(user_id: str):
    supabase = get_supabase()
    res = supabase.table("users").select("*").eq("id", user_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다")
    return {"status": "success", "data": res.data}


# ============================================================
# 4. 회원 정보 수정
# ============================================================

@router.patch("/{user_id}")
def update_user(user_id: str, req: UserUpdate):
    supabase = get_supabase()

    existing = supabase.table("users").select("id").eq("id", user_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다")

    update_data = {k: v for k, v in req.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now().isoformat()

    res = supabase.table("users").update(update_data).eq("id", user_id).execute()

    return {
        "status":  "success",
        "message": "회원 정보가 수정됐습니다",
        "data":    res.data[0] if res.data else {},
    }


# ============================================================
# 5. 회원 비활성화 (v2.0.0: 담당 SCHEDULED 일정 미배정 처리)
# ============================================================

@router.delete("/{user_id}")
def delete_user(user_id: str):
    supabase = get_supabase()

    existing = supabase.table("users").select("id").eq("id", user_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다")

    # users 비활성화
    supabase.table("users").update({
        "is_active":   False,
        "status_code": "DELETED",
        "updated_at":  datetime.now().isoformat(),
    }).eq("id", user_id).execute()

    # 담당 SCHEDULED 일정 미배정 처리
    unassigned = _unassign_user_schedules(supabase, user_id)

    return {
        "status":  "success",
        "message": "회원이 비활성화됐습니다",
        "data":    {"unassigned_schedules": unassigned},
    }


# ============================================================
# 6. 회원 상태 변경 (v2.0.0: INACTIVE/DELETED/SUSPENDED 시 일정 미배정)
# ============================================================

@router.patch("/{user_id}/status")
def update_user_status(user_id: str, req: StatusUpdate):
    """user_status: ACTIVE/INACTIVE/SUSPENDED/DELETED/PENDING"""
    supabase = get_supabase()

    existing = supabase.table("users").select("id").eq("id", user_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다")

    is_active = (req.status_code == "ACTIVE")
    supabase.table("users").update({
        "status_code": req.status_code,
        "is_active":   is_active,
        "updated_at":  datetime.now().isoformat(),
    }).eq("id", user_id).execute()

    # 비활성화 상태인 경우 담당 일정 미배정 처리
    unassigned = 0
    if req.status_code in DEACTIVATE_STATUSES:
        unassigned = _unassign_user_schedules(supabase, user_id)

    return {
        "status":  "success",
        "message": f"회원 상태가 변경됐습니다 ({req.status_code})",
        "data":    {"unassigned_schedules": unassigned},
    }


# ============================================================
# 7. 회원 역할 변경 (어드민용)
# ============================================================

@router.patch("/{user_id}/role")
def update_user_role(user_id: str, req: RoleUpdate):
    """user_role: 001=최고관리자/002=관리자/003=안전관리자/004=작업자
       005=협력업체관리자/006=협력업체작업자/007=점검자/008=승인자"""
    supabase = get_supabase()

    existing = supabase.table("users").select("id").eq("id", user_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다")

    valid = supabase.table("system_codes").select("code").eq("category", "user_role")\
        .eq("code", req.role_code).limit(1).execute()
    if not valid.data:
        raise HTTPException(status_code=400, detail="유효하지 않은 역할 코드입니다")

    supabase.table("users").update({
        "role_code":  req.role_code,
        "updated_at": datetime.now().isoformat(),
    }).eq("id", user_id).execute()

    return {"status": "success", "message": f"회원 역할이 변경됐습니다 ({req.role_code})"}


# ============================================================
# 8. 담당 시설 목록
# ============================================================

@router.get("/{user_id}/factories")
def get_user_factories(user_id: str):
    supabase = get_supabase()

    user = supabase.table("users").select("factory_id, company_id")\
        .eq("id", user_id).single().execute()
    if not user.data:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다")

    company_id = user.data.get("company_id")
    if not company_id:
        return {"status": "success", "data": {"items": [], "total": 0}}

    res = supabase.table("factories").select(
        "id, name, site_type, address_road, employee_count, status_code"
    ).eq("company_id", company_id).order("created_at", desc=True).execute()

    return {"status": "success", "data": {"items": res.data, "total": len(res.data)}}
