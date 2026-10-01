# routers/member_quotes.py — v1.1.0
"""회원 견적 Core API — 고객 마이페이지 견적(자동/개별) 서버 계약.

인증: get_current_user(Bearer). 소유권: services.company_scope.
가격 SoT: price_master(서버 계산). 클라이언트 금액/company_id/created_by/source/status 불신.
설문견적(/quotes/survey/*)과 분리 — 이 라우터는 source in (member_auto, member_custom) 만 다룬다.

v1.1.0 (WO-BE-FE-QUOTE-CONSTRUCTION-REG-01):
  POST /v2/construction-sites — 미계약 건설 견적용 최소 사업장 등록.
  construction_sites INSERT only. factory/diagnosis/schedule side effect 0.
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from schemas.saas_quote_v2 import SaasQuoteIssueRequestV2
from services.company_scope import require_company_id
from services import member_quote_svc as svc
from services import member_quote_pdf_svc as pdf_svc
from services import saas_quote_v2 as saas_quote_v2_svc
from services.gotenberg_svc import PdfRenderError
from services.saas_pricing_preview_v2 import SaasPricingPreviewError
from services.saas_quote_v2 import SaasQuoteV2Error
from services.saas_quote_site_scope_v2 import QuoteSiteScopeError

logger = logging.getLogger("member_quotes")
router = APIRouter(prefix="/me/quotes", tags=["member-quotes"])
_NOT_FOUND = "견적을 찾을 수 없습니다"
_EOK_TO_WON = 100_000_000  # construction_sites.contract_amount 억원 ↔ pricing criteria 원


class AutoQuoteBody(BaseModel):
    service_type: str
    sector: str
    tier_code: str
    term_months: Optional[int] = None
    contact_name: Optional[str] = None    # 선택, 표시 스냅샷 — 가격/소유권 무관


class CustomQuoteBody(BaseModel):
    service_type: str
    sector: str
    request_title: str
    request_detail: str = ""
    contact_name: Optional[str] = None    # 선택


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
        calc = svc.calc_quote(
            get_supabase(), body.service_type, body.sector, body.tier_code, body.term_months)
    except svc.MemberQuoteError as e:
        _raise(e)
    calc["contact_name"] = svc.normalize_contact_name(body.contact_name)  # display echo — not calc output
    return {"status": "success", "data": calc}


@router.post("/auto")
def auto_issue(body: AutoQuoteBody, current: dict = Depends(get_current_user)):
    """자동견적 발행 — 서버가 다시 계산해 quotes INSERT."""
    supabase = get_supabase()
    company_id = _require_member_company(current, supabase)   # ALL 포함 자사강제 / 무회사 403
    try:
        row = svc.create_auto_quote(supabase, company_id, current.get("id"),
                                    body.service_type, body.sector, body.tier_code, body.term_months,
                                    contact_name=body.contact_name)
    except svc.MemberQuoteError as e:
        _raise(e)
    return {"status": "success", "data": row}


def _quote_manual_slack_detail(row: Dict[str, Any]) -> str:
    """수동 견적요청 알림 detail (실측 필드만, 개인정보 최소)."""
    sd = (row.get("survey_data") or {}).get("member_custom") or {}
    return (
        f"견적번호: {row.get('quote_no') or '-'}\n"
        f"회사: {row.get('company_name') or '-'}\n"
        f"요청자: {row.get('contact_name') or '-'}\n"
        f"서비스: {row.get('service_type') or '-'} / 섹터: {sd.get('sector') or '-'}\n"
        f"제목: {sd.get('request_title') or '-'}\n"
        f"내용: {(sd.get('request_detail') or '')[:400]}"
    )


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
                                      body.request_title.strip(), (body.request_detail or "").strip(),
                                      contact_name=body.contact_name)
    except svc.MemberQuoteError as e:
        _raise(e)

    # WO-SLACK-EVENT-HUB-001 PR-② : create_custom_quote 성공 반환 직후 1회.
    # sync handler 이므로 send_slack_sync 사용(fire-and-forget). 채널은 dispatcher 라우팅
    # (EVENT_TYPE_CHANNEL: QUOTE_MANUAL_REQUESTED → APPROVAL). 실패해도 견적요청 성공 유지.
    try:
        from services.slack_dispatcher import send_slack_sync
        title = f"수동 견적요청 · {row.get('company_name') or '-'} · {row.get('contact_name') or '-'}"
        send_slack_sync("QUOTE_MANUAL_REQUESTED", "INFO", title, _quote_manual_slack_detail(row))
    except Exception as e:  # noqa: BLE001
        logger.warning("[quote_manual slack] dispatch failed: %s", e)

    return {"status": "success", "data": row}


_V2_CUSTOM_CODES = frozenset({"CUSTOM_QUOTE_REQUIRED", "COMPLIANCE_BASE_QUOTE_REQUIRED"})
_V2_GATE_CODES = frozenset({"QUOTE_PRICING_NOT_READY", "QUOTE_SNAPSHOT_INVALID", "COMPANY_SNAPSHOT_REQUIRED"})
_PREVIEW_CLIENT_CODES = frozenset({"INVALID_SELECTION", "STANDARD_SITE_REQUIRED", "DUPLICATE_SITE"})
_PREVIEW_SERVER_CODES = frozenset({"BASE_PRICE_NOT_FOUND", "INVALID_BASE_PRICE_ROW"})


@router.post("/v2/issue")
def issue_v2(body: SaasQuoteIssueRequestV2, current: dict = Depends(get_current_user)):
    """SaaS V2 자동견적 발행.

    - 인증 필수 (Bearer)
    - company_id = auth context
    - 서버 재계산 필수 (Preview V2 경유)
    - READY 상태만 quotes INSERT
    """
    supabase = get_supabase()
    company_id = _require_member_company(current, supabase)
    try:
        row = saas_quote_v2_svc.issue_saas_quote_v2(
            supabase, body, current.get("id"), company_id,
        )
        return {"status": "success", "data": row}
    except SaasQuoteV2Error as exc:
        if exc.code in _V2_CUSTOM_CODES:
            raise HTTPException(
                status_code=409,
                detail={"code": exc.code, "message": exc.message, "route_to_custom": True},
            )
        if exc.code in _V2_GATE_CODES:
            raise HTTPException(
                status_code=409,
                detail={"code": exc.code, "message": exc.message},
            )
        raise HTTPException(status_code=500, detail={"code": exc.code})
    except SaasPricingPreviewError as exc:
        if exc.code in _PREVIEW_CLIENT_CODES:
            raise HTTPException(
                status_code=422,
                detail={"code": exc.code, "message": exc.message},
            )
        if exc.code in _PREVIEW_SERVER_CODES:
            raise HTTPException(
                status_code=503,
                detail={"code": exc.code, "message": exc.message},
            )
        raise HTTPException(status_code=500, detail={"code": exc.code})
    except QuoteSiteScopeError as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail={"code": exc.code, "message": exc.message},
        )
    except Exception:
        raise HTTPException(status_code=503, detail={"code": "INTERNAL_ERROR"})


class CommercialConstructionSiteBody(BaseModel):
    site_name: str
    criteria_value: float  # 원 단위. 서버가 억원으로 변환해 DB 저장.


@router.post("/v2/construction-sites")
def register_commercial_construction_site(
    body: CommercialConstructionSiteBody,
    current: dict = Depends(get_current_user),
):
    """견적 발행용 건설현장 최소 등록.

    construction_sites INSERT only.
    factory 생성 / auto_diagnose / schedule 생성 = 0.
    """
    supabase = get_supabase()
    company_id = _require_member_company(current, supabase)

    if not body.site_name.strip():
        raise HTTPException(status_code=422, detail={"code": "SITE_NAME_REQUIRED",
                                                      "message": "현장명이 필요합니다."})
    if body.criteria_value < 0:
        raise HTTPException(status_code=422, detail={"code": "INVALID_CRITERIA",
                                                      "message": "공사금액은 0 이상이어야 합니다."})

    contract_amount = body.criteria_value / _EOK_TO_WON  # 원 → 억원
    from services.time import now_kst
    now = now_kst().isoformat()
    row = {
        "company_id": company_id,
        "site_name": body.site_name.strip(),
        "contract_amount": contract_amount,
        "status_code": "PLANNED",
        "created_at": now,
        "updated_at": now,
    }
    res = supabase.table("construction_sites").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail={"code": "SITE_INSERT_FAILED",
                                                      "message": "건설현장 등록에 실패했습니다."})
    inserted = res.data[0]
    return {
        "status": "success",
        "data": {
            "id": inserted["id"],
            "site_name": inserted["site_name"],
            "sector": "CONSTRUCTION",
            "criteria_value": body.criteria_value,
        },
    }


class SaasV2PaymentPrepareBody(BaseModel):
    """POST /me/quotes/v2/{quote_id}/payment/prepare — client input 최소화."""
    proof_type: Optional[str] = None
    buyername: Optional[str] = None
    buyertel: Optional[str] = None
    buyeremail: Optional[str] = None

    @field_validator("proof_type")
    @classmethod
    def _check_proof_type(cls, v: Optional[str]) -> Optional[str]:
        from schemas.payment import _validate_client_proof_type
        return _validate_client_proof_type(v)


@router.post("/v2/{quote_id}/payment/prepare")
def prepare_v2_payment(
    quote_id: str,
    body: SaasV2PaymentPrepareBody,
    current: dict = Depends(get_current_user),
):
    """Frozen Quote V2 → INICIS 결제 준비.

    서버 파생: user_id, company_id, amounts, product_type, plan_code, period_months.
    금지 client field: amount, company_id, user_id, product_type, plan_code, period_months.
    소유권: /me 자사 강제 + quote 소유권 (adapter 내부 검증).
    타사 quote_id → 404 (소유권 은닉).
    """
    supabase = get_supabase()
    company_id = _require_member_company(current, supabase)
    from services.saas_payment_v2_adapter import (
        SaasPaymentV2AdapterError,
        prepare_saas_v2_payment_from_quote,
    )
    try:
        result = prepare_saas_v2_payment_from_quote(
            supabase,
            quote_id=quote_id,
            user_id=current["id"],
            company_id=company_id,
            proof_type=body.proof_type,
            buyername=body.buyername,
            buyertel=body.buyertel,
            buyeremail=body.buyeremail,
        )
    except SaasPaymentV2AdapterError as exc:
        if exc.code in {"QUOTE_NOT_FOUND", "QUOTE_NOT_OWNED"}:
            raise HTTPException(status_code=404, detail={"code": exc.code, "message": exc.message})
        if exc.code in {"QUOTE_PAYMENT_PENDING", "QUOTE_ALREADY_PAID", "QUOTE_PAYMENT_STATE_CONFLICT"}:
            raise HTTPException(status_code=409, detail={"code": exc.code, "message": exc.message})
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message})
    return result


@router.post("/v2/{quote_id}/renewal/payment/prepare")
def prepare_v2_renewal_payment(
    quote_id: str,
    body: SaasV2PaymentPrepareBody,
    current: dict = Depends(get_current_user),
):
    """Renewal Frozen Quote → INICIS Renewal 결제 준비.

    client는 contract_id를 전달하지 않는다.
    server가 quote의 survey_data.commercial_v3_renewal에서 contract_id를 파생한다.
    """
    supabase = get_supabase()
    company_id = _require_member_company(current, supabase)

    # Load + ownership
    from services import member_quote_svc as _mqs
    quote = _mqs.get_member_quote(supabase, quote_id)
    if not quote or str(quote.get("company_id")) != str(company_id):
        raise HTTPException(status_code=404, detail={"code": "QUOTE_NOT_FOUND", "message": "견적을 찾을 수 없습니다."})

    # Validate renewal binding
    survey = quote.get("survey_data") or {}
    renewal_ctx = survey.get("commercial_v3_renewal") if isinstance(survey, dict) else None
    if not renewal_ctx or not isinstance(renewal_ctx, dict):
        raise HTTPException(status_code=422, detail={"code": "NOT_RENEWAL_QUOTE", "message": "연장 견적이 아닙니다."})

    contract_id = str(renewal_ctx.get("contract_id") or "")
    current_version_no = renewal_ctx.get("current_version_no")
    if not contract_id or current_version_no is None:
        raise HTTPException(status_code=422, detail={"code": "RENEWAL_BINDING_INVALID", "message": "연장 바인딩이 유효하지 않습니다."})

    # Verify CV still matches (version_no binding check)
    from services.saas_commercial_version_time_v2 import (
        TemporalVersionError,
        select_effective_commercial_version_v2,
        contract_end_date_to_effective_at_v2,
    )
    from services.time import now_kst
    _now = now_kst()
    cv_res = (
        supabase.table("saas_contract_commercial_versions")
        .select("id, version_no, contract_id, superseded_at, effective_from")
        .eq("contract_id", contract_id)
        .execute()
    )
    all_cvs = cv_res.data or []
    try:
        current_cv = select_effective_commercial_version_v2(all_cvs, _now)
    except TemporalVersionError:
        raise HTTPException(status_code=409, detail={"code": "CURRENT_CV_NOT_FOUND", "message": "현재 계약 버전을 확인할 수 없습니다."})

    if int(current_cv.get("version_no") or -1) != int(current_version_no):
        raise HTTPException(status_code=409, detail={"code": "RENEWAL_VERSION_MISMATCH", "message": "계약 버전이 변경되었습니다. 연장 견적을 다시 발행해 주세요."})

    # Temporal window guard
    ct_res2 = (
        supabase.table("contracts")
        .select("id, end_date")
        .eq("id", contract_id)
        .limit(1)
        .execute()
    )
    ct_row = (ct_res2.data or [None])[0]
    end_date = (ct_row or {}).get("end_date")
    if end_date:
        contract_end_boundary = contract_end_date_to_effective_at_v2(end_date)
        if _now >= contract_end_boundary:
            raise HTTPException(
                status_code=422,
                detail={"code": "RENEWAL_WINDOW_CLOSED", "message": "계약 연장 기간이 종료되었습니다."},
            )

    from services.saas_renewal_v2_adapter import (
        SaasRenewalV2AdapterError,
        prepare_saas_v2_renewal_payment_from_quote,
    )
    try:
        result = prepare_saas_v2_renewal_payment_from_quote(
            supabase,
            contract_id=contract_id,
            quote_id=quote_id,
            company_id=company_id,
            user_id=current["id"],
            as_of=_now,
            proof_type=body.proof_type,
            buyername=body.buyername,
            buyertel=body.buyertel,
            buyeremail=body.buyeremail,
        )
    except SaasRenewalV2AdapterError as exc:
        if exc.code in {"CONTRACT_NOT_FOUND", "CONTRACT_NOT_OWNED", "QUOTE_NOT_FOUND", "QUOTE_NOT_OWNED"}:
            raise HTTPException(status_code=404, detail={"code": exc.code, "message": exc.message})
        if exc.code in {"RENEWAL_ALREADY_SCHEDULED", "CURRENT_CV_SUPERSEDED", "RENEWAL_BOUNDARY_CONFLICT"}:
            raise HTTPException(status_code=409, detail={"code": exc.code, "message": exc.message})
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message})
    return result


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
