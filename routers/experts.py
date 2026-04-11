# routers/experts.py — v1.0.0
# 전문가 등록 신청 / 현황 / 어드민 승인 API
#
# ⚠️ 용어 규칙: 없는 단어
#   금지: 소개비, 소개료, 소개수수료, 인력소개
#   대체: platform_fee, 플랫폼 이용료, 전문가 매칭, performance_fee

from __future__ import annotations
import re
import logging
from datetime import datetime, timezone
from typing import Optional, List, Any, Dict

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from routers.auth import get_current_user
from db.supabase_client import get_supabase

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/experts", tags=["전문가"])


# ════════════════════════════════════════════
class ExpertApplyRequest(BaseModel):
    expert_type:     str                 # safety | fix | consult
    biz_name:        str
    biz_number:      str                 # 시스템 내부 저장: 숫자 10자리
    representative:  Optional[str] = None
    contact_phone:   str
    service_regions: List[str]
    intro_text:      Optional[str] = None
    terms_agreed:    bool
    terms_agreed_at: str                 # ISO datetime
    type_data:       Dict[str, Any] = {}
    """
    safety  → { certifications, cert_files, service_sectors, max_contracts }
    fix     → { specialties, has_construction_license, license_type, tech_count }
    consult → { specialties, qualifications, cert_files, max_cases_per_year }
    """


class ExpertApproveRequest(BaseModel):
    platform_fee_rate: float = 10.0   # % 단위, 플랫폼 이용료율
    review_note:       Optional[str] = None


class ExpertRejectRequest(BaseModel):
    review_note: str


# ════════════════════════════════════════════
# 헬퍼: 어드민 권한 확인 (role_code 001)
# ════════════════════════════════════════════
def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role_code") != "001":
        raise HTTPException(status_code=403, detail="어드민만 접근 가능합니다.")
    return current_user


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _app_to_dict(app: dict) -> dict:
    return {
        "status":           app["status"],
        "application_id":  app["id"],
        "applied_at":       app["created_at"],
        "reviewed_at":      app.get("reviewed_at"),
        "platform_fee_rate": float(app["platform_fee_rate"]) if app.get("platform_fee_rate") else None,
        "review_note":      app.get("review_note") if app["status"] == "rejected" else None,
    }


# ════════════════════════════════════════════
# POST /experts/apply — 전문가 등록 신청
# ════════════════════════════════════════════
@router.post("/apply")
def expert_apply(
    req: ExpertApplyRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    전문가 등록 신청.

    제약조건:
    - 본인인증 필수
    - 플랫폼 이용 약관 동의 필수
    - 사업자등록번호 형식 (숫자 10자리)
    - 동일 타입 pending/approved 중복 불가
    """
    supabase = get_supabase()

    # 1. 본인인증 확인
    if not current_user.get("identity_verified"):
        raise HTTPException(status_code=403, detail="본인인증이 필요합니다.")

    # 2. 플랫폼 이용 약관 동의 확인
    if not req.terms_agreed:
        raise HTTPException(status_code=400, detail="플랫폼 이용 약관에 동의해야 합니다.")

    # 3. expert_type 유효성 확인
    if req.expert_type not in ("safety", "fix", "consult"):
        raise HTTPException(status_code=400, detail="expert_type은 safety / fix / consult 중 하나여야 합니다.")

    # 4. 사업자번호 형식 확인 (숫자 10자리)
    biz_no = re.sub(r"[^0-9]", "", req.biz_number)
    if len(biz_no) != 10:
        raise HTTPException(status_code=400, detail="사업자등록번호가 올바르지 않습니다 (숫자 10자리).")

    # 5. 중복 신청 확인 (pending / approved)
    existing = supabase.table("expert_applications") \
        .select("id, status") \
        .eq("user_id", current_user["id"]) \
        .eq("expert_type", req.expert_type) \
        .in_("status", ["pending", "approved"]) \
        .limit(1).execute()
    if existing.data:
        raise HTTPException(
            status_code=409,
            detail="이미 신청 중이거나 활성화된 등록이 있습니다."
        )

    # 6. terms_agreed_at 파싱
    try:
        agreed_at = req.terms_agreed_at.replace("Z", "+00:00")
    except Exception:
        agreed_at = _now_iso()

    # 7. 저장
    now = _now_iso()
    res = supabase.table("expert_applications").insert({
        "user_id":          current_user["id"],
        "expert_type":      req.expert_type,
        "status":           "pending",
        "biz_name":         req.biz_name,
        "biz_number":       biz_no,
        "representative":   req.representative,
        "contact_phone":    req.contact_phone,
        "service_regions":  req.service_regions,
        "intro_text":       req.intro_text,
        "terms_agreed":     req.terms_agreed,
        "terms_agreed_at":  agreed_at,
        "identity_verified": current_user.get("identity_verified", False),
        "type_data":        req.type_data,
        "created_at":       now,
        "updated_at":       now,
    }).execute()

    if not res.data:
        raise HTTPException(status_code=500, detail="저장 실패")

    return {
        "success": True,
        "data": {
            "application_id": res.data[0]["id"],
            "status":         "pending",
            "message":        "등록이 접수되었습니다. 영업일 기준 3~5일 내 검토 후 이메일로 안내드립니다."
        }
    }


# ════════════════════════════════════════════
# GET /experts/status — 내 전문가 등록 현황
# ════════════════════════════════════════════
@router.get("/status")
def expert_status(current_user: dict = Depends(get_current_user)):
    """
    내 전문가 등록 현황 (3개 타입별).

    응답:
    ```json
    {
      "success": true,
      "data": {
        "identity_verified": true,
        "applications": {
          "safety":  { "status": "pending", ... },
          "fix":     { "status": "approved", ... },
          "consult": null
        }
      }
    }
    ```
    """
    supabase = get_supabase()
    apps_res = supabase.table("expert_applications").select(
        "id, expert_type, status, created_at, reviewed_at, platform_fee_rate, review_note"
    ).eq("user_id", current_user["id"]).execute()

    applications: Dict[str, Any] = {"safety": None, "fix": None, "consult": None}
    for app in (apps_res.data or []):
        applications[app["expert_type"]] = _app_to_dict(app)

    return {
        "success": True,
        "data": {
            "identity_verified": current_user.get("identity_verified") or False,
            "applications":      applications,
        }
    }


# ════════════════════════════════════════════
# PATCH /experts/approve/:id — 어드민 승인
# (admin.taieng.co.kr 전용, role_code 001)
# ════════════════════════════════════════════
@router.patch("/approve/{application_id}")
def expert_approve(
    application_id: str,
    req: ExpertApproveRequest,
    current_user: dict = Depends(require_admin),
):
    """
    어드민 전용: 전문가 등록 승인.
    - platform_fee_rate: 플랫폼 이용료율 (%)
    """
    supabase = get_supabase()
    app_res = supabase.table("expert_applications") \
        .select("id, status, user_id") \
        .eq("id", application_id).limit(1).execute()

    if not app_res.data:
        raise HTTPException(status_code=404, detail="신청을 찾을 수 없습니다.")
    if app_res.data[0]["status"] != "pending":
        raise HTTPException(status_code=400, detail="pending 상태의 신청만 승인 가능합니다.")

    now = _now_iso()
    supabase.table("expert_applications").update({
        "status":           "approved",
        "reviewed_by":      current_user["id"],
        "reviewed_at":      now,
        "platform_fee_rate": req.platform_fee_rate,
        "review_note":      req.review_note,
        "updated_at":       now,
    }).eq("id", application_id).execute()

    # TODO: 이메일 발송 (승인 안내)
    log.info(f"[EXPERT APPROVE] {application_id} 승인, reviewer={current_user['id']}")

    return {
        "success": True,
        "data": {
            "application_id":   application_id,
            "status":           "approved",
            "platform_fee_rate": req.platform_fee_rate,
        }
    }


# ════════════════════════════════════════════
# PATCH /experts/reject/:id — 어드민 반려
# ════════════════════════════════════════════
@router.patch("/reject/{application_id}")
def expert_reject(
    application_id: str,
    req: ExpertRejectRequest,
    current_user: dict = Depends(require_admin),
):
    """\uc5b4\ub4dc\ubbfc \uc804\uc6a9: \uc804\ubb38\uac00 \ub4f1\ub85d \ubc18\ub824."""
    supabase = get_supabase()
    app_res = supabase.table("expert_applications") \
        .select("id, status") \
        .eq("id", application_id).limit(1).execute()
    if not app_res.data:
        raise HTTPException(status_code=404, detail="\uc2e0\uccad\uc744 \ucc3e\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.")
    if app_res.data[0]["status"] != "pending":
        raise HTTPException(status_code=400, detail="pending \uc0c1\ud0dc\uc758 \uc2e0\uccad\ub9cc \ubc18\ub824 \uac00\ub2a5\ud569\ub2c8\ub2e4.")

    now = _now_iso()
    supabase.table("expert_applications").update({
        "status":      "rejected",
        "reviewed_by": current_user["id"],
        "reviewed_at": now,
        "review_note": req.review_note,
        "updated_at":  now,
    }).eq("id", application_id).execute()

    return {"success": True, "data": {"application_id": application_id, "status": "rejected"}}


# ════════════════════════════════════════════
# GET /experts/list — 어드민: 신청 목록 조회
# ════════════════════════════════════════════
@router.get("/list")
def expert_list(
    page:        int          = Query(1, ge=1),
    page_size:   int          = Query(20, ge=1, le=100),
    status:      Optional[str] = Query(None, description="pending | approved | rejected | inactive"),
    expert_type: Optional[str] = Query(None, description="safety | fix | consult"),
    current_user: dict = Depends(require_admin),
):
    """
    어드민 전용: 전신청 목록.
    admin.taieng.co.kr 어드민만 접근 가능.
    """
    supabase = get_supabase()
    query = supabase.table("expert_applications").select(
        "id, user_id, expert_type, status, biz_name, biz_number, contact_phone, "
        "service_regions, terms_agreed, identity_verified, platform_fee_rate, "
        "reviewed_at, review_note, created_at, updated_at",
        count="exact",
    )
    if status:
        query = query.eq("status", status)
    if expert_type:
        query = query.eq("expert_type", expert_type)

    offset = (page - 1) * page_size
    res = query.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()

    return {
        "success": True,
        "data": {
            "items":       res.data or [],
            "total":       res.count or 0,
            "page":        page,
            "page_size":   page_size,
            "total_pages": ((res.count or 0) + page_size - 1) // page_size,
        }
    }
