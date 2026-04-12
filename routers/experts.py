# routers/experts.py — v1.1.0
# 전문가 등록 신청 / 현황 / 어드민 승인 API
#
# v1.1.0: expert_type EXPERT/CONSULTING/REPAIR 체계로 전환
#         entity_type (사업자 구분) + 허용 매트릭스 검증 추가
#         선임(EXPERT) 전용 근무형태(상주/비상주) + 상세 필드 추가
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
from pydantic import BaseModel, field_validator

from routers.auth import get_current_user
from db.supabase_client import get_supabase

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/experts", tags=["전문가"])


# ════════════════════════════════════════════
# 허용 매트릭스 (확정)
# EXPERT     = 선임대행 (개인·개인사업자·간이과세·법인 모두 허용)
# CONSULTING = 컨설팅  (동일)
# REPAIR     = 수선중개 (개인 불가 → 사업자 등록 필수)
# ════════════════════════════════════════════
ALLOWED_ENTITY_TYPES: Dict[str, set] = {
    "EXPERT":     {"INDIVIDUAL", "SOLE_PROPRIETOR", "SIMPLIFIED_TAX", "CORPORATION"},
    "CONSULTING": {"INDIVIDUAL", "SOLE_PROPRIETOR", "SIMPLIFIED_TAX", "CORPORATION"},
    "REPAIR":     {"SOLE_PROPRIETOR", "SIMPLIFIED_TAX", "CORPORATION"},
}

VALID_EXPERT_TYPES  = set(ALLOWED_ENTITY_TYPES.keys())
VALID_ENTITY_TYPES  = {"INDIVIDUAL", "SOLE_PROPRIETOR", "SIMPLIFIED_TAX", "CORPORATION"}
VALID_WORK_TYPES    = {"RESIDENT", "NON_RESIDENT"}


def validate_expert_entity(expert_type: str, entity_type: str) -> None:
    """expert_type × entity_type 허용 매트릭스 검증"""
    allowed = ALLOWED_ENTITY_TYPES.get(expert_type, set())
    if entity_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"{expert_type} 유형은 {entity_type} 사업자로 신청할 수 없습니다.",
        )


def validate_work_types(expert_type: str, work_types: Optional[List[str]]) -> None:
    """선임(EXPERT) 전용 근무형태 검증"""
    if expert_type != "EXPERT":
        return
    if not work_types:
        raise HTTPException(400, "선임대행은 근무형태를 최소 1개 선택해야 합니다.")
    invalid = set(work_types) - VALID_WORK_TYPES
    if invalid:
        raise HTTPException(400, f"유효하지 않은 근무형태: {invalid}")


# ════════════════════════════════════════════
# Pydantic 모델
# ════════════════════════════════════════════

class ResidentDetail(BaseModel):
    """상주 선임 상세 정보"""
    employment_type: Optional[str] = None   # REGULAR / CONTRACT / DISPATCH / NEGOTIATE
    immediate_join:  Optional[str] = None   # Y / N
    salary_min:      Optional[int] = None
    salary_max:      Optional[int] = None


class NonResidentDetail(BaseModel):
    """비상주 선임 상세 정보"""
    visit_per_month: Optional[int] = None
    remote_support:  Optional[str] = None   # Y / N
    visit_price:     Optional[int] = None


class ExpertApplyBody(BaseModel):
    user_id:      str
    expert_type:  str   # EXPERT / CONSULTING / REPAIR
    entity_type:  str   # INDIVIDUAL / SOLE_PROPRIETOR / SIMPLIFIED_TAX / CORPORATION

    biz_name:        str
    biz_number:      str                  # 숫자 10자리
    representative:  Optional[str] = None
    contact_phone:   str
    service_regions: List[str]
    intro_text:      Optional[str] = None
    terms_agreed:    bool
    terms_agreed_at: str                  # ISO datetime

    # 선임(EXPERT) 전용
    work_types:          Optional[List[str]]         = None
    resident_detail:     Optional[ResidentDetail]    = None
    non_resident_detail: Optional[NonResidentDetail] = None

    type_data: Dict[str, Any] = {}

    @field_validator("expert_type")
    @classmethod
    def check_expert_type(cls, v: str) -> str:
        if v not in VALID_EXPERT_TYPES:
            raise ValueError(f"expert_type은 {VALID_EXPERT_TYPES} 중 하나여야 합니다.")
        return v

    @field_validator("entity_type")
    @classmethod
    def check_entity_type(cls, v: str) -> str:
        if v not in VALID_ENTITY_TYPES:
            raise ValueError(f"entity_type은 {VALID_ENTITY_TYPES} 중 하나여야 합니다.")
        return v

    @field_validator("work_types")
    @classmethod
    def check_work_types(cls, v: Optional[List[str]], info) -> Optional[List[str]]:
        # expert_type이 아직 검증 안 됐을 수 있으므로 None-safe하게 처리
        # 크로스필드 검증은 apply 엔드포인트에서 validate_work_types() 호출
        return v


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
    req: ExpertApplyBody,
    current_user: dict = Depends(get_current_user),
):
    """
    전문가 등록 신청.

    expert_type: EXPERT(선임대행) / CONSULTING(컨설팅) / REPAIR(수선중개)
    entity_type: INDIVIDUAL / SOLE_PROPRIETOR / SIMPLIFIED_TAX / CORPORATION

    허용 매트릭스:
    - EXPERT / CONSULTING: 모든 사업자 유형 허용
    - REPAIR: SOLE_PROPRIETOR / SIMPLIFIED_TAX / CORPORATION 만 허용 (개인 불가)

    EXPERT 전용: work_types(상주/비상주) 최소 1개 필수
    """
    supabase = get_supabase()

    # 1. 본인인증 확인
    if not current_user.get("identity_verified"):
        raise HTTPException(status_code=403, detail="본인인증이 필요합니다.")

    # 2. 약관 동의 확인
    if not req.terms_agreed:
        raise HTTPException(status_code=400, detail="플랫폼 이용 약관에 동의해야 합니다.")

    # 3. 허용 매트릭스 검증 (expert_type × entity_type)
    validate_expert_entity(req.expert_type, req.entity_type)

    # 4. 선임 근무형태 검증
    validate_work_types(req.expert_type, req.work_types)

    # 5. 사업자번호 형식 (숫자 10자리)
    biz_no = re.sub(r"[^0-9]", "", req.biz_number)
    if len(biz_no) != 10:
        raise HTTPException(status_code=400, detail="사업자등록번호가 올바르지 않습니다 (숫자 10자리).")

    # 6. 중복 신청 확인 (pending / approved)
    existing = (
        supabase.table("expert_applications")
        .select("id, status")
        .eq("user_id", current_user["id"])
        .eq("expert_type", req.expert_type)
        .in_("status", ["pending", "approved"])
        .limit(1)
        .execute()
    )
    if existing.data:
        raise HTTPException(status_code=409, detail="이미 신청 중이거나 활성화된 등록이 있습니다.")

    # 7. terms_agreed_at 파싱
    try:
        agreed_at = req.terms_agreed_at.replace("Z", "+00:00")
    except Exception:
        agreed_at = _now_iso()

    # 8. 상주/비상주 상세 펼치기
    resident     = req.resident_detail.model_dump()     if req.resident_detail     else {}
    non_resident = req.non_resident_detail.model_dump() if req.non_resident_detail else {}

    # 9. 저장
    now = _now_iso()
    row = {
        "user_id":          current_user["id"],
        "expert_type":      req.expert_type,
        "entity_type":      req.entity_type,
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
        # 선임 전용
        "work_types":       req.work_types,
        "employment_type":  resident.get("employment_type"),
        "immediate_join":   resident.get("immediate_join"),
        "salary_min":       resident.get("salary_min"),
        "salary_max":       resident.get("salary_max"),
        "visit_per_month":  non_resident.get("visit_per_month"),
        "remote_support":   non_resident.get("remote_support"),
        "visit_price":      non_resident.get("visit_price"),
        "created_at":       now,
        "updated_at":       now,
    }
    res = supabase.table("expert_applications").insert(row).execute()

    if not res.data:
        raise HTTPException(status_code=500, detail="저장 실패")

    return {
        "success": True,
        "data": {
            "application_id": res.data[0]["id"],
            "status":         "pending",
            "message":        "등록이 접수되었습니다. 영업일 기준 3~5일 내 검토 후 이메일로 안내드립니다.",
        },
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
        "id, expert_type, entity_type, status, created_at, reviewed_at, "
        "platform_fee_rate, review_note, work_types"
    ).eq("user_id", current_user["id"]).execute()

    applications: Dict[str, Any] = {"EXPERT": None, "CONSULTING": None, "REPAIR": None}
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
        "id, user_id, expert_type, entity_type, status, biz_name, biz_number, contact_phone, "
        "service_regions, terms_agreed, identity_verified, platform_fee_rate, "
        "work_types, employment_type, salary_min, salary_max, "
        "visit_per_month, remote_support, visit_price, "
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
