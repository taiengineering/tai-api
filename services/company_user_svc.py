"""회사 사용자 관리 · 초대 · 자격 게이트 — WP-A.

WO-SAFE-COMPANY-ACCESS-001. 핵심 규율:
  - platform 전용 ALL guard 재사용 금지. 회사 사용자관리는 COMPANY scope +
    worker-list 권한 조합(capability) 이 필요하다.
  - 1 user = 1 company. 회사 관리자는 role name 이 아니라 capability.
  - UNLIMITED. 시트/사용자 수 게이트 신설 금지 (총원 제한 카운터 신규 코드 0).
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from typing import Any, Dict, Iterable, Optional, Tuple

from fastapi import HTTPException
from services.time import business_today, now_kst, serialize_external_utc

log = logging.getLogger("company_user_svc")


# ── Constants ────────────────────────────────────────────────────────
WORKER_LIST_MENU_CODE = "worker-list"
_ACTION_TO_CRUD = {
    "LIST":    "can_list",
    "INVITE":  "can_create",
    "APPROVE": "can_update",
    "ROLE":    "can_update",
    "STATUS":  "can_update",
    "CANCEL":  "can_delete",
}

# 신규 회사 사용자관리 UI 에서 노출 대상 role scope.
_MEMBER_ROLE_SCOPES = ("COMPANY", "FACTORY", "TEAM", "ASSIGNED")

# 노출 금지 role_code (platform / SUPERADMIN 계열).
_EXCLUDED_ROLE_CODES = ("001", "031", "032", "033")


# ── Errors ──────────────────────────────────────────────────────────
class CompanyUserError(Exception):
    """도메인 오류. code / message / http_status."""
    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


# ── Guard : _require_company_user_admin ─────────────────────────────
def _require_company_user_admin(current: dict, sb, action: str) -> None:
    """회사 사용자관리 capability 게이트.

    5 조건 모두 통과해야 한다 :
      1. status_code == 'ACTIVE'
      2. is_active == True
      3. company_id 존재
      4. role_data_scope.scope_type == 'COMPANY'   (FACTORY / TEAM / ASSIGNED 는 부적격)
      5. role_menu_permissions(role_code, menu=worker-list, <crud>) == true

    action 매핑 :
      LIST → can_list · INVITE → can_create · APPROVE/ROLE/STATUS → can_update ·
      CANCEL → can_delete

    실패 : 403 . status 불량은 auth 게이트가 선차단하므로 여기 오면 대개 정상 사용자다.
    """
    if not current:
        raise HTTPException(status_code=401, detail="토큰이 없습니다")
    # 1 / 2 (auth 게이트가 이미 차단하지만 방어)
    if current.get("status_code") != "ACTIVE" or not bool(current.get("is_active")):
        raise HTTPException(status_code=403,
                            detail={"code": "ACCOUNT_NOT_ACTIVE",
                                    "message": "활성 상태 계정만 접근 가능합니다."})
    # 3
    cid = current.get("company_id")
    if not cid:
        raise HTTPException(status_code=403,
                            detail={"code": "COMPANY_REQUIRED",
                                    "message": "회사 소속이 필요합니다."})
    role_code = current.get("role_code")
    if not role_code:
        raise HTTPException(status_code=403,
                            detail={"code": "ROLE_REQUIRED",
                                    "message": "역할 정보가 없습니다."})
    # 4 role_data_scope.scope_type == 'COMPANY'
    try:
        r = (sb.table("role_data_scope")
             .select("scope_type").eq("role_code", role_code)
             .limit(1).execute())
        scope_type = (r.data[0].get("scope_type") if r.data else None)
    except Exception:
        # 스코프 조회 실패 시 fail-closed (관리 기능이므로).
        raise HTTPException(status_code=503,
                            detail={"code": "SCOPE_LOOKUP_FAILED",
                                    "message": "역할 스코프 조회에 실패했습니다."})
    if scope_type != "COMPANY":
        raise HTTPException(status_code=403,
                            detail={"code": "SCOPE_INSUFFICIENT",
                                    "message": "회사 관리 권한이 없습니다."})
    # 5 role_menu_permissions(worker-list, action→crud)
    crud = _ACTION_TO_CRUD.get(action)
    if not crud:
        # 알 수 없는 action 은 코드 결함. 방어적으로 403.
        raise HTTPException(status_code=403,
                            detail={"code": "UNKNOWN_ACTION",
                                    "message": "지원하지 않는 관리 액션입니다."})
    try:
        p = (sb.table("role_menu_permissions")
             .select("can_list, can_create, can_read, can_update, can_delete")
             .eq("role_code", role_code).eq("menu_code", WORKER_LIST_MENU_CODE)
             .limit(1).execute())
        row = p.data[0] if p.data else None
    except Exception:
        raise HTTPException(status_code=503,
                            detail={"code": "MENU_PERM_LOOKUP_FAILED",
                                    "message": "권한 조회에 실패했습니다."})
    if not row or not bool(row.get(crud)):
        raise HTTPException(status_code=403,
                            detail={"code": "MENU_PERMISSION_DENIED",
                                    "message": "이 작업을 수행할 권한이 없습니다."})


# ── 자격(entitlement) — strict fail-closed ──────────────────────────
def require_active_company_saas(sb, company_id: Optional[str]) -> None:
    """SaaS 자격 검증 · **fail-closed**.

    ACTIVE SaaS subscription 또는 ACTIVE SaaS contract 가 있어야 통과.
    없으면 403 SAAS_ENTITLEMENT_REQUIRED · 조회 실패는 503 (fail-open 금지).

    permission_guard.active_entitlement 는 exception 시 fail-open 이라 별도 헬퍼.
    """
    if not company_id:
        raise HTTPException(status_code=403,
                            detail={"code": "COMPANY_REQUIRED",
                                    "message": "회사 소속이 필요합니다."})
    try:
        today = business_today().isoformat()
        now = serialize_external_utc(now_kst())
        # subscription
        sub = (sb.table("subscriptions")
               .select("id, ended_at").eq("company_id", company_id)
               .eq("status", "ACTIVE").ilike("product_type", "SAAS%")
               .limit(20).execute())
        for row in sub.data or []:
            ended = row.get("ended_at")
            if not ended or str(ended) > now:
                return
        # contract
        con = (sb.table("contracts")
               .select("id, end_date").eq("company_id", company_id)
               .eq("is_active", True).ilike("service_type", "SAAS%")
               .limit(20).execute())
        for row in con.data or []:
            end = row.get("end_date")
            if not end or str(end)[:10] >= today:
                return
    except Exception:
        log.exception("[COMPANY-USER-SVC] entitlement 조회 실패 — fail-closed")
        raise HTTPException(status_code=503,
                            detail={"code": "ENTITLEMENT_LOOKUP_FAILED",
                                    "message": "자격 조회에 일시적 오류가 발생했습니다."})
    # 어떤 ACTIVE SaaS 도 없음.
    raise HTTPException(status_code=403,
                        detail={"code": "SAAS_ENTITLEMENT_REQUIRED",
                                "message": "이 회사에는 활성화된 TAI Safe 이용권이 없습니다."})


# ── Assignable role validation (invite create + role patch 공통) ─
# PATCH-2 BLOCKER-2B : list_assignable_roles 필터를 mutation 경로에서도 강제.
def assert_assignable_role(sb, role_code: Optional[str]) -> None:
    """지정 가능한 role 인지 서버 강제 검증.

    필터 (list_assignable_roles 와 동일):
      - role_code 가 001 / 031 / 032 / 033 이면 거부 (platform · super admin)
      - roles.is_active == True
      - role_data_scope.scope_type in (COMPANY / FACTORY / TEAM / ASSIGNED)
        (ALL / PLATFORM 은 거부)

    위반 시 422 ROLE_NOT_ASSIGNABLE 예외 (라우터가 HTTPException 로 변환).
    """
    if not role_code:
        raise CompanyUserError("ROLE_REQUIRED", "역할이 필요합니다.", 422)
    if role_code in _EXCLUDED_ROLE_CODES:
        raise CompanyUserError("ROLE_NOT_ASSIGNABLE",
                               "지정할 수 없는 역할입니다.", 422)
    try:
        r = (sb.table("roles").select("role_code, is_active")
             .eq("role_code", role_code).limit(1).execute()).data or []
    except Exception:
        raise CompanyUserError("ROLE_LOOKUP_FAILED",
                               "역할 조회에 실패했습니다.", 503)
    if not r or not bool(r[0].get("is_active")):
        raise CompanyUserError("ROLE_NOT_ASSIGNABLE",
                               "지정할 수 없는 역할입니다.", 422)
    try:
        s = (sb.table("role_data_scope").select("scope_type")
             .eq("role_code", role_code).limit(1).execute()).data or []
    except Exception:
        raise CompanyUserError("ROLE_LOOKUP_FAILED",
                               "역할 스코프 조회에 실패했습니다.", 503)
    scope = s[0].get("scope_type") if s else None
    if scope not in _MEMBER_ROLE_SCOPES:
        raise CompanyUserError("ROLE_NOT_ASSIGNABLE",
                               "지정할 수 없는 역할입니다.", 422)


# ── Company Admin capability (bootstrap 용 · role 이름 아님) ──────
def _has_company_admin_capability(sb, role_code: str) -> bool:
    """role_code 가 회사 사용자 관리 capability 를 가지는가.

    COMPANY scope + worker-list can_list/create/update/delete 전부 true.
    """
    if not role_code:
        return False
    try:
        r = (sb.table("role_data_scope").select("scope_type")
             .eq("role_code", role_code).limit(1).execute())
        if not r.data or r.data[0].get("scope_type") != "COMPANY":
            return False
        p = (sb.table("role_menu_permissions")
             .select("can_list, can_create, can_update, can_delete")
             .eq("role_code", role_code).eq("menu_code", WORKER_LIST_MENU_CODE)
             .limit(1).execute())
        row = p.data[0] if p.data else None
        return bool(row and row.get("can_list") and row.get("can_create")
                    and row.get("can_update") and row.get("can_delete"))
    except Exception:
        log.exception("[COMPANY-USER-SVC] capability 판정 실패")
        return False


def _company_admin_active_count(sb, company_id: str) -> int:
    """회사에서 관리 capability 를 가진 ACTIVE + is_active 사용자 수."""
    if not company_id:
        return 0
    try:
        rows = (sb.table("users").select("id, role_code, status_code, is_active")
                .eq("company_id", company_id).eq("status_code", "ACTIVE")
                .eq("is_active", True).execute()).data or []
    except Exception:
        log.exception("[COMPANY-USER-SVC] users 조회 실패")
        return 0
    count = 0
    for u in rows:
        if _has_company_admin_capability(sb, u.get("role_code")):
            count += 1
    return count


# ── Roles list (신규 UI 에서 관리자에게 배정 가능한 role 목록) ────
def list_assignable_roles(sb) -> list:
    """UI 배정 후보 : is_active + scope in (COMPANY/FACTORY/TEAM/ASSIGNED),
    ALL/PLATFORM/001/031/032/033 제외."""
    try:
        roles = (sb.table("roles")
                 .select("role_code, role_name, is_active")
                 .eq("is_active", True).execute()).data or []
        scopes = (sb.table("role_data_scope")
                  .select("role_code, scope_type").execute()).data or []
    except Exception:
        log.exception("[COMPANY-USER-SVC] roles 조회 실패")
        return []
    scope_by_role = {s.get("role_code"): s.get("scope_type") for s in scopes}
    out = []
    for r in roles:
        rc = r.get("role_code")
        if rc in _EXCLUDED_ROLE_CODES:
            continue
        st = scope_by_role.get(rc)
        if st not in _MEMBER_ROLE_SCOPES:
            continue
        out.append({"role_code": rc, "role_name": r.get("role_name"), "scope_type": st})
    return out


# ── Users projection (sensitive 필드 제거) ─────────────────────────
_USER_PROJECTION = (
    "id, email, name, phone, role_code, company_id, factory_id, team_id, "
    "status_code, is_active, profile_image_url, created_at, updated_at"
)


def list_company_users(sb, company_id: str) -> list:
    if not company_id:
        return []
    try:
        rows = (sb.table("users").select(_USER_PROJECTION)
                .eq("company_id", company_id).execute()).data or []
    except Exception:
        log.exception("[COMPANY-USER-SVC] company users 조회 실패")
        return []
    return rows


def get_company_user(sb, company_id: str, user_id: str) -> Optional[dict]:
    if not company_id or not user_id:
        return None
    try:
        rows = (sb.table("users").select(_USER_PROJECTION)
                .eq("id", user_id).eq("company_id", company_id).limit(1).execute()).data
    except Exception:
        log.exception("[COMPANY-USER-SVC] user 조회 실패")
        return None
    return rows[0] if rows else None


# ── Invite (SHA-256 token_hash + invite-frozen) ────────────────────
INVITE_TTL_DAYS = 7

def hash_token(raw_token: str) -> str:
    """가입 토큰의 SHA-256 hex digest — DB 저장/조회용."""
    if raw_token is None:
        return ""
    return hashlib.sha256(str(raw_token).encode("utf-8")).hexdigest()


def _mask_email(email: Optional[str]) -> str:
    if not email:
        return ""
    e = str(email)
    if "@" not in e:
        return "*" * len(e)
    local, dom = e.split("@", 1)
    if len(local) <= 2:
        masked = local[0] + "*"
    else:
        masked = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{masked}@{dom}"


def build_invite_row(company_id: str, email: str, role_code: str,
                     factory_id: Optional[str], team_id: Optional[str],
                     invited_by: str, ttl_days: Optional[int] = None) -> Tuple[Dict[str, Any], str]:
    """서버 결정값으로 invite row 생성 (raw token 반환은 응답 1회용).

    (row_to_insert, raw_token) 반환. row 에는 token_hash 만 저장.
    """
    from datetime import timedelta
    days = int(ttl_days) if ttl_days is not None else INVITE_TTL_DAYS
    raw = secrets.token_urlsafe(32)
    row = {
        "company_id": company_id,
        "email": (email or "").strip().lower(),
        "role_code": role_code,
        "factory_id": factory_id,
        "team_id": team_id,
        "status": "PENDING",
        "token_hash": hash_token(raw),
        "invited_by": invited_by,
        "expires_at": serialize_external_utc(now_kst() + timedelta(days=days)),
        "created_at": now_kst().isoformat(),
        "updated_at": now_kst().isoformat(),
    }
    return row, raw


def _find_invite_by_hash(sb, token_hash: str) -> Optional[dict]:
    if not token_hash:
        return None
    try:
        rows = (sb.table("company_user_invites").select("*")
                .eq("token_hash", token_hash).limit(1).execute()).data
    except Exception:
        log.exception("[COMPANY-USER-SVC] invite 조회 실패")
        return None
    return rows[0] if rows else None


def find_invite_by_raw_token(sb, raw_token: str) -> Optional[dict]:
    return _find_invite_by_hash(sb, hash_token(raw_token))


def invite_public_info(invite: dict, roles_map: Dict[str, str],
                       companies_map: Dict[str, str]) -> dict:
    """token/info 공개 응답 — masked email · role name · company name · valid."""
    if not invite:
        return {"valid": False}
    now = serialize_external_utc(now_kst())
    valid = (invite.get("status") == "PENDING"
             and invite.get("expires_at") and str(invite["expires_at"]) > now)
    return {
        "valid": bool(valid),
        "company_name": companies_map.get(invite.get("company_id")) if valid else None,
        "email_masked": _mask_email(invite.get("email")) if valid else None,
        "role_name": roles_map.get(invite.get("role_code")) if valid else None,
        "expires_at": invite.get("expires_at") if valid else None,
    }
