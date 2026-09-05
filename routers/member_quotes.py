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
from services.company_scope import require_company_id, scoped_list_company, _ensure_own_company
from services import member_quote_svc as svc

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
    company_id = require_company_id(current, supabase)   # 비-ALL 토큰회사 강제 / 무회사 403
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
    company_id = require_company_id(current, supabase)
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
    """내 회사 견적 목록 — member_auto/member_custom 만. survey_web 미포함."""
    supabase = get_supabase()
    scoped_cid, deny_all = scoped_list_company(current, supabase, None)
    if deny_all:
        return {"status": "success", "data": {"items": [], "total": 0, "page": page,
                                              "page_size": page_size, "total_pages": 0}}
    return {"status": "success", "data": svc.list_member_quotes(supabase, scoped_cid, page, page_size)}


@router.get("/{quote_id}")
def get_my_quote(quote_id: str, current: dict = Depends(get_current_user)):
    """견적 상세 — 소유 회사만. 타사/비회원소스는 404(존재 은닉)."""
    supabase = get_supabase()
    row = svc.get_member_quote(supabase, quote_id)
    if not row:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    _ensure_own_company(row.get("company_id"), current, supabase, _NOT_FOUND)
    return {"status": "success", "data": row}
