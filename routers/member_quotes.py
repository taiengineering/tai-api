# routers/member_quotes.py — v1.0.0 (WO-MYPAGE-QUOTE-PROCESS-001 STEP 2A)
"""회원 견적 Core API — 고객 마이페이지 견적(자동/개별) 서버 계약.

인증: get_current_user(Bearer). 소유권: services.company_scope.
가격 SoT: price_master(서버 계산). 클라이언트 금액/company_id/created_by/source/status 불신.
설문견적(/quotes/survey/*)과 분리 — 이 라우터는 source in (member_auto, member_custom) 만 다룬다.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import require_company_id
from services import member_quote_svc as svc
from services import member_quote_pdf_svc as pdf_svc
from services.gotenberg_svc import PdfRenderError

router = APIRouter(prefix="/me/quotes", tags=["member-quotes"])
_NOT_FOUND = "견적을 찾을 수 없습니다"


class AutoQuoteBody(BaseModel):
    service_type: str
    sector: str
    tier_code: str
    term_months: Optional[int] = None


class CustomQuoteBody(BaseModel):
    service_type: str
    sector: str
    request_title: str
    request_detail: str = ""


def _raise(e: svc.MemberQuoteError):
    if e.code == "CUSTOM_QUOTE_REQUIRED":
        raise HTTPException(status_code=409,
                            detail={"code": e.code, "route_to_custom": True, "message": e.message})
    raise HTTPException(status_code=e.http_status, detail={"code": e.code, "message": e.message})


def _require_member_company(current: dict, supabase) -> str:
    """/me/* 전용 — 관리자(ALL) 포함 '자사만'. 무회사면 403.
    require_company_id 는 ALL 에서 None 을 줄 수 있어(전사 노출 원인) None 이면 역할 무관 403."""
    cid = require_company_id(current, supabase)
    if not cid:
        raise HTTPException(status_code=403, detail={"code": "COMPANY_REQUIRED",
                                                     "message": "회사 등록이 필요합니다."})
    return cid


@router.post("/auto/preview")
def auto_preview(body: AutoQuoteBody, current: dict = Depends(get_current_user)):
    """가격 미리보기 — DB write 없음."""
    try:
        return {"status": "success", "data": svc.calc_quote(
            get_supabase(), body.service_type, body.sector, body.tier_code, body.term_months)}
    except svc.MemberQuoteError as e:
        _raise(e)


@router.post("/auto")
def auto_issue(body: AutoQuoteBody, current: dict = Depends(get_current_user)):
    """자동견적 발행 — 서버가 다시 계산해 quotes INSERT."""
    supabase = get_supabase()
    company_id = _require_member_company(current, supabase)   # ALL 포함 자사강제 / 무회사 403
    try:
        row = svc.create_auto_quote(supabase, company_id, current.get("id"),
                                    body.service_type, body.sector, body.tier_code, body.term_months)
    except svc.MemberQuoteError as e:
        _raise(e)
    return {"status": "success", "data": row}


@router.post("/custom")
def custom_request(body: CustomQuoteBody, current: dict = Depends(get_current_user)):
    """개별견적 요청 — 클라이언트 금액 없음. 서버가 0원으로 접수."""
    supabase = get_supabase()
    company_id = _require_member_company(current, supabase)
    if not (body.request_title or "").strip():
        raise HTTPException(status_code=422, detail={"code": "TITLE_REQUIRED", "message": "요청 제목이 필요합니다."})
    try:
        row = svc.create_custom_quote(supabase, company_id, current.get("id"),
                                      body.service_type, body.sector,
                                      body.request_title.strip(), (body.request_detail or "").strip())
    except svc.MemberQuoteError as e:
        _raise(e)
    return {"status": "success", "data": row}


@router.get("")
def list_my_quotes(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                   current: dict = Depends(get_current_user)):
    """내 회사 견적 목록 — /me 계약: ALL 이라도 자사만. member_auto/member_custom 만."""
    supabase = get_supabase()
    company_id = _require_member_company(current, supabase)   # ALL 이라도 전사 조회 금지
    return {"status": "success", "data": svc.list_member_quotes(supabase, company_id, page, page_size)}


@router.get("/{quote_id}")
def get_my_quote(quote_id: str, current: dict = Depends(get_current_user)):
    """견적 상세 — /me 계약: 소유 회사만(ALL 도 타사 404)."""
    supabase = get_supabase()
    company_id = _require_member_company(current, supabase)
    row = svc.get_member_quote(supabase, quote_id)
    if not row or str(row.get("company_id")) != str(company_id):   # ALL 도 타사 404
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return {"status": "success", "data": row}


@router.post("/{quote_id}/pdf")
async def issue_quote_pdf(quote_id: str, current: dict = Depends(get_current_user)):
    """내부결재 첨부용 견적서 PDF — member_auto/ISSUED 만. /me strict 소유권. 멱등."""
    supabase = get_supabase()
    company_id = _require_member_company(current, supabase)
    row = svc.get_member_quote(supabase, quote_id)
    if not row or str(row.get("company_id")) != str(company_id):   # 타사·비회원소스 404
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    try:
        result = await pdf_svc.issue_or_get_quote_pdf(row, current.get("id"))
    except (pdf_svc.QuotePdfError, PdfRenderError) as e:
        raise HTTPException(status_code=e.http_status, detail={"code": e.code, "message": e.message})
    doc = result["document"]
    return {"status": "success", "data": {
        "quote_id": quote_id,
        "document_id": doc.get("id"),
        "file_name": doc.get("file_name"),
        "generated": result["generated"],
        "url": result["url"],
        "expires_in": 3600,
    }}
