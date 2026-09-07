# routers/company_users.py — v1.0.0 (WO-SAFE-COMPANY-ACCESS-001 · WP-A)
"""회사 사용자 관리 · 초대 라우터.

전 endpoint: Depends(get_current_user) → _require_company_user_admin(action) + (mutation)
require_active_company_saas. target = current.company_id. body/query 에 company_id 없음.
cross-company = 404 (존재 은닉).

/user-invites/{token}/info 는 공개(permission_guard PUBLIC allowlist).
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

# PATCH-1 : Inicis CI 계약을 register(routers/auth.py) 와 정확히 동일하게 맞춘다.
#   실제 테이블 = inicis_auth_requests (mtx_id → status='SUCCESS', user_ci 등).
#   identity_ci = SHA-256(user_ci) hex.  users.identity_ci 로 CI 중복가입 차단.
#   초대 가입도 본인인증을 필수로 취급(register 와 동일 강도).

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services import company_user_svc as svc
from services.time import now_kst, serialize_external_utc


router = APIRouter(tags=["company-users"])
_NOT_FOUND = "사용자를 찾을 수 없습니다"


# ── Body schemas (company_id 절대 미노출) ───────────────────────────
class InviteCreateBody(BaseModel):
    email: str
    role_code: str
    factory_id: Optional[str] = None
    team_id: Optional[str] = None


class RolePatchBody(BaseModel):
    role_code: str
    factory_id: Optional[str] = None
    team_id: Optional[str] = None


class StatusPatchBody(BaseModel):
    status_code: str        # ACTIVE | INACTIVE 만


class InviteAcceptBody(BaseModel):
    name: str
    phone: str
    password: str
    mtx_id: Optional[str] = None                       # Inicis 본인확인 mtx_id 재사용


# ── Helpers ────────────────────────────────────────────────────────
def _raise(e: svc.CompanyUserError):
    raise HTTPException(status_code=e.http_status, detail={"code": e.code, "message": e.message})


def _get_company_name(sb, company_id: str) -> Optional[str]:
    try:
        r = sb.table("companies").select("name").eq("id", company_id).limit(1).execute()
        return r.data[0].get("name") if r.data else None
    except Exception:
        return None


def _entitlement_snapshot(sb, company_id: str) -> dict:
    """/me/company/access 응답용 entitlement 정보 (읽기 전용 · fail-safe)."""
    if not company_id:
        return {"active": False, "source": None, "plan_code": None,
                "start_date": None, "end_date": None}
    try:
        now = serialize_external_utc(now_kst())
        sub = (sb.table("subscriptions")
               .select("id, product_type, start_date, ended_at, plan_code")
               .eq("company_id", company_id).eq("status", "ACTIVE")
               .ilike("product_type", "SAAS%").limit(20).execute()).data or []
        for row in sub:
            ended = row.get("ended_at")
            if not ended or str(ended) > now:
                return {"active": True, "source": "subscription",
                        "plan_code": row.get("plan_code"),
                        "start_date": row.get("start_date"),
                        "end_date": ended}
        con = (sb.table("contracts")
               .select("id, service_type, plan_code, start_date, end_date, is_active")
               .eq("company_id", company_id).eq("is_active", True)
               .ilike("service_type", "SAAS%").limit(20).execute()).data or []
        from services.time import business_today
        today = business_today().isoformat()
        for row in con:
            end = row.get("end_date")
            if not end or str(end)[:10] >= today:
                return {"active": True, "source": "contract",
                        "plan_code": row.get("plan_code"),
                        "start_date": row.get("start_date"),
                        "end_date": end}
    except Exception:
        # entitlement snapshot 은 표시용 · 오류 시 active=False (mutation 은 별도로 fail-closed).
        return {"active": False, "source": None, "plan_code": None,
                "start_date": None, "end_date": None}
    return {"active": False, "source": None, "plan_code": None,
            "start_date": None, "end_date": None}


def _can_manage_users(sb, current: dict) -> bool:
    """UI 배지용 : capability 게이트를 실제로 통과할 수 있는지 조용히 판정."""
    try:
        svc._require_company_user_admin(current, sb, "LIST")
        return True
    except HTTPException:
        return False


def _last_admin_guard(sb, company_id: str, target_user_id: str,
                     new_role_code: Optional[str] = None,
                     will_be_inactive: bool = False) -> None:
    """LAST_COMPANY_ADMIN 보호.
    회사의 관리 capability ACTIVE 가 1명뿐이고 그 사용자가 target 이며
    이번 변경이 그 자격을 상실시키면 409.
    """
    count = svc._company_admin_active_count(sb, company_id)
    if count > 1:
        return
    if count == 0:
        return
    # 유일 관리자가 target 인가?
    try:
        r = (sb.table("users").select("id, role_code, status_code, is_active")
             .eq("id", target_user_id).eq("company_id", company_id)
             .limit(1).execute())
    except Exception:
        return
    if not r.data:
        return
    tgt = r.data[0]
    is_currently_capability = (
        tgt.get("status_code") == "ACTIVE" and bool(tgt.get("is_active"))
        and svc._has_company_admin_capability(sb, tgt.get("role_code"))
    )
    if not is_currently_capability:
        return
    # 새 상태 판정
    would_stay_capability = True
    if will_be_inactive:
        would_stay_capability = False
    elif new_role_code is not None and new_role_code != tgt.get("role_code"):
        would_stay_capability = svc._has_company_admin_capability(sb, new_role_code)
    if not would_stay_capability:
        raise HTTPException(status_code=409, detail={
            "code": "LAST_COMPANY_ADMIN",
            "message": "회사에 남는 관리자가 없어 변경할 수 없습니다.",
        })


# ═══════════════════════════════════════════════════════════════════
# GET /me/company/access — 403 아님, 현재 상태 반환
# ═══════════════════════════════════════════════════════════════════
@router.get("/me/company/access")
def get_company_access(current: dict = Depends(get_current_user)):
    """회사 접근 정보 · entitlement 스냅샷 + can_manage_users.

    이 엔드포인트는 표시용이라 capability 게이트를 강제하지 않는다
    (403 아님 · 정보만 반환). Safe frontend 는 entitlement.active 로 진입 여부 판정.
    """
    sb = get_supabase()
    company_id = current.get("company_id")
    company_name = _get_company_name(sb, company_id) if company_id else None
    ent = _entitlement_snapshot(sb, company_id) if company_id else \
        {"active": False, "source": None, "plan_code": None, "start_date": None, "end_date": None}
    return {"status": "success", "data": {
        "company_id": company_id,
        "company_name": company_name,
        "entitlement": ent,
        "can_manage_users": _can_manage_users(sb, current),
    }}


# ═══════════════════════════════════════════════════════════════════
# GET /me/company/users
# ═══════════════════════════════════════════════════════════════════
@router.get("/me/company/users")
def list_users(current: dict = Depends(get_current_user)):
    sb = get_supabase()
    svc._require_company_user_admin(current, sb, "LIST")
    company_id = current["company_id"]
    users = svc.list_company_users(sb, company_id)
    return {"status": "success", "data": {"items": users, "total": len(users)}}


# ═══════════════════════════════════════════════════════════════════
# GET /me/company/user-roles — 배정 가능한 role 목록
# ═══════════════════════════════════════════════════════════════════
@router.get("/me/company/user-roles")
def list_user_roles(current: dict = Depends(get_current_user)):
    sb = get_supabase()
    svc._require_company_user_admin(current, sb, "LIST")
    roles = svc.list_assignable_roles(sb)
    return {"status": "success", "data": {"items": roles, "total": len(roles)}}


# ═══════════════════════════════════════════════════════════════════
# GET /me/company/user-invites
# ═══════════════════════════════════════════════════════════════════
@router.get("/me/company/user-invites")
def list_invites(current: dict = Depends(get_current_user)):
    sb = get_supabase()
    svc._require_company_user_admin(current, sb, "LIST")
    company_id = current["company_id"]
    try:
        rows = (sb.table("company_user_invites")
                .select("id, email, role_code, factory_id, team_id, status, "
                        "expires_at, invited_by, created_at, accepted_at, cancelled_at")
                .eq("company_id", company_id).execute()).data or []
    except Exception:
        rows = []
    return {"status": "success", "data": {"items": rows, "total": len(rows)}}


# ═══════════════════════════════════════════════════════════════════
# POST /me/company/user-invites — 생성
# ═══════════════════════════════════════════════════════════════════
@router.post("/me/company/user-invites")
def create_invite(body: InviteCreateBody, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    svc._require_company_user_admin(current, sb, "INVITE")
    svc.require_active_company_saas(sb, current.get("company_id"))
    company_id = current["company_id"]
    email = (body.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail={"code": "INVALID_EMAIL",
                                                     "message": "유효한 이메일이 필요합니다."})
    role_code = body.role_code
    if not role_code:
        raise HTTPException(status_code=422, detail={"code": "ROLE_REQUIRED",
                                                     "message": "역할이 필요합니다."})
    # 기존 user 충돌
    try:
        er = (sb.table("users").select("id, company_id, status_code")
              .eq("email", email).limit(1).execute()).data or []
    except Exception:
        er = []
    if er:
        u = er[0]
        if u.get("company_id") and str(u["company_id"]) != str(company_id):
            raise HTTPException(status_code=409, detail={
                "code": "USER_BELONGS_TO_ANOTHER_COMPANY",
                "message": "다른 회사에 속한 사용자입니다.",
            })
        if u.get("company_id") == company_id and u.get("status_code") == "ACTIVE":
            raise HTTPException(status_code=409, detail={
                "code": "USER_ALREADY_MEMBER",
                "message": "이미 회사에 소속된 사용자입니다.",
            })
    # 같은 회사 PENDING invite 중복
    try:
        pend = (sb.table("company_user_invites").select("id")
                .eq("company_id", company_id).eq("email", email)
                .eq("status", "PENDING").limit(1).execute()).data or []
    except Exception:
        pend = []
    if pend:
        raise HTTPException(status_code=409, detail={
            "code": "INVITE_PENDING_EXISTS",
            "message": "이미 대기 중인 초대가 있습니다.",
        })
    # factory / team scope 검증 (own-company)
    if body.factory_id:
        try:
            f = (sb.table("factories").select("id, company_id")
                 .eq("id", body.factory_id).limit(1).execute()).data or []
        except Exception:
            f = []
        if not f or str(f[0].get("company_id")) != str(company_id):
            raise HTTPException(status_code=422, detail={
                "code": "FACTORY_OUT_OF_SCOPE",
                "message": "다른 회사의 시설을 지정할 수 없습니다.",
            })
    if body.team_id:
        try:
            t = (sb.table("teams").select("id, factory_id")
                 .eq("id", body.team_id).limit(1).execute()).data or []
        except Exception:
            t = []
        if not t:
            raise HTTPException(status_code=422, detail={
                "code": "TEAM_NOT_FOUND",
                "message": "팀을 찾을 수 없습니다.",
            })
        # team.factory.company_id 검증
        try:
            fid = t[0].get("factory_id")
            f = (sb.table("factories").select("id, company_id")
                 .eq("id", fid).limit(1).execute()).data or []
        except Exception:
            f = []
        if not f or str(f[0].get("company_id")) != str(company_id):
            raise HTTPException(status_code=422, detail={
                "code": "TEAM_OUT_OF_SCOPE",
                "message": "다른 회사의 팀을 지정할 수 없습니다.",
            })
    # invite row 생성
    row, raw_token = svc.build_invite_row(
        company_id=company_id, email=email, role_code=role_code,
        factory_id=body.factory_id, team_id=body.team_id,
        invited_by=current.get("id"),
    )
    try:
        ins = sb.table("company_user_invites").insert(row).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail={
            "code": "INVITE_INSERT_FAILED",
            "message": "초대 생성에 실패했습니다.",
        }) from e
    inserted = ins.data[0] if ins.data else row
    # raw_token 은 응답 1회 · DB/log/slack 저장 금지.
    return {"status": "success", "data": {
        "invite": {
            "id": inserted.get("id"),
            "email": inserted.get("email"),
            "role_code": inserted.get("role_code"),
            "status": inserted.get("status"),
            "expires_at": inserted.get("expires_at"),
        },
        "token": raw_token,
    }}


# ═══════════════════════════════════════════════════════════════════
# DELETE /me/company/user-invites/{invite_id} → CANCELLED
# ═══════════════════════════════════════════════════════════════════
@router.delete("/me/company/user-invites/{invite_id}")
def cancel_invite(invite_id: str, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    svc._require_company_user_admin(current, sb, "CANCEL")
    company_id = current["company_id"]
    now = now_kst().isoformat()
    res = (sb.table("company_user_invites")
           .update({"status": "CANCELLED", "cancelled_at": now, "updated_at": now})
           .eq("id", invite_id).eq("company_id", company_id)
           .eq("status", "PENDING").execute())
    if not res.data:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return {"status": "success", "data": res.data[0]}


# ═══════════════════════════════════════════════════════════════════
# POST /me/company/users/{user_id}/approve — PENDING → ACTIVE
# ═══════════════════════════════════════════════════════════════════
@router.post("/me/company/users/{user_id}/approve")
def approve_user(user_id: str, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    svc._require_company_user_admin(current, sb, "APPROVE")
    svc.require_active_company_saas(sb, current.get("company_id"))
    company_id = current["company_id"]
    now = now_kst().isoformat()
    res = (sb.table("users")
           .update({"status_code": "ACTIVE", "is_active": True, "updated_at": now})
           .eq("id", user_id).eq("company_id", company_id)
           .eq("status_code", "PENDING").execute())
    if not res.data:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return {"status": "success", "data": res.data[0]}


# ═══════════════════════════════════════════════════════════════════
# PATCH /me/company/users/{user_id}/role
# ═══════════════════════════════════════════════════════════════════
@router.patch("/me/company/users/{user_id}/role")
def patch_user_role(user_id: str, body: RolePatchBody,
                     current: dict = Depends(get_current_user)):
    sb = get_supabase()
    svc._require_company_user_admin(current, sb, "ROLE")
    svc.require_active_company_saas(sb, current.get("company_id"))
    company_id = current["company_id"]
    # 존재 + own-company
    tgt = svc.get_company_user(sb, company_id, user_id)
    if not tgt:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    if not body.role_code:
        raise HTTPException(status_code=422, detail={"code": "ROLE_REQUIRED",
                                                     "message": "역할이 필요합니다."})
    # role scope 유효성
    try:
        s = (sb.table("role_data_scope").select("scope_type")
             .eq("role_code", body.role_code).limit(1).execute()).data or []
    except Exception:
        s = []
    if not s:
        raise HTTPException(status_code=422, detail={"code": "ROLE_NOT_FOUND",
                                                     "message": "역할을 찾을 수 없습니다."})
    scope = s[0].get("scope_type")
    if scope == "FACTORY" and not body.factory_id:
        raise HTTPException(status_code=422, detail={"code": "FACTORY_REQUIRED",
                                                     "message": "FACTORY 스코프 역할은 시설이 필요합니다."})
    if scope == "TEAM" and not body.team_id:
        raise HTTPException(status_code=422, detail={"code": "TEAM_REQUIRED",
                                                     "message": "TEAM 스코프 역할은 팀이 필요합니다."})
    # factory / team own-company 검증
    if body.factory_id:
        try:
            f = (sb.table("factories").select("company_id").eq("id", body.factory_id)
                 .limit(1).execute()).data or []
        except Exception:
            f = []
        if not f or str(f[0].get("company_id")) != str(company_id):
            raise HTTPException(status_code=422, detail={
                "code": "FACTORY_OUT_OF_SCOPE",
                "message": "다른 회사의 시설을 지정할 수 없습니다.",
            })
    if body.team_id:
        try:
            t = (sb.table("teams").select("factory_id").eq("id", body.team_id)
                 .limit(1).execute()).data or []
        except Exception:
            t = []
        if not t:
            raise HTTPException(status_code=422, detail={"code": "TEAM_NOT_FOUND",
                                                         "message": "팀을 찾을 수 없습니다."})
        try:
            fid = t[0].get("factory_id")
            f = (sb.table("factories").select("company_id").eq("id", fid)
                 .limit(1).execute()).data or []
        except Exception:
            f = []
        if not f or str(f[0].get("company_id")) != str(company_id):
            raise HTTPException(status_code=422, detail={
                "code": "TEAM_OUT_OF_SCOPE",
                "message": "다른 회사의 팀을 지정할 수 없습니다.",
            })
    # LAST_COMPANY_ADMIN 보호
    _last_admin_guard(sb, company_id, user_id, new_role_code=body.role_code)
    now = now_kst().isoformat()
    patch = {"role_code": body.role_code, "updated_at": now}
    if body.factory_id is not None:
        patch["factory_id"] = body.factory_id
    if body.team_id is not None:
        patch["team_id"] = body.team_id
    res = (sb.table("users").update(patch)
           .eq("id", user_id).eq("company_id", company_id).execute())
    if not res.data:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return {"status": "success", "data": res.data[0]}


# ═══════════════════════════════════════════════════════════════════
# PATCH /me/company/users/{user_id}/status — ACTIVE | INACTIVE
# ═══════════════════════════════════════════════════════════════════
@router.patch("/me/company/users/{user_id}/status")
def patch_user_status(user_id: str, body: StatusPatchBody,
                       current: dict = Depends(get_current_user)):
    sb = get_supabase()
    svc._require_company_user_admin(current, sb, "STATUS")
    svc.require_active_company_saas(sb, current.get("company_id"))
    company_id = current["company_id"]
    new = (body.status_code or "").upper()
    if new not in ("ACTIVE", "INACTIVE"):
        raise HTTPException(status_code=422, detail={
            "code": "STATUS_NOT_ALLOWED",
            "message": "허용되지 않는 상태값입니다. (ACTIVE|INACTIVE)",
        })
    tgt = svc.get_company_user(sb, company_id, user_id)
    if not tgt:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    if new == "ACTIVE" and tgt.get("status_code") == "PENDING":
        raise HTTPException(status_code=409, detail={
            "code": "USE_APPROVE_FOR_PENDING",
            "message": "PENDING 상태는 approve 엔드포인트로 처리하세요.",
        })
    # LAST_COMPANY_ADMIN 보호
    if new == "INACTIVE":
        _last_admin_guard(sb, company_id, user_id, will_be_inactive=True)
    now = now_kst().isoformat()
    patch = {"status_code": new, "is_active": (new == "ACTIVE"), "updated_at": now}
    res = (sb.table("users").update(patch)
           .eq("id", user_id).eq("company_id", company_id).execute())
    if not res.data:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return {"status": "success", "data": res.data[0]}


# ═══════════════════════════════════════════════════════════════════
# GET /user-invites/{token}/info — PUBLIC
# ═══════════════════════════════════════════════════════════════════
@router.get("/user-invites/{token}/info")
def get_invite_info(token: str):
    sb = get_supabase()
    invite = svc.find_invite_by_raw_token(sb, token)
    if not invite:
        return {"status": "success", "data": {"valid": False}}
    # role_name / company_name 매핑
    roles_map = {}
    try:
        rs = (sb.table("roles").select("role_code, role_name").execute()).data or []
        roles_map = {r.get("role_code"): r.get("role_name") for r in rs}
    except Exception:
        roles_map = {}
    companies_map = {}
    try:
        cs = (sb.table("companies").select("id, name")
              .eq("id", invite.get("company_id")).limit(1).execute()).data or []
        companies_map = {str(c.get("id")): c.get("name") for c in cs}
    except Exception:
        companies_map = {}
    return {"status": "success",
            "data": svc.invite_public_info(invite, roles_map, companies_map)}


# ═══════════════════════════════════════════════════════════════════
# POST /user-invites/{token}/accept — 신규 회원 가입 (invite-frozen)
#   결과 user : status = PENDING · is_active = false. 승인은 관리자 approve.
# ═══════════════════════════════════════════════════════════════════
@router.post("/user-invites/{token}/accept")
def accept_invite(token: str, body: InviteAcceptBody):
    sb = get_supabase()
    invite = svc.find_invite_by_raw_token(sb, token)
    if not invite:
        raise HTTPException(status_code=404, detail={"code": "INVITE_NOT_FOUND",
                                                     "message": "초대를 찾을 수 없습니다."})
    st = invite.get("status")
    now_str = serialize_external_utc(now_kst())
    if st in ("ACCEPTED", "CANCELLED"):
        raise HTTPException(status_code=410, detail={"code": f"INVITE_{st}",
                                                     "message": "재사용할 수 없는 초대입니다."})
    if invite.get("expires_at") and str(invite["expires_at"]) < now_str:
        raise HTTPException(status_code=410, detail={"code": "INVITE_EXPIRED",
                                                     "message": "만료된 초대입니다."})
    if st != "PENDING":
        raise HTTPException(status_code=409, detail={"code": "INVITE_STATE_INVALID",
                                                     "message": "유효하지 않은 초대 상태입니다."})
    # 필수 입력
    if not body.name or not body.phone or not body.password:
        raise HTTPException(status_code=422, detail={"code": "MISSING_FIELDS",
                                                     "message": "필수 입력이 부족합니다."})
    phone_norm = re.sub(r"[^0-9]", "", body.phone or "")
    if not phone_norm:
        raise HTTPException(status_code=422, detail={"code": "INVALID_PHONE",
                                                     "message": "전화번호가 유효하지 않습니다."})
    # ── Inicis 본인인증 검증 (routers.auth.register 와 동일 계약) ──
    #   inicis_auth_requests: mtx_id → status='SUCCESS', user_ci
    #   identity_ci = SHA-256(user_ci) hex. users.identity_ci 와 대조해 CI 중복가입 차단.
    #   PATCH-1 정책 : 초대 가입도 register 와 동일 강도 → mtx_id 필수.
    identity_ci = None
    identity_fields: dict = {}
    if not body.mtx_id:
        raise HTTPException(status_code=400, detail={
            "code": "IDENTITY_VERIFICATION_REQUIRED",
            "message": "본인인증이 필요합니다. 본인인증을 먼저 완료해 주세요.",
        })
    try:
        ia = (sb.table("inicis_auth_requests")
              .select("status, user_ci, user_name, user_phone, user_birthday")
              .eq("mtx_id", body.mtx_id).limit(1).execute()).data or []
    except Exception:
        ia = []
    if not ia or ia[0].get("status") != "SUCCESS":
        raise HTTPException(status_code=400, detail={
            "code": "IDENTITY_VERIFICATION_REQUIRED",
            "message": "본인인증이 필요합니다. 본인인증을 먼저 완료해 주세요.",
        })
    _ci = (ia[0].get("user_ci") or "").strip()
    if not _ci:
        raise HTTPException(status_code=400, detail={
            "code": "IDENTITY_CI_MISSING",
            "message": "본인인증 정보를 확인할 수 없습니다.",
        })
    identity_ci = hashlib.sha256(_ci.encode("utf-8")).hexdigest()
    try:
        dup = (sb.table("users").select("id")
               .eq("identity_ci", identity_ci).limit(1).execute()).data or []
    except Exception:
        dup = []
    if dup:
        raise HTTPException(status_code=409, detail={
            "code": "CI_ALREADY_USED",
            "message": "이미 본인확인된 계정이 있습니다.",
        })
    identity_fields = {
        "identity_verified": True,
        "identity_verified_at": now_kst().isoformat(),
        "identity_name": ia[0].get("user_name"),
        "identity_phone": ia[0].get("user_phone"),
        "identity_birth": ia[0].get("user_birthday"),
        "identity_ci": identity_ci,
    }
    # phone 중복
    try:
        pd = (sb.table("users").select("id").eq("phone", phone_norm)
              .limit(1).execute()).data or []
    except Exception:
        pd = []
    if pd:
        raise HTTPException(status_code=409, detail={"code": "PHONE_ALREADY_USED",
                                                     "message": "이미 사용 중인 전화번호입니다."})
    # invite-frozen : company/role/factory/team = invite 값. email = invite.email.
    import bcrypt
    pw_hash = bcrypt.hashpw(body.password.encode("utf-8"),
                             bcrypt.gensalt()).decode("utf-8")
    user_row = {
        "email": invite.get("email"),
        "phone": phone_norm,
        "name": body.name.strip(),
        "password_hash": pw_hash,
        "company_id": invite.get("company_id"),
        "role_code": invite.get("role_code"),
        "factory_id": invite.get("factory_id"),
        "team_id": invite.get("team_id"),
        "status_code": "PENDING",
        "is_active": False,
        "created_at": now_kst().isoformat(),
        "updated_at": now_kst().isoformat(),
    }
    # PATCH-1 : identity_fields (identity_verified/at/name/phone/birth/ci) 병합.
    user_row.update(identity_fields)
    try:
        ins = sb.table("users").insert(user_row).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "USER_INSERT_FAILED",
                                                     "message": "가입에 실패했습니다."}) from e
    saved = ins.data[0] if ins.data else user_row
    # invite → ACCEPTED
    try:
        (sb.table("company_user_invites").update({
            "status": "ACCEPTED",
            "accepted_user_id": saved.get("id"),
            "accepted_at": now_kst().isoformat(),
            "updated_at": now_kst().isoformat(),
        }).eq("id", invite.get("id")).execute())
    except Exception:
        pass
    # projection : sensitive 제거
    for k in ("password_hash", "identity_ci"):
        saved.pop(k, None)
    return {"status": "success", "data": saved}
