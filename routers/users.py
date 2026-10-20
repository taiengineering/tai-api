#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAI Users 라우터 - 회원 관리 v2.5.0

v2.5.0: 인가·회사범위·민감정보 통제 강화 (WO-TAI-API-SEC-DATA-READ-001-R2)
  - role_permissions DB 기반 USER_VIEW/CREATE/UPDATE/DELETE 인가 검증
  - 비어드민: JWT company_id 강제 (타사 접근 404 차단, company_id=None → 빈결과)
  - PATCH /role: 고권한 역할(_HIGH_PRIVILEGE_ROLES) 변경 최고관리자(001)만 허용
                 자기 역할 상승 금지
  - POST /users: 비어드민 company_id 강제, 고권한 role 부여 금지
  - PATCH /{id}: 비어드민 company_id 필드 변경 차단
  - wildcard-select 제거 → _USER_PUBLIC_COLS (password_hash 등 민감 컬럼 제외)
v2.4.0: 전 엔드포인트 인증 의무화 + JWT 기반 회사 범위 강제 (WO-TAI-API-SEC-DATA-READ-001)
v2.3.1: get_users 데모제외를 어드민 전체목록에만 적용
v2.3.0: 목록 size 상한 100→500 (LEDGER §68)
v2.2.0: 어드민 전체목록에서 데모(체험) 테넌트 사용자 제외
v2.1.0: APPOINTMENT 이벤트 트리거 추가
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

VERSION = "2.5.0"

DEACTIVATE_STATUSES = {"INACTIVE", "DELETED", "SUSPENDED"}

# 고권한 역할 코드 — 최고관리자(001)만 부여·변경 가능
_HIGH_PRIVILEGE_ROLES = frozenset({"001", "031", "032", "033"})

# API 응답에 포함되는 안전한 공개 컬럼
# 제외: password_hash, email_verify_token, auth_id,
#       raw_app_meta_data, raw_user_meta_data, identity_ci
_USER_PUBLIC_COLS = (
    "id,email,name,phone,username,role_code,company_id,factory_id,team_id,"
    "status_code,is_active,department,position,profile_image_url,"
    "allow_push,allow_sms,allow_email,allow_kakao,"
    "user_code,sector,last_login_at,created_at,updated_at,"
    "identity_verified,identity_name,identity_phone,identity_birth,"
    "address_road,address_jibun,address_detail,address_sido,"
    "address_sigungu,address_dong,zipcode,social_provider"
)

# allow-list 집합 — INSERT/UPDATE 응답 필터링에 사용
_PUBLIC_COLS_SET = frozenset(c.strip() for c in _USER_PUBLIC_COLS.split(","))


def _strip_to_public(row: dict) -> dict:
    """INSERT/UPDATE 응답에서 허용 목록(_PUBLIC_COLS_SET) 외 컬럼 제거 (allow-list)."""
    if not row:
        return {}
    return {k: v for k, v in row.items() if k in _PUBLIC_COLS_SET}


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
# 보안 헬퍼
# ============================================================

def _has_permission(supabase, role_code: str, permission_code: str) -> bool:
    """role_permissions 테이블에서 권한 보유 여부 확인. 실패 시 False(fail-close)."""
    if not role_code:
        return False
    try:
        res = (
            supabase.table("role_permissions")
            .select("id")
            .eq("role_code", role_code)
            .eq("permission_code", permission_code)
            .limit(1)
            .execute()
        )
        return bool(res.data)
    except Exception:
        return False


def _is_platform_admin(supabase, role_code: str) -> bool:
    """role_data_scope.scope_type == 'ALL'이면 플랫폼 전체 관리자."""
    if not role_code:
        return False
    try:
        r = (
            supabase.table("role_data_scope")
            .select("scope_type")
            .eq("role_code", role_code)
            .limit(1)
            .execute()
        )
        return bool(r.data) and r.data[0].get("scope_type") == "ALL"
    except Exception:
        return False


def _assert_user_company(target_company_id, current_user: dict, supabase) -> None:
    """비어드민이 타사 사용자에 접근하면 404(존재 숨김)."""
    if _is_platform_admin(supabase, current_user.get("role_code")):
        return
    jwt_company_id = current_user.get("company_id")
    if not jwt_company_id or target_company_id != jwt_company_id:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다")


def _assert_target_not_privileged(target_role_code, current_user: dict, supabase) -> None:
    """대상 사용자가 고권한 역할(_HIGH_PRIVILEGE_ROLES)이면 최고관리자(001)만 조작 가능."""
    if target_role_code not in _HIGH_PRIVILEGE_ROLES:
        return
    if _is_platform_admin(supabase, current_user.get("role_code")):
        return
    raise HTTPException(
        status_code=403,
        detail={"error": "TARGET_PRIVILEGE_DENIED",
                "message": "고권한 계정은 최고관리자만 수정·삭제할 수 있습니다"},
    )


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
    keyword:     Optional[str] = Query(default=None),
    role:        Optional[str] = Query(default=None),
    status:      Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    user_role = current_user.get("role_code")

    # USER_VIEW 권한 확인
    if not _has_permission(supabase, user_role, "USER_VIEW"):
        raise HTTPException(
            status_code=403,
            detail={"error": "PERMISSION_DENIED", "required": "USER_VIEW"},
        )

    is_admin = _is_platform_admin(supabase, user_role)
    jwt_company_id = current_user.get("company_id")

    # 비어드민: JWT company_id 강제 (클라이언트 파라미터 무시)
    if not is_admin:
        if not jwt_company_id:
            # 비어드민이면서 회사 없음 → 빈 결과
            return {
                "status": "success",
                "data": {"items": [], "total": 0, "page": page, "size": size, "total_pages": 0},
            }
        company_id = jwt_company_id
    else:
        # 어드민: 본인 회사가 있고 클라 파라미터 없으면 본인 회사 범위 유지
        if jwt_company_id and not company_id:
            company_id = jwt_company_id

    effective_search = search or keyword
    effective_role = role_code or role
    effective_status = status_code or status

    query = supabase.table("users").select(_USER_PUBLIC_COLS, count="exact")
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
def create_user(req: UserCreate, current_user: dict = Depends(get_current_user)):
    supabase = get_supabase()
    user_role = current_user.get("role_code")

    # USER_CREATE 권한 확인
    if not _has_permission(supabase, user_role, "USER_CREATE"):
        raise HTTPException(
            status_code=403,
            detail={"error": "PERMISSION_DENIED", "required": "USER_CREATE"},
        )

    is_admin = _is_platform_admin(supabase, user_role)
    jwt_company_id = current_user.get("company_id")

    # 비어드민: company_id 강제, 고권한 역할 부여 금지
    if not is_admin:
        if not jwt_company_id:
            raise HTTPException(status_code=403, detail="회사 등록이 필요합니다")
        req.company_id = jwt_company_id  # 클라이언트 값 무시
        if req.role_code in _HIGH_PRIVILEGE_ROLES:
            raise HTTPException(
                status_code=403,
                detail={"error": "ROLE_PRIVILEGE_DENIED",
                        "message": "고권한 역할은 최고관리자만 부여할 수 있습니다"},
            )

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
    return {"status": "success", "message": "회원이 등록됐습니다", "data": _strip_to_public(res.data[0])}


# ============================================================
# 3. 회원 상세 조회
# ============================================================

@router.get("/{user_id}")
def get_user(user_id: str, current_user: dict = Depends(get_current_user)):
    supabase = get_supabase()
    user_role = current_user.get("role_code")

    # USER_VIEW 권한 확인
    if not _has_permission(supabase, user_role, "USER_VIEW"):
        raise HTTPException(
            status_code=403,
            detail={"error": "PERMISSION_DENIED", "required": "USER_VIEW"},
        )

    res = supabase.table("users").select(_USER_PUBLIC_COLS).eq("id", user_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다")

    # 타사 접근 차단
    _assert_user_company(res.data.get("company_id"), current_user, supabase)

    return {"status": "success", "data": res.data}


# ============================================================
# 4. 회원 정보 수정
# ============================================================

@router.patch("/{user_id}")
def update_user(user_id: str, req: UserUpdate, current_user: dict = Depends(get_current_user)):
    supabase = get_supabase()
    user_role = current_user.get("role_code")

    # USER_UPDATE 권한 확인
    if not _has_permission(supabase, user_role, "USER_UPDATE"):
        raise HTTPException(
            status_code=403,
            detail={"error": "PERMISSION_DENIED", "required": "USER_UPDATE"},
        )

    existing = supabase.table("users").select(
        "id,company_id"
    ).eq("id", user_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다")

    # 타사 접근 차단
    _assert_user_company(existing.data.get("company_id"), current_user, supabase)

    update_data = {k: v for k, v in req.dict().items() if v is not None}

    # 비어드민: company_id 변경 차단 (테넌트 이동 방지)
    is_admin = _is_platform_admin(supabase, user_role)
    if not is_admin:
        update_data.pop("company_id", None)

    update_data["updated_at"] = serialize_business_datetime(now_kst())
    res = supabase.table("users").update(update_data).eq("id", user_id).execute()
    row = res.data[0] if res.data else {}
    return {"status": "success", "message": "회원 정보가 수정됐습니다", "data": _strip_to_public(row)}


# ============================================================
# 5. 회원 비활성화 (v2.0.0: 담당 SCHEDULED 일정 미배정)
# ============================================================

@router.delete("/{user_id}")
def delete_user(user_id: str, current_user: dict = Depends(get_current_user)):
    supabase = get_supabase()
    user_role = current_user.get("role_code")

    # USER_DELETE 권한 확인
    if not _has_permission(supabase, user_role, "USER_DELETE"):
        raise HTTPException(
            status_code=403,
            detail={"error": "PERMISSION_DENIED", "required": "USER_DELETE"},
        )

    existing = supabase.table("users").select(
        "id,company_id,role_code"
    ).eq("id", user_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다")

    # 타사 접근 차단
    _assert_user_company(existing.data.get("company_id"), current_user, supabase)
    # 고권한 대상 보호
    _assert_target_not_privileged(existing.data.get("role_code"), current_user, supabase)

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
def update_user_status(user_id: str, req: StatusUpdate, current_user: dict = Depends(get_current_user)):
    supabase = get_supabase()
    user_role = current_user.get("role_code")

    # USER_UPDATE 권한 확인
    if not _has_permission(supabase, user_role, "USER_UPDATE"):
        raise HTTPException(
            status_code=403,
            detail={"error": "PERMISSION_DENIED", "required": "USER_UPDATE"},
        )

    existing = supabase.table("users").select(
        "id,company_id,role_code"
    ).eq("id", user_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다")

    # 타사 접근 차단
    _assert_user_company(existing.data.get("company_id"), current_user, supabase)
    # 고권한 대상 보호
    _assert_target_not_privileged(existing.data.get("role_code"), current_user, supabase)

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
async def update_user_role(user_id: str, req: RoleUpdate, current_user: dict = Depends(get_current_user)):
    """
    v2.5.0: 역할 변경 인가 강화
      - USER_UPDATE 권한 필수
      - 자기 역할 변경 금지
      - 고권한 역할(_HIGH_PRIVILEGE_ROLES) 변경은 최고관리자(001)만
      - 타사 대상 변경 차단

    v2.1.0: role_code='002'(안전관리자) 설정 시 factory_id 있으면
    APPOINTMENT 이벤트 트리거 자동 호출.
    """
    supabase = get_supabase()
    user_role = current_user.get("role_code")

    # USER_UPDATE 권한 확인
    if not _has_permission(supabase, user_role, "USER_UPDATE"):
        raise HTTPException(
            status_code=403,
            detail={"error": "PERMISSION_DENIED", "required": "USER_UPDATE"},
        )

    # 자기 역할 변경 금지
    if user_id == str(current_user.get("id") or ""):
        raise HTTPException(
            status_code=403,
            detail={"error": "SELF_ROLE_CHANGE_FORBIDDEN",
                    "message": "본인의 역할은 직접 변경할 수 없습니다"},
        )

    # 고권한 역할 변경은 최고관리자(001)만
    if req.role_code in _HIGH_PRIVILEGE_ROLES and user_role != "001":
        raise HTTPException(
            status_code=403,
            detail={"error": "INSUFFICIENT_PRIVILEGE",
                    "message": "고권한 역할 변경은 최고관리자만 가능합니다"},
        )

    user_res = supabase.table("users").select(
        "id,role_code,factory_id,company_id"
    ).eq("id", user_id).single().execute()
    if not user_res.data:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다")

    # 타사 접근 차단
    _assert_user_company(user_res.data.get("company_id"), current_user, supabase)
    # 고권한 대상 보호 (기존 역할이 고권한이면 최고관리자만 변경 가능)
    _assert_target_not_privileged(user_res.data.get("role_code"), current_user, supabase)

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
def get_user_factories(user_id: str, current_user: dict = Depends(get_current_user)):
    supabase = get_supabase()
    user_role = current_user.get("role_code")

    # USER_VIEW 권한 확인
    if not _has_permission(supabase, user_role, "USER_VIEW"):
        raise HTTPException(
            status_code=403,
            detail={"error": "PERMISSION_DENIED", "required": "USER_VIEW"},
        )

    user = supabase.table("users").select(
        "factory_id, company_id"
    ).eq("id", user_id).single().execute()
    if not user.data:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다")

    # 타사 접근 차단
    _assert_user_company(user.data.get("company_id"), current_user, supabase)

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
