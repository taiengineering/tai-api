# routers/admin_quotes.py — v1.0.0 (WO-MYPAGE-QUOTE-PROCESS-001 STEP 2D-A)
"""관리자 견적 라우터 — /admin/quotes.

인증: get_current_user(Bearer). 권한: services.company_scope._require_admin (ALL만 통과).
정본: services.admin_quote_svc. PDF 재사용: services.member_quote_pdf_svc.

body 로 신뢰 금지 : company_name / created_by / source / status_code /
  quote_no / supply_amount / vat_amount / total_amount.
manual : contact_name 수신 허용(정규화 후 저장).
custom→issue : 기존 REQUESTED row 의 contact_name/company/survey_data/created_at 보존.

STEP 2D-B(admin-vue3 프론트) 는 별건 WO — 이 파일은 백엔드만.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _require_admin
from services import admin_quote_svc as svc
from services import member_quote_svc as mq_svc
from services import member_quote_pdf_svc as pdf_svc
from services.gotenberg_svc import PdfRenderError


router = APIRouter(prefix="/admin/quotes", tags=["admin-quotes"])
_NOT_FOUND = "견적을 찾을 수 없습니다"


class ManualQuoteBody(BaseModel):
    company_id: str
    service_type: Optional[str] = None
    sector: Optional[str] = None
    tier_code: Optional[str] = None
    display_name: Optional[str] = None
    billing_unit: str
    term_months: Optional[int] = None
    quantity: Optional[int] = None
    unit_amount: int
    vat_rate: Optional[float] = None                    # None → 서비스 기본 0.1
    contact_name: Optional[str] = None
    memo: Optional[str] = None


class CustomIssueBody(BaseModel):
    # PATCH-1 : service_type / sector 는 클라이언트가 override 못 한다.
    #   service_type = 기존 row.service_type
    #   sector       = survey_data.member_custom.sector
    # 관리자는 상품/티어/과금/기간/수량/단가/부가세율/메모만 조작한다.
    tier_code: Optional[str] = None
    display_name: Optional[str] = None
    billing_unit: str
    term_months: Optional[int] = None
    quantity: Optional[int] = None
    unit_amount: int
    vat_rate: Optional[float] = None
    memo: Optional[str] = None


def _raise(e: svc.AdminQuoteError):
    raise HTTPException(status_code=e.http_status, detail={"code": e.code, "message": e.message})


def _resolve_custom_context(row: dict):
    """custom preview/issue : service_type / sector 는 오직 기존 row / survey_data 만.

    PATCH-1 : body override 제거. 관리자는 회원의 신청 컨텍스트를 그대로 사용해야 한다
    (관리자가 임의로 서비스/섹터를 바꾸는 경로 봉쇄).
    """
    service_type = row.get("service_type")
    sd = (row.get("survey_data") or {}).get("member_custom") or {}
    sector = sd.get("sector")
    return service_type, sector


# ═══════════════════════════════════════════════════════════════════
# LIST / DETAIL
# ═══════════════════════════════════════════════════════════════════
@router.get("")
def list_quotes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source: Optional[str] = Query(None),
    status_code: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current: dict = Depends(get_current_user),
):
    """관리자 견적 목록 — ADMIN_SOURCES (member_auto/member_custom/admin_manual) 만.
    survey_web 등 legacy 는 미노출."""
    supabase = get_supabase()
    _require_admin(current, supabase)
    return {
        "status": "success",
        "data": svc.list_admin_quotes(supabase, page, page_size, source, status_code, search),
    }


@router.get("/{quote_id}")
def get_quote(quote_id: str, current: dict = Depends(get_current_user)):
    """관리자 견적 상세 — ADMIN_SOURCES 만. 그 외 source 는 404 (존재 은닉)."""
    supabase = get_supabase()
    _require_admin(current, supabase)
    row = svc.get_admin_quote(supabase, quote_id)
    if not row:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return {"status": "success", "data": row}


# ═══════════════════════════════════════════════════════════════════
# MANUAL PREVIEW / ISSUE (admin_manual)
# ═══════════════════════════════════════════════════════════════════
@router.post("/manual/preview")
def manual_preview(body: ManualQuoteBody, current: dict = Depends(get_current_user)):
    """수동 견적 미리보기 — DB write 0 · PDF call 0. quote_no 발급 없음.
    PATCH-1 : 회사 존재를 _require_company_name 으로 강제(재조회, 미존재 → 404)."""
    supabase = get_supabase()
    _require_admin(current, supabase)
    if not body.company_id:
        raise HTTPException(status_code=422, detail={"code": "COMPANY_REQUIRED",
                                                     "message": "회사 지정이 필요합니다."})
    try:
        company_name = svc._require_company_name(supabase, body.company_id)
        item = svc.calc_manual_quote(
            body.service_type, body.sector, body.tier_code, body.display_name,
            body.billing_unit, body.term_months, body.quantity, body.unit_amount,
            body.vat_rate if body.vat_rate is not None else 0.1,
        )
    except svc.AdminQuoteError as e:
        _raise(e)
    return {"status": "success", "data": {
        "company_id": body.company_id,
        "company_name": company_name,
        "contact_name": mq_svc.normalize_contact_name(body.contact_name),
        "item": item,
        "service_type": item["service_type"],
        "supply_amount": item["supply_amount"],
        "vat_amount": item["vat_amount"],
        "total_amount": item["total_amount"],
    }}


@router.post("/manual")
def manual_issue(body: ManualQuoteBody, current: dict = Depends(get_current_user)):
    """관리자 수동 견적 발행 — admin_manual/ISSUED. quote_no unique retry 재사용."""
    supabase = get_supabase()
    _require_admin(current, supabase)
    try:
        row = svc.create_admin_manual(
            supabase, current.get("id"), body.company_id, body.contact_name,
            body.service_type, body.sector, body.tier_code, body.display_name,
            body.billing_unit, body.term_months, body.quantity, body.unit_amount,
            body.vat_rate if body.vat_rate is not None else 0.1,
            body.memo,
        )
    except svc.AdminQuoteError as e:
        _raise(e)
    return {"status": "success", "data": row}


# ═══════════════════════════════════════════════════════════════════
# CUSTOM PREVIEW / ISSUE (member_custom REQUESTED → ISSUED)
# ═══════════════════════════════════════════════════════════════════
@router.post("/{quote_id}/custom/preview")
def custom_preview(quote_id: str, body: CustomIssueBody,
                   current: dict = Depends(get_current_user)):
    """개별 견적 발행 미리보기 — REQUESTED 상태의 member_custom 만.

    write=0. 대상 row 는 immutable(quote_no·company·contact·survey_data·created_at 전부 그대로).
    service_type/sector fallback : body → 기존 row → survey_data.
    """
    supabase = get_supabase()
    _require_admin(current, supabase)
    row = svc.get_admin_quote(supabase, quote_id)
    if not row:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    if row.get("source") != "member_custom" or row.get("status_code") != "REQUESTED":
        raise HTTPException(status_code=409, detail={
            "code": "NOT_CUSTOM_REQUESTED",
            "message": "요청 상태의 개별 견적만 미리보기 대상입니다.",
        })
    service_type, sector = _resolve_custom_context(row)
    try:
        item = svc.calc_manual_quote(
            service_type, sector, body.tier_code, body.display_name,
            body.billing_unit, body.term_months, body.quantity, body.unit_amount,
            body.vat_rate if body.vat_rate is not None else 0.1,
        )
    except svc.AdminQuoteError as e:
        _raise(e)
    return {"status": "success", "data": {
        "quote_id": quote_id,
        "company_id": row.get("company_id"),
        "company_name": row.get("company_name"),
        "contact_name": row.get("contact_name"),
        "item": item,
        "service_type": item["service_type"],
        "supply_amount": item["supply_amount"],
        "vat_amount": item["vat_amount"],
        "total_amount": item["total_amount"],
    }}


@router.post("/{quote_id}/custom/issue")
def custom_issue(quote_id: str, body: CustomIssueBody,
                 current: dict = Depends(get_current_user)):
    """개별 견적 발행 확정 — same-row conditional UPDATE (member_custom + REQUESTED → ISSUED).

    이미 ISSUED / 다른 source / 삭제된 row 시 409 QUOTE_ALREADY_ISSUED.
    quote_no · company · contact_name · survey_data · created_at 보존.
    """
    supabase = get_supabase()
    _require_admin(current, supabase)
    row = svc.get_admin_quote(supabase, quote_id)
    if not row:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    if row.get("source") != "member_custom":
        raise HTTPException(status_code=409, detail={
            "code": "NOT_CUSTOM_REQUESTED",
            "message": "개별 견적이 아닙니다.",
        })
    # PATCH-1 : 기존 row 의 company_name snapshot 이 누락된 경우 발행 불가.
    #   (재조회로 우회하지 않는다 — 스냅샷 무결성이 위반된 상태에서 발행 금지)
    cn = row.get("company_name")
    if not cn or not str(cn).strip():
        raise HTTPException(status_code=409, detail={
            "code": "QUOTE_SNAPSHOT_INCOMPLETE",
            "message": "견적의 회사명 정보가 누락되어 발행할 수 없습니다.",
        })
    service_type, sector = _resolve_custom_context(row)
    try:
        result = svc.issue_custom(
            supabase, quote_id, service_type, sector, body.tier_code, body.display_name,
            body.billing_unit, body.term_months, body.quantity, body.unit_amount,
            body.vat_rate if body.vat_rate is not None else 0.1,
            body.memo,
        )
    except svc.AdminQuoteError as e:
        _raise(e)
    return {"status": "success", "data": result}


# ═══════════════════════════════════════════════════════════════════
# ADMIN PDF (재사용 pdf_svc, admin scope)
# ═══════════════════════════════════════════════════════════════════
@router.post("/{quote_id}/pdf")
async def issue_admin_quote_pdf(quote_id: str, current: dict = Depends(get_current_user)):
    """관리자 견적 PDF 발급 — ADMIN_SOURCES + ISSUED 만.
    pdf_svc.issue_or_get_quote_pdf 를 재사용 (eligibility 확장분이 검증).
    uploaded_by = admin id, document.company_id = quote.company_id 유지.
    """
    supabase = get_supabase()
    _require_admin(current, supabase)
    row = svc.get_admin_quote(supabase, quote_id)
    if not row:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    try:
        result = await pdf_svc.issue_or_get_quote_pdf(row, current.get("id"))
    except (pdf_svc.QuotePdfError, PdfRenderError) as e:
        raise HTTPException(status_code=e.http_status,
                            detail={"code": e.code, "message": e.message})
    doc = result["document"]
    return {"status": "success", "data": {
        "quote_id": quote_id,
        "document_id": doc.get("id"),
        "file_name": doc.get("file_name"),
        "generated": result["generated"],
        "url": result["url"],
        "expires_in": 3600,
    }}
