"""회원 견적서 PDF 발급 (내부결재 첨부용) — STEP 2B.

정본 = 발행된 quotes row(frozen snapshot). 가격 마스터·회사 마스터 재조회 0. 가격계산 0.
저장/서명URL = document_svc 재사용. 소유권 strict 검증은 라우터가 선행.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from services import document_svc
from services.gotenberg_svc import render_html_pdf
from services.time import to_kst, parse_external_datetime

GENERATED_BY = "member_quote_pdf_v1"
TEMPLATE_VERSION = "member_quote_v1"
_TEMPLATE_NAME = "member_quote_v1.html"
_TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "templates", "quotes",
)
_jinja = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


class QuotePdfError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _supplier_config() -> Dict[str, str]:
    """기존 TAI_* 재사용(대표자=TAI_CEO_NAME, invoice_svc 실측 정합) + 연락처 3개 신규."""
    cfg = {
        "name": (os.getenv("TAI_CORP_NAME") or "").strip(),
        "representative": (os.getenv("TAI_CEO_NAME") or "").strip(),
        "business_no": (os.getenv("TAI_CORP_NUM") or "").strip(),
        "address": (os.getenv("TAI_CORP_ADDR") or "").strip(),
        "tel": (os.getenv("QUOTE_SUPPLIER_TEL") or "").strip(),
        "fax": (os.getenv("QUOTE_SUPPLIER_FAX") or "").strip(),         # 선택
        "email": (os.getenv("QUOTE_SUPPLIER_EMAIL") or "").strip(),
    }
    missing = [k for k in ("name", "representative", "business_no", "address", "tel", "email") if not cfg[k]]
    if missing:
        raise QuotePdfError(
            "QUOTE_SUPPLIER_CONFIG_MISSING",
            "공급자 설정 누락: {}".format(",".join(missing)),
            503,
        )
    return cfg


def _validate_snapshot(quote: Dict[str, Any]) -> Dict[str, Any]:
    """상위 snapshot + member_auto/ISSUED + items 무결성. 정본=frozen(가격/회사 재조회 0)."""
    # PATCH-2: 상위 필드 필수 (빈문자/공백도 누락). 회사 마스터·가격 마스터 재조회로 보충 금지 → fail-closed.
    for k in ("id", "company_id", "quote_no", "company_name", "created_at"):
        v = quote.get(k)
        if v is None or (isinstance(v, str) and not v.strip()):
            raise QuotePdfError("QUOTE_SNAPSHOT_INCOMPLETE", "견적 필수 정보 누락: {}".format(k), 409)
    if quote.get("source") != "member_auto" or quote.get("status_code") != "ISSUED":
        raise QuotePdfError("PDF_NOT_AVAILABLE",
                            "자동 발급(ISSUED) 견적만 PDF 발급이 가능합니다.", 409)
    items = quote.get("items") or []
    if not isinstance(items, list) or not items:
        raise QuotePdfError("QUOTE_SNAPSHOT_INCOMPLETE", "견적 품목 snapshot이 없습니다.", 409)
    item = items[0]
    req = ("display_name", "billing_unit", "unit_amount", "quantity",
           "supply_amount", "vat_amount", "total_amount")
    if any(item.get(k) is None for k in req):
        raise QuotePdfError("QUOTE_SNAPSHOT_INCOMPLETE", "견적 품목 snapshot 필드가 누락됐습니다.", 409)
    if (int(quote.get("supply_amount") or 0) != int(item["supply_amount"])
            or int(quote.get("vat_amount") or 0) != int(item["vat_amount"])
            or int(quote.get("total_amount") or 0) != int(item["total_amount"])):
        raise QuotePdfError("QUOTE_SNAPSHOT_INVALID", "견적 금액 snapshot이 일치하지 않습니다.", 409)
    return item


def _quote_date_kst(created_at) -> str:
    try:
        return to_kst(parse_external_datetime(str(created_at).replace("Z", "+00:00"))).strftime("%Y-%m-%d")
    except Exception as e:
        raise QuotePdfError("QUOTE_SNAPSHOT_INVALID", "견적일자를 확인할 수 없습니다.", 409) from e


def _period_label(item: Dict[str, Any]) -> str:
    if (item.get("billing_unit") or "").upper() == "MONTHLY":
        return "{}개월".format(item.get("term_months"))
    return "1회"


def _render_html(quote, item, supplier, quote_date) -> str:
    def won(n):
        return "{:,}".format(int(n or 0))

    return _jinja.get_template(_TEMPLATE_NAME).render(
        quote_no=quote.get("quote_no"),
        quote_date=quote_date,
        receiver=quote.get("company_name") or "",
        supplier=supplier,
        service_type=item.get("service_type") or quote.get("service_type") or "",
        product_name=item.get("display_name"),
        period=_period_label(item),
        quantity=item.get("quantity"),
        unit_amount=won(item.get("unit_amount")),
        supply=won(quote.get("supply_amount")),
        vat=won(quote.get("vat_amount")),
        total=won(quote.get("total_amount")),
    )


async def _find_existing_pdf(quote_id, company_id) -> Optional[Dict[str, Any]]:
    """document_svc.get_attachments 는 is_active + deleted_at IS NULL 필터를 이미 적용한다."""
    for d in await document_svc.get_attachments("quotes", quote_id):
        if (d.get("generated_by") == GENERATED_BY
                and d.get("source") == "AUTO_GENERATED"
                and str(d.get("company_id")) == str(company_id)):
            return d
    return None


async def _safe_signed_url(doc_id: str) -> str:
    """PATCH-3: None/빈문자/예외 모두 controlled 503. raw 예외 미노출."""
    try:
        url = await document_svc.get_signed_url(doc_id, 3600)
    except Exception as e:                                          # noqa: BLE001
        raise QuotePdfError("PDF_DOWNLOAD_UNAVAILABLE",
                            "PDF 다운로드 링크 발급에 실패했습니다.", 503) from e
    if not url or not str(url).strip():
        raise QuotePdfError("PDF_DOWNLOAD_UNAVAILABLE",
                            "PDF 다운로드 링크를 발급할 수 없습니다.", 503)
    return url


async def issue_or_get_quote_pdf(quote: Dict[str, Any], current_user_id: str) -> Dict[str, Any]:
    """멱등: 검증 통과 후 기존 PDF 재사용(generated=False) 또는 신규 생성. (라우터가 자사 소유권 선검증)"""
    item = _validate_snapshot(quote)                                # PATCH-1: 재사용 전에 계약 검증
    quote_id, company_id = quote["id"], quote["company_id"]
    existing = await _find_existing_pdf(quote_id, company_id)       # §15 sequential idempotency
    if existing:
        return {
            "document": existing,
            "generated": False,
            "url": await _safe_signed_url(existing["id"]),          # PATCH-3
        }
    supplier = _supplier_config()                                   # §4 (503 if missing)
    html = _render_html(quote, item, supplier, _quote_date_kst(quote.get("created_at")))
    pdf_bytes = render_html_pdf(html, trace_id=quote.get("quote_no"))
    doc = await document_svc.register_generated(
        file_bytes=pdf_bytes,
        file_name="TAI_견적서_{}.pdf".format(quote.get("quote_no")),
        mime_type="application/pdf",
        company_id=company_id,
        category="general",
        generated_by=GENERATED_BY,
        generation_params={
            "renderer": "gotenberg_chromium",
            "template_version": TEMPLATE_VERSION,
            "quote_no": quote.get("quote_no"),
            "snapshot_source": "quotes.items",
        },
        linked_table="quotes",
        linked_id=quote_id,
        tags=["quote", "member_auto"],
        uploaded_by=current_user_id,
    )
    if str(doc.get("company_id")) != str(company_id):               # §18 방어
        raise QuotePdfError("PDF_OWNERSHIP_MISMATCH", "문서 소유권 불일치.", 500)
    return {
        "document": doc,
        "generated": True,
        "url": await _safe_signed_url(doc["id"]),                   # PATCH-3
    }
