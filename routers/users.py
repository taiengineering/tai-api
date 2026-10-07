#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAI Users 라우터 - 회원 관리 v2.3.1

v2.3.1: get_users 데모제외를 어드민 전체목록에만 적용
  - factory_id 지정 조회(담당자 드롭다운)에서 company_id 없을 때 데모 사용자가 neq 제외되던 결함 수정
v2.3.0: 목록 size 상한 100→500 (LEDGER §68)
  - 대시보드 담당자 목록이 GET /users?size=200 을 보내 le=100 위반으로 422 → 담당자 열·배정
    셀렉트가 빈다. factory_id 로 좁힌 목록이라 테넌트당 인원이 유한하므로 상한만 상향.
v2.2.0: 어드민 전체목록(get_users, company_id 미지정)에서 데모(체험) 테넌트 사용자 제외
  - 데모 회사(is_demo) 소속 사용자 id 를 조회해 목록에서 neq 로 제외(회사 스코프 조회 시엔 유지)
v2.1.0: APPOINTMENT 이벤트 트리거 추가
  - PATCH /users/{id}/role 에서 role_code='002' 설정 시 + factory_id 있으면
    trigger_event_schedules(APPOINTMENT) 자동 호출
v2.0.0: 퍼사자 일정 미배정 처리
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date
from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.time import business_today, now_kst, serialize_business_datetime
from services.document_signature_svc import (
    SignatureError,
    get_profile_signature,
    save_profile_signature,
)

router = APIRouter(prefix="/users", tags=["users"])

VERSION = "2.3.1"

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
    status_code: str


class RoleUpdate(BaseModel):
    role_code: str


# ============================================================
# 내부 헬퍼
# ============================================================

def _unassign_user_schedules(supabase, user_id: str) -> int:
    """퍼사자의 SCHEDULED 일정을 assigned_user_id=NULL로 처리."""
    try:
        res = supabase.table("work_schedules").update(
            {"assigned_user_id": None}
        ).eq("assigned_user_id", user_id).eq("status_code", "SCHEDULED").execute()
        return len(res.data or [])
    except Exception as e:
        print(f"[USERS] work_schedules 미배정 실패 (user_id={user_id}): {e}")
        return 0


def _demo_user_ids(supabase) -> list:
    """데모(체험) 회사에 소속된 사용자 id 목록. 어드민 전체목록 제외용."""
    try:
        co = supabase.table("companies").select("id").eq("is_demo", True).execute()
        cids = [c["id"] for c in (co.data or [])]
        if not cids:
            return []
        us = supabase.table("users").select("id").in_("company_id", cids).execute()
        return [u["id"] for u in (us.data or [])]
    except Exception as e:
        print(f"[USERS] 데모 사용자 조회 실패: {e}")
        return []


def _enrich_user_rows(supabase, items: list) -> list:
    """회원관리 목록 표시용 라벨을 FK 기준으로 병합한다.

    기존 /users 소비자는 raw 컬럼을 그대로 사용하므로 원본 필드는 보존하고,
    admin member-list 가 기대하는 role_name/company_name/factory_name/status_name 만
    additive 하게 추가한다.
    """
    if not items:
        return []

    role_codes = list({r.get("role_code") for r in items if r.get("role_code")})
    company_ids = list({r.get("company_id") for r in items if r.get("company_id")})
    factory_ids = list({r.get("factory_id") for r in items if r.get("factory_id")})
    status_codes = list({r.get("status_code") for r in items if r.get("status_code")})

    role_map = {}
    if role_codes:
        rows = (
            supabase.table("roles")
            .select("role_code,role_name")
            .in_("role_code", role_codes)
            .execute()
            .data
        ) or []
        role_map = {r.get("role_code"): r.get("role_name") for r in rows}

    company_map = {}
    if company_ids:
        rows = (
            supabase.table("companies")
            .select("id,name")
            .in_("id", company_ids)
            .execute()
            .data
        ) or []
        company_map = {r.get("id"): r.get("name") for r in rows}

    factory_map = {}
    if factory_ids:
        rows = (
            supabase.table("factories")
            .select("id,name")
            .in_("id", factory_ids)
            .execute()
            .data
        ) or []
        factory_map = {r.get("id"): r.get("name") for r in rows}

    status_map = {}
    if status_codes:
        rows = (
            supabase.table("system_codes")
            .select("code,code_name")
            .eq("category", "user_status")
            .in_("code", status_codes)
            .execute()
            .data
        ) or []
        status_map = {r.get("code"): r.get("code_name") for r in rows}

    out = []
    for row in items:
        item = dict(row)
        role_code = item.get("role_code")
        company_id = item.get("company_id")
        factory_id = item.get("factory_id")
        status_code = item.get("status_code")
        item["role_name"] = role_map.get(role_code)
        item["company_name"] = company_map.get(company_id)
        item["factory_name"] = factory_map.get(factory_id)
        item["status"] = status_code
        item["status_name"] = status_map.get(status_code)
        out.append(item)
    return out


# ============================================================
# 1. 회원 목록
#    company_id·factory_id 둘 다 미지정(어드민 전체목록)이면 데모 테넌트 사용자 제외.
#    NULL company_id(내부 계정 등) 보존 위해 company_id 필터 대신 사용자 id neq 사용.
# ============================================================

@router.get("")
def get_users(
    page:        int  = Query(default=1, ge=1),
    size:        int  = Query(default=20, ge=1, le=500),
    search:      Optional[str] = Query(default=None),
    company_id:  Optional[str] = Query(default=None),
    factory_id:  Optional[str] = Query(default=None),
    role_code:   Optional[str] = Query(default=None),
    status_code: Optional[str] = Query(default=None),
    # admin-vue3 member-list 호환 별칭. canonical 파라미터가 있으면 canonical 우선.
    keyword:     Optional[str] = Query(default=None),
    role:        Optional[str] = Query(default=None),
    status:      Optional[str] = Query(default=None),
):
    supabase = get_supabase()

    effective_search = search or keyword
    effective_role = role_code or role
    effective_status = status_code or status

    query = supabase.table("users").select("*", count="exact")
    if not company_id and not factory_id:
        for uid in _demo_user_ids(supabase):
            query = query.neq("id", uid)
    if effective_search:
        query = query.or_(f"name.ilike.%{effective_search}%,email.ilike.%{effective_search}%")
    if company_id:       query = query.eq("company_id", company_id)
    if factory_id:       query = query.eq("factory_id", factory_id)
    if effective_role:   query = query.eq("role_code", effective_role)
    if effective_status: query = query.eq("status_code", effective_status)
    offset = (page - 1) * size
    res = query.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    items = _enrich_user_rows(supabase, res.data or [])
    return {
        "status": "success",
        "data": {
            "items":       items,
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
    now = now_kst()
    data = {
        **req.dict(exclude_none=True),
        "user_code":   f"USR-{now.strftime('%Y%m%d%H%M%S')}",
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
    update_data["updated_at"] = serialize_business_datetime(now_kst())
    res = supabase.table("users").update(update_data).eq("id", user_id).execute()
    return {"status": "success", "message": "회원 정보가 수정됐습니다", "data": res.data[0] if res.data else {}}


# ============================================================
# 5. 회원 비활성화 (v2.0.0: 담당 SCHEDULED 일정 미배정)
# ============================================================

@router.delete("/{user_id}")
def delete_user(user_id: str):
    supabase = get_supabase()
    existing = supabase.table("users").select("id").eq("id", user_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다")
    supabase.table("users").update({
        "is_active":   False,
        "status_code": "DELETED",
        "updated_at":  serialize_business_datetime(now_kst()),
    }).eq("id", user_id).execute()
    unassigned = _unassign_user_schedules(supabase, user_id)
    return {"status": "success", "message": "회원이 비활성화됐습니다", "data": {"unassigned_schedules": unassigned}}


# ============================================================
# 6. 회원 상태 변경 (v2.0.0)
# ============================================================

@router.patch("/{user_id}/status")
def update_user_status(user_id: str, req: StatusUpdate):
    supabase = get_supabase()
    existing = supabase.table("users").select("id").eq("id", user_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다")
    is_active = (req.status_code == "ACTIVE")
    supabase.table("users").update({
        "status_code": req.status_code,
        "is_active":   is_active,
        "updated_at":  serialize_business_datetime(now_kst()),
    }).eq("id", user_id).execute()
    unassigned = 0
    if req.status_code in DEACTIVATE_STATUSES:
        unassigned = _unassign_user_schedules(supabase, user_id)
    return {
        "status":  "success",
        "message": f"회원 상태가 변경됐습니다 ({req.status_code})",
        "data":    {"unassigned_schedules": unassigned},
    }


# ============================================================
# 7. 회원 역할 변경 (v2.1.0: APPOINTMENT 트리거 추가)
# ============================================================

@router.patch("/{user_id}/role")
async def update_user_role(user_id: str, req: RoleUpdate):
    """
    v2.1.0: role_code='002'(안전관리자) 설정 시 factory_id 있으면
    APPOINTMENT 이벤트 트리거 자동 호출.
    """
    supabase = get_supabase()

    user_res = supabase.table("users").select(
        "id, role_code, factory_id"
    ).eq("id", user_id).single().execute()
    if not user_res.data:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다")

    valid = supabase.table("system_codes").select("code").eq(
        "category", "user_role"
    ).eq("code", req.role_code).limit(1).execute()
    if not valid.data:
        raise HTTPException(status_code=400, detail="유효하지 않은 역할 코드입니다")

    supabase.table("users").update({
        "role_code":  req.role_code,
        "updated_at": serialize_business_datetime(now_kst()),
    }).eq("id", user_id).execute()

    # APPOINTMENT 트리거: role_code='002'(안전관리자) + factory_id 있으면
    factory_id = user_res.data.get("factory_id")
    if req.role_code == "002" and factory_id:
        try:
            from routers.event_trigger import trigger_event_schedules
            await trigger_event_schedules(
                factory_id = factory_id,
                event_type = "APPOINTMENT",
                event_date = business_today(),
                context    = {"assigned_user_id": user_id},
            )
        except Exception as e:
            print(f"[USERS] APPOINTMENT 트리거 실패 (user={user_id}): {e}")

    return {"status": "success", "message": f"회원 역할이 변경됐습니다 ({req.role_code})"}


# ============================================================
# 8. 담당 시설 목록
# ============================================================

@router.get("/{user_id}/factories")
def get_user_factories(user_id: str):
    supabase = get_supabase()
    user = supabase.table("users").select(
        "factory_id, company_id"
    ).eq("id", user_id).single().execute()
    if not user.data:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다")
    company_id = user.data.get("company_id")
    if not company_id:
        return {"status": "success", "data": {"items": [], "total": 0}}
    res = supabase.table("factories").select(
        "id, name, site_type, address_road, employee_count, status_code"
    ).eq("company_id", company_id).order("created_at", desc=True).execute()
    return {"status": "success", "data": {"items": res.data, "total": len(res.data)}}


# ============================================================
# 9. Profile Signature (OBJ02-C2-SIG-B)
# ============================================================

class SignatureBody(BaseModel):
    signature_data: str  # data:image/png;base64,...


@router.post("/{user_id}/signature")
def register_signature(
    user_id: str,
    body: SignatureBody,
    current_user: dict = Depends(get_current_user),
):
    """Profile signature 등록. path user_id == authenticated user 전용."""
    auth_id = str(current_user.get("id") or "").strip()
    if not auth_id:
        raise HTTPException(401, "authenticated user identity unavailable")
    if user_id != auth_id:
        raise HTTPException(403, "cross-user signature registration forbidden")
    try:
        result = save_profile_signature(auth_id, body.signature_data)
        return {"status": "success", "data": result}
    except SignatureError as e:
        raise HTTPException(400, str(e))


@router.get("/{user_id}/signature")
def get_signature(
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Profile signature 조회. path user_id == authenticated user 전용."""
    auth_id = str(current_user.get("id") or "").strip()
    if not auth_id:
        raise HTTPException(401, "authenticated user identity unavailable")
    if user_id != auth_id:
        raise HTTPException(403, "cross-user signature read forbidden")
    try:
        result = get_profile_signature(auth_id)
        if result is None:
            raise HTTPException(404, "no profile signature registered")
        return {"status": "success", "data": result}
    except SignatureError as e:
        raise HTTPException(400, str(e))
