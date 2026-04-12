"""
routers/experts.py — v2.1.0
전문가 등록 신청 / 현황 / 어드민 승인·반려 / 활성 테이블 자동 적재 / Storage 서류 업로드

v2.1.0: Storage 서류 업로드 연동 추가
  - POST /experts/upload-url             : Signed Upload URL 발급
  - POST /experts/attach                 : 업로드 완료 후 attachments 등록
  - GET  /experts/admin/{id}/documents   : 어드민 서류 조회 (Signed URL 재발급)

v2.0.0: 전체 데이터 적재 구조로 재설계
  - ExpertApplyBody 전체 필드 (사업자·자격증·인허가·근무형태)
  - POST /experts/verify-biz          : 국세청 사업자번호 검증
  - POST /experts/apply               : 신청 접수
  - GET  /experts/my-status           : 내 신청 현황
  - GET  /experts/admin/list          : 어드민 신청 목록
  - PATCH /experts/admin/{id}/approve : 승인 + 활성 테이블 자동 적재
  - PATCH /experts/admin/{id}/reject  : 반려

prefix: /experts  (main.py에서 지정)
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator, model_validator

from db.supabase_client import get_supabase
from routers.auth import get_current_user

log    = logging.getLogger(__name__)
router = APIRouter()   # prefix는 main.py에서 지정

NTS_API_KEY = os.getenv("NTS_API_KEY", "")

# ── 허용 매트릭스 ────────────────────────────────────────────────────────
ALLOWED_ENTITY_TYPES: Dict[str, set] = {
    "EXPERT":     {"INDIVIDUAL", "SOLE_PROPRIETOR", "SIMPLIFIED_TAX", "CORPORATION"},
    "CONSULTING": {"INDIVIDUAL", "SOLE_PROPRIETOR", "SIMPLIFIED_TAX", "CORPORATION"},
    "REPAIR":     {"SOLE_PROPRIETOR", "SIMPLIFIED_TAX", "CORPORATION"},
}
VALID_EXPERT_TYPES = set(ALLOWED_ENTITY_TYPES.keys())
VALID_ENTITY_TYPES = {"INDIVIDUAL", "SOLE_PROPRIETOR", "SIMPLIFIED_TAX", "CORPORATION"}
VALID_WORK_TYPES   = {"RESIDENT", "NON_RESIDENT"}


# ── 유틸 ──────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_user_name(user_id: str) -> str:
    try:
        supabase = get_supabase()
        res = supabase.table("users").select("identity_name, name").eq("id", user_id).limit(1).execute()
        if res.data:
            u = res.data[0]
            return u.get("identity_name") or u.get("name") or ""
    except Exception as e:
        log.warning(f"[EXPERT] _get_user_name failed: {e}")
    return ""


def _require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role_code") != "001":
        raise HTTPException(status_code=403, detail="어드민만 접근 가능합니다.")
    return current_user


# ── Pydantic 모델 ──────────────────────────────────────────────────────────
class BizVerifyBody(BaseModel):
    biz_number: str


class ExpertApplyBody(BaseModel):
    # 필수
    user_id:     str
    expert_type: str
    entity_type: str

    # 사업자 정보
    biz_number:        Optional[str]  = None
    biz_name:          Optional[str]  = None
    biz_ceo_name:      Optional[str]  = None
    biz_type:          Optional[str]  = None
    biz_item:          Optional[str]  = None
    biz_open_date:     Optional[str]  = None
    biz_address:       Optional[str]  = None
    biz_zipcode:       Optional[str]  = None
    biz_verify_status: Optional[str]  = None
    biz_verify_raw:    Optional[dict] = None

    # 법인 전용
    corp_number:         Optional[str] = None
    corp_established_at: Optional[str] = None

    # 자격증 (선임/컨설팅)
    license_type:      Optional[str] = None
    license_number:    Optional[str] = None
    license_issued_at: Optional[str] = None
    license_issuer:    Optional[str] = None

    # 인허가 (수선)
    permit_type:       Optional[str] = None
    permit_number:     Optional[str] = None
    permit_doc_number: Optional[str] = None

    # 활동 정보
    contact_phone:   Optional[str]       = None
    service_regions: Optional[List[str]] = None
    expert_fields:   Optional[List[str]] = None
    career_summary:  Optional[str]       = None
    career_years:    Optional[int]       = None
    intro_text:      Optional[str]       = None

    # 선임 전용 근무형태
    work_types:      Optional[List[str]] = None
    employment_type: Optional[str]       = None
    immediate_join:  Optional[str]       = None
    salary_min:      Optional[int]       = None
    salary_max:      Optional[int]       = None
    visit_per_month: Optional[int]       = None
    remote_support:  Optional[str]       = None
    visit_price:     Optional[int]       = None

    # 법적 동의
    terms_agreed:       bool = False
    legal_terms_agreed: bool = False

    @field_validator("expert_type")
    @classmethod
    def check_expert_type(cls, v: str) -> str:
        if v not in ALLOWED_ENTITY_TYPES:
            raise ValueError(f"expert_type은 {VALID_EXPERT_TYPES} 중 하나여야 합니다.")
        return v

    @field_validator("entity_type")
    @classmethod
    def check_entity_type(cls, v: str) -> str:
        if v not in VALID_ENTITY_TYPES:
            raise ValueError(f"entity_type은 {VALID_ENTITY_TYPES} 중 하나여야 합니다.")
        return v

    @model_validator(mode="after")
    def cross_validate(self) -> "ExpertApplyBody":
        allowed = ALLOWED_ENTITY_TYPES.get(self.expert_type, set())
        if self.entity_type not in allowed:
            raise ValueError(f"{self.expert_type}은 {self.entity_type}으로 신청할 수 없습니다.")
        if self.expert_type == "EXPERT" and not self.work_types:
            raise ValueError("선임대행은 근무형태를 최소 1개 선택해야 합니다.")
        if self.work_types:
            invalid = set(self.work_types) - VALID_WORK_TYPES
            if invalid:
                raise ValueError(f"유효하지 않은 근무형태: {invalid}")
        return self


class ApproveBody(BaseModel):
    platform_fee_rate: float = 10.0
    review_note:       Optional[str] = None


class RejectBody(BaseModel):
    reason: str


# ── 승인 시 활성 테이블 자동 적재 ─────────────────────────────────────────
def _activate_expert(app: dict, now: str) -> None:
    supabase     = get_supabase()
    etype        = app["expert_type"]
    entity       = app["entity_type"]
    regions_list = app.get("service_regions") or []
    regions_str  = ",".join(regions_list)

    if etype in ("EXPERT", "CONSULTING") and entity == "CORPORATION":
        supabase.table("safety_agencies").insert({
            "user_id":         app["user_id"],
            "application_id":  app["id"],
            "agency_name":     app.get("biz_name", ""),
            "phone":           app.get("contact_phone", ""),
            "business_no":     app.get("biz_number", ""),
            "license_no":      app.get("permit_number", ""),
            "region_sido":     regions_list,
            "specialties":     app.get("expert_fields") or [],
            "entity_type":     entity,
            "expert_type":     etype,
            "corp_number":     app.get("corp_number", ""),
            "expert_fields":   app.get("expert_fields") or [],
            "verified_status": "APPROVED",
            "is_active":       True,
            "created_at":      now,
            "updated_at":      now,
        }).execute()
        log.info(f"[EXPERT APPROVE] safety_agencies 적재 — app={app['id']}")

    elif etype in ("EXPERT", "CONSULTING"):
        supabase.table("safety_personnel").insert({
            "user_id":              app["user_id"],
            "application_id":       app["id"],
            "name":                 _get_user_name(app["user_id"]),
            "phone":                app.get("contact_phone", ""),
            "qualification_type":   app.get("license_type", ""),
            "qualification_no":     app.get("license_number", ""),
            "career_years":         app.get("career_years") or 0,
            "region_sido":          regions_str,
            "industry_specialties": app.get("expert_fields") or [],
            "entity_type":          entity,
            "expert_type":          etype,
            "biz_number":           app.get("biz_number", ""),
            "biz_name":             app.get("biz_name", ""),
            "work_types":           app.get("work_types") or [],
            "employment_type":      app.get("employment_type", ""),
            "immediate_join":       app.get("immediate_join", ""),
            "salary_min":           app.get("salary_min"),
            "salary_max":           app.get("salary_max"),
            "visit_per_month":      app.get("visit_per_month"),
            "remote_support":       app.get("remote_support", ""),
            "visit_price":          app.get("visit_price"),
            "verified_status":      "APPROVED",
            "is_active":            True,
            "created_at":           now,
            "updated_at":           now,
        }).execute()
        log.info(f"[EXPERT APPROVE] safety_personnel 적재 — app={app['id']}")

    elif etype == "REPAIR":
        supabase.table("repair_companies").insert({
            "user_id":           app["user_id"],
            "application_id":    app["id"],
            "company_name":      app.get("biz_name", ""),
            "phone":             app.get("contact_phone", ""),
            "business_no":       app.get("biz_number", ""),
            "license_types":     [app.get("permit_type")] if app.get("permit_type") else [],
            "equipment_types":   app.get("expert_fields") or [],
            "region_sido":       regions_str,
            "entity_type":       entity,
            "permit_type":       app.get("permit_type", ""),
            "permit_number":     app.get("permit_number", ""),
            "permit_doc_number": app.get("permit_doc_number", ""),
            "biz_type":          app.get("biz_type", ""),
            "biz_item":          app.get("biz_item", ""),
            "expert_fields":     app.get("expert_fields") or [],
            "verified_status":   "APPROVED",
            "is_active":         True,
            "created_at":        now,
            "updated_at":        now,
        }).execute()
        log.info(f"[EXPERT APPROVE] repair_companies 적재 — app={app['id']}")


# ── 엔드포인트 ────────────────────────────────────────────────────────────

@router.post("/verify-biz")
async def verify_biz(body: BizVerifyBody):
    """국세청 사업자번호 상태 조회 — POST /experts/verify-biz"""
    if not NTS_API_KEY:
        raise HTTPException(status_code=503, detail="사업자번호 검증 서비스 준비 중입니다.")
    biz_no = re.sub(r"[^0-9]", "", body.biz_number)
    if len(biz_no) != 10:
        raise HTTPException(status_code=400, detail="사업자등록번호는 숫자 10자리여야 합니다.")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.odcloud.kr/api/nts-businessman/v1/status",
                params={"serviceKey": NTS_API_KEY},
                json={"b_no": [biz_no]},
            )
            resp.raise_for_status()
            nts_data = resp.json()
    except httpx.HTTPStatusError as e:
        log.error(f"[BIZ VERIFY] NTS HTTP error: {e}")
        raise HTTPException(status_code=502, detail="국세청 API 오류")
    except Exception as e:
        log.error(f"[BIZ VERIFY] error: {e}")
        raise HTTPException(status_code=502, detail="사업자번호 조회 실패")

    items = nts_data.get("data", [])
    if not items:
        raise HTTPException(status_code=404, detail="사업자번호 조회 결과 없음")
    item = items[0]
    b_stt_cd    = item.get("b_stt_cd", "")
    status_map  = {"01": "VALID", "02": "CLOSED", "03": "SUSPENDED"}
    tax_type    = item.get("tax_type", "")
    entity_hint = "SIMPLIFIED_TAX" if "간이" in tax_type else "SOLE_PROPRIETOR"

    return {
        "status": "success",
        "data": {
            "biz_number":    biz_no,
            "verify_status": status_map.get(b_stt_cd, "UNVERIFIED"),
            "biz_name":      item.get("b_nm", ""),
            "ceo_name":      item.get("p_nm", ""),
            "biz_type":      item.get("b_type", ""),
            "biz_item":      item.get("b_sector", ""),
            "tax_type":      tax_type,
            "entity_hint":   entity_hint,
            "raw":           item,
        },
    }


@router.post("/apply")
def expert_apply(
    body: ExpertApplyBody,
    current_user: dict = Depends(get_current_user),
):
    """전문가 등록 신청 — POST /experts/apply"""
    supabase = get_supabase()

    if not current_user.get("identity_verified"):
        raise HTTPException(status_code=403, detail="본인인증이 필요합니다.")
    if not body.terms_agreed or not body.legal_terms_agreed:
        raise HTTPException(status_code=400, detail="이용 약관 및 법적 동의가 필요합니다.")

    # 사업자번호 검증 (개인 제외)
    biz_no = None
    if body.entity_type != "INDIVIDUAL":
        raw_no = re.sub(r"[^0-9]", "", body.biz_number or "")
        if len(raw_no) != 10:
            raise HTTPException(status_code=400, detail="사업자등록번호가 올바르지 않습니다 (숫자 10자리).")
        biz_no = raw_no

    # 중복 신청 확인
    dup = (
        supabase.table("expert_applications")
        .select("id, status")
        .eq("user_id", current_user["id"])
        .eq("expert_type", body.expert_type)
        .in_("status", ["PENDING", "AI_REVIEWING", "REVIEWING", "APPROVED"])
        .limit(1)
        .execute()
    )
    if dup.data:
        raise HTTPException(status_code=409, detail="이미 신청 중이거나 활성화된 등록이 있습니다.")

    now = _now_iso()
    row: Dict[str, Any] = {
        "user_id":     current_user["id"],
        "expert_type": body.expert_type,
        "entity_type": body.entity_type,
        "status":      "PENDING",
        "biz_number":           biz_no,
        "biz_name":             body.biz_name,
        "biz_ceo_name":         body.biz_ceo_name,
        "biz_type":             body.biz_type,
        "biz_item":             body.biz_item,
        "biz_open_date":        body.biz_open_date,
        "biz_address":          body.biz_address,
        "biz_zipcode":          body.biz_zipcode,
        "biz_verify_status":    body.biz_verify_status,
        "biz_verify_raw":       body.biz_verify_raw,
        "corp_number":          body.corp_number,
        "corp_established_at":  body.corp_established_at,
        "license_type":         body.license_type,
        "license_number":       body.license_number,
        "license_issued_at":    body.license_issued_at,
        "license_issuer":       body.license_issuer,
        "permit_type":          body.permit_type,
        "permit_number":        body.permit_number,
        "permit_doc_number":    body.permit_doc_number,
        "contact_phone":        body.contact_phone,
        "service_regions":      body.service_regions,
        "expert_fields":        body.expert_fields,
        "career_summary":       body.career_summary,
        "career_years":         body.career_years,
        "intro_text":           body.intro_text,
        "work_types":           body.work_types,
        "employment_type":      body.employment_type,
        "immediate_join":       body.immediate_join,
        "salary_min":           body.salary_min,
        "salary_max":           body.salary_max,
        "visit_per_month":      body.visit_per_month,
        "remote_support":       body.remote_support,
        "visit_price":          body.visit_price,
        "terms_agreed":         body.terms_agreed,
        "legal_terms_agreed":   body.legal_terms_agreed,
        "legal_terms_agreed_at": now,
        "identity_verified":    current_user.get("identity_verified", False),
        "created_at": now,
        "updated_at": now,
    }
    res = supabase.table("expert_applications").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="저장 실패")

    return {
        "status": "success",
        "data": {
            "application_id": res.data[0]["id"],
            "status":         "PENDING",
            "message":        "등록이 접수되었습니다. 영업일 기준 3~5일 내 검토 후 이메일로 안내드립니다.",
        },
    }


@router.get("/my-status")
def my_status(
    user_id: str = Query(..., description="회원 UUID"),
    current_user: dict = Depends(get_current_user),
):
    """내 전문가 신청 현황 — GET /experts/my-status?user_id={uuid}"""
    if current_user["id"] != user_id and current_user.get("role_code") != "001":
        raise HTTPException(status_code=403, detail="권한이 없습니다.")

    supabase = get_supabase()
    res = supabase.table("expert_applications").select(
        "id, expert_type, entity_type, status, reject_reason, approved_at, "
        "work_types, biz_name, contact_phone, service_regions, expert_fields, "
        "created_at, updated_at"
    ).eq("user_id", user_id).order("created_at", desc=True).execute()

    grouped: Dict[str, Any] = {k: None for k in VALID_EXPERT_TYPES}
    for app in (res.data or []):
        et = app.get("expert_type", "")
        if et in grouped and grouped[et] is None:
            grouped[et] = app

    return {
        "status": "success",
        "data": {
            "identity_verified": current_user.get("identity_verified", False),
            "applications":      grouped,
            "all":               res.data or [],
        },
    }


@router.get("/admin/list")
def admin_list(
    status:      Optional[str] = Query(None),
    expert_type: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    keyword:     Optional[str] = Query(None, description="사업자명 또는 연락처"),
    page: int = Query(1,  ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(_require_admin),
):
    """어드민: 전문가 신청 목록 — GET /experts/admin/list"""
    supabase = get_supabase()
    q = supabase.table("expert_applications").select(
        "id, user_id, expert_type, entity_type, status, "
        "biz_name, biz_number, biz_ceo_name, contact_phone, "
        "service_regions, expert_fields, work_types, "
        "license_type, license_number, permit_type, permit_number, "
        "reject_reason, approved_at, trust_level, created_at, updated_at",
        count="exact",
    )
    if status:      q = q.eq("status", status)
    if expert_type: q = q.eq("expert_type", expert_type)
    if entity_type: q = q.eq("entity_type", entity_type)
    if keyword:     q = q.or_(f"biz_name.ilike.%{keyword}%,contact_phone.ilike.%{keyword}%")

    offset = (page - 1) * size
    res    = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    total  = res.count or 0

    return {
        "status": "success",
        "data": {
            "items":       res.data or [],
            "total":       total,
            "page":        page,
            "size":        size,
            "total_pages": (total + size - 1) // size,
        },
    }


@router.patch("/admin/{application_id}/approve")
def admin_approve(
    application_id: str,
    body: ApproveBody,
    current_user: dict = Depends(_require_admin),
):
    """
    어드민: 전문가 승인 + 활성 테이블 자동 적재
    PATCH /experts/admin/{application_id}/approve

    EXPERT/CONSULTING + CORPORATION → safety_agencies
    EXPERT/CONSULTING + 그 외       → safety_personnel
    REPAIR                          → repair_companies
    """
    supabase = get_supabase()
    app_res  = (
        supabase.table("expert_applications")
        .select("*")
        .eq("id", application_id)
        .limit(1)
        .execute()
    )
    if not app_res.data:
        raise HTTPException(status_code=404, detail="신청을 찾을 수 없습니다.")
    app = app_res.data[0]
    if app["status"] == "APPROVED":
        raise HTTPException(status_code=400, detail="이미 승인된 신청입니다.")
    if app["status"] == "REJECTED":
        raise HTTPException(status_code=400, detail="반려된 신청은 재승인할 수 없습니다.")

    now = _now_iso()
    supabase.table("expert_applications").update({
        "status":            "APPROVED",
        "approved_at":       now,
        "platform_fee_rate": body.platform_fee_rate,
        "review_note":       body.review_note,
        "reviewed_by":       current_user["id"],
        "updated_at":        now,
    }).eq("id", application_id).execute()

    app["id"] = application_id
    try:
        _activate_expert(app, now)
    except Exception as e:
        log.error(f"[EXPERT APPROVE] _activate_expert 실패: {e}")

    log.info(f"[EXPERT APPROVE] {application_id} — reviewer={current_user['id']}")
    return {
        "status": "success",
        "data": {
            "application_id":    application_id,
            "status":            "APPROVED",
            "platform_fee_rate": body.platform_fee_rate,
            "approved_at":       now,
        },
    }


@router.patch("/admin/{application_id}/reject")
def admin_reject(
    application_id: str,
    body: RejectBody,
    current_user: dict = Depends(_require_admin),
):
    """어드민: 전문가 신청 반려 — PATCH /experts/admin/{application_id}/reject"""
    supabase = get_supabase()
    app_res  = (
        supabase.table("expert_applications")
        .select("id, status")
        .eq("id", application_id)
        .limit(1)
        .execute()
    )
    if not app_res.data:
        raise HTTPException(status_code=404, detail="신청을 찾을 수 없습니다.")
    if app_res.data[0]["status"] == "APPROVED":
        raise HTTPException(status_code=400, detail="승인된 신청은 반려할 수 없습니다.")

    now = _now_iso()
    supabase.table("expert_applications").update({
        "status":        "REJECTED",
        "reject_reason": body.reason,
        "reviewed_by":   current_user["id"],
        "updated_at":    now,
    }).eq("id", application_id).execute()

    log.info(f"[EXPERT REJECT] {application_id} — reviewer={current_user['id']}")
    return {
        "status": "success",
        "data": {
            "application_id": application_id,
            "status":         "REJECTED",
            "reason":         body.reason,
        },
    }


# ════════════════════════════════════════════════════════════════════════
# Storage 서류 업로드 — expert-documents 버킷
# 경로 규칙: {application_id}/{doc_type}/{uuid}_{filename}
# ════════════════════════════════════════════════════════════════════════

ALLOWED_DOC_TYPES: Dict[str, str] = {
    "BIZ_REG":   "사업자등록증",
    "CORP_REG":  "법인등기부등본",
    "LICENSE":   "자격증",
    "PERMIT":    "인허가증",
    "INSURANCE": "배상책임보험",
    "PORTFOLIO": "포트폴리오",
}
STORAGE_BUCKET   = "expert-documents"
MAX_FILE_SIZE    = 20 * 1024 * 1024   # 20 MB


class UploadUrlBody(BaseModel):
    application_id: str
    doc_type:       str   # BIZ_REG / CORP_REG / LICENSE / PERMIT / INSURANCE / PORTFOLIO
    file_name:      str
    file_size:      int   # bytes


class AttachBody(BaseModel):
    application_id: str
    doc_type:       str
    file_path:      str   # Storage 경로 (URL 아님)
    file_name:      str
    file_size:      int
    mime_type:      str


@router.post("/upload-url")
def get_upload_url(
    body: UploadUrlBody,
    current_user: dict = Depends(get_current_user),
):
    """
    Supabase Storage Signed Upload URL 발급
    POST /experts/upload-url

    프론트에서 반환된 signed_url로 PUT 직접 업로드.
    업로드 완료 후 /experts/attach 호출하여 attachments 등록.
    """
    if body.file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="파일 크기는 20MB 이하여야 합니다.")
    if body.doc_type not in ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 doc_type입니다. 허용: {list(ALLOWED_DOC_TYPES.keys())}")

    supabase = get_supabase()

    # 신청서 소유권 확인 (본인 또는 어드민)
    app_res = (
        supabase.table("expert_applications")
        .select("id, user_id")
        .eq("id", body.application_id)
        .limit(1)
        .execute()
    )
    if not app_res.data:
        raise HTTPException(status_code=404, detail="신청서를 찾을 수 없습니다.")
    if (app_res.data[0]["user_id"] != current_user["id"]
            and current_user.get("role_code") != "001"):
        raise HTTPException(status_code=403, detail="권한이 없습니다.")

    # 파일 경로 생성: {application_id}/{doc_type}/{uuid12}_{filename}
    file_uuid = uuid4().hex[:12]
    safe_name = f"{file_uuid}_{body.file_name}"
    file_path = f"{body.application_id}/{body.doc_type}/{safe_name}"

    # Signed Upload URL 발급 (60분 유효)
    try:
        res = supabase.storage.from_(STORAGE_BUCKET).create_signed_upload_url(file_path)
    except Exception as e:
        log.error(f"[EXPERT UPLOAD] Signed URL 발급 실패: {e}")
        raise HTTPException(status_code=500, detail="업로드 URL 발급 실패")

    return {
        "status": "success",
        "data": {
            "signed_url": res["signedUrl"],
            "token":      res.get("token", ""),
            "path":       file_path,
            "bucket":     STORAGE_BUCKET,
            "doc_type":   body.doc_type,
            "doc_label":  ALLOWED_DOC_TYPES[body.doc_type],
        },
    }


@router.post("/attach")
def register_attachment(
    body: AttachBody,
    current_user: dict = Depends(get_current_user),
):
    """
    업로드 완료 후 attachments 테이블 등록
    POST /experts/attach

    Storage PUT 업로드 완료 → 이 엔드포인트 호출하여 DB 기록.
    응답으로 24시간짜리 Signed 뷰 URL 반환 (어드민 검토용).
    """
    if body.doc_type not in ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=400, detail="유효하지 않은 doc_type입니다.")

    supabase = get_supabase()

    # 24시간 Signed 뷰 URL 발급
    try:
        signed = supabase.storage.from_(STORAGE_BUCKET).create_signed_url(
            body.file_path,
            expires_in=86400,
        )
        view_url = signed.get("signedURL", "")
    except Exception as e:
        log.warning(f"[EXPERT ATTACH] Signed 뷰 URL 발급 실패 (첨부는 계속 진행): {e}")
        view_url = ""

    # attachments 테이블 저장
    supabase.table("attachments").insert({
        "table_name":    "expert_applications",
        "record_id":     body.application_id,
        "file_category": body.doc_type,
        "file_url":      body.file_path,     # Storage 경로 저장 (URL 아님)
        "file_name":     body.file_name,
        "file_size":     body.file_size,
        "mime_type":     body.mime_type,
        "description":   ALLOWED_DOC_TYPES.get(body.doc_type, ""),
        "uploaded_by":   current_user.get("id"),
        "created_at":    _now_iso(),
    }).execute()

    return {
        "status": "success",
        "data": {
            "file_path": body.file_path,
            "doc_type":  body.doc_type,
            "doc_label": ALLOWED_DOC_TYPES[body.doc_type],
            "view_url":  view_url,
        },
    }


@router.get("/admin/{application_id}/documents")
def get_application_documents(
    application_id: str,
    current_user: dict = Depends(_require_admin),
):
    """
    어드민: 신청서 첨부 서류 목록 + Signed 뷰 URL 재발급 (1시간)
    GET /experts/admin/{application_id}/documents
    """
    supabase = get_supabase()

    res = (
        supabase.table("attachments")
        .select("*")
        .eq("table_name", "expert_applications")
        .eq("record_id", application_id)
        .order("created_at", desc=False)
        .execute()
    )

    docs = []
    for att in (res.data or []):
        view_url = ""
        try:
            signed = supabase.storage.from_(STORAGE_BUCKET).create_signed_url(
                att["file_url"],
                expires_in=3600,   # 1시간
            )
            view_url = signed.get("signedURL", "")
        except Exception as e:
            log.warning(f"[EXPERT DOCS] Signed URL 실패 path={att.get('file_url')}: {e}")

        docs.append({
            **att,
            "doc_label": ALLOWED_DOC_TYPES.get(att.get("file_category", ""), ""),
            "view_url":  view_url,
        })

    return {
        "status": "success",
        "data": {"items": docs, "total": len(docs)},
    }


# ════════════════════════════════════════════════════════════════════════
# 승인된 전문가 통합 목록 / 활성 토글 (v2.2.0)
# ════════════════════════════════════════════════════════════════════════

# source_table → 실제 DB 테이블명 매핑
TABLE_MAP: Dict[str, str] = {
    "personnel": "safety_personnel",
    "agency":    "safety_agencies",
    "repair":    "repair_companies",
}


@router.get("/admin/expert-list")
def admin_expert_list(
    expert_type:     Optional[str]  = Query(None, description="EXPERT/CONSULTING/REPAIR"),
    entity_type:     Optional[str]  = Query(None),
    verified_status: Optional[str]  = Query(None, description="APPROVED 등"),
    is_active:       Optional[bool] = Query(None),
    keyword:         Optional[str]  = Query(None, description="이름 또는 회사명"),
    page: int = Query(1,  ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(_require_admin),
):
    """
    어드민: 승인된 전문가 통합 목록
    GET /experts/admin/expert-list

    v_expert_list 뷰 사용
    (safety_personnel + safety_agencies + repair_companies UNION)
    """
    supabase = get_supabase()
    q = supabase.table("v_expert_list").select("*", count="exact")

    if expert_type:           q = q.eq("expert_type",     expert_type)
    if entity_type:           q = q.eq("entity_type",     entity_type)
    if verified_status:       q = q.eq("verified_status", verified_status)
    if is_active is not None: q = q.eq("is_active",       is_active)
    if keyword:
        q = q.or_(f"expert_name.ilike.%{keyword}%,biz_name.ilike.%{keyword}%")

    offset = (page - 1) * size
    res    = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    total  = res.count or 0

    return {
        "status": "success",
        "data": {
            "items":       res.data or [],
            "total":       total,
            "page":        page,
            "size":        size,
            "total_pages": (total + size - 1) // size if total else 0,
        },
    }


@router.patch("/admin/expert/{source_table}/{expert_id}/toggle")
def toggle_expert_active(
    source_table: str,
    expert_id:    str,
    is_active:    bool = Query(..., description="true=활성화, false=비활성화"),
    current_user: dict = Depends(_require_admin),
):
    """
    어드민: 전문가 활성/비활성 토글
    PATCH /experts/admin/expert/{source_table}/{expert_id}/toggle?is_active=true

    source_table: personnel / agency / repair
    """
    table = TABLE_MAP.get(source_table)
    if not table:
        raise HTTPException(
            status_code=400,
            detail=f"source_table은 {list(TABLE_MAP.keys())} 중 하나여야 합니다.",
        )

    supabase = get_supabase()
    now = _now_iso()

    res = supabase.table(table).update({
        "is_active":  is_active,
        "updated_at": now,
    }).eq("id", expert_id).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="전문가를 찾을 수 없습니다.")

    log.info(
        f"[EXPERT TOGGLE] table={table} id={expert_id} "
        f"is_active={is_active} by={current_user['id']}"
    )
    return {
        "status":  "success",
        "message": f"{'활성화' if is_active else '비활성화'} 처리되었습니다.",
        "data": {
            "source_table": source_table,
            "expert_id":    expert_id,
            "is_active":    is_active,
        },
    }
