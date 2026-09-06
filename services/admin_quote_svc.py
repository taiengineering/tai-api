"""관리자 견적 서비스 — STEP 2D-A.

WO-MYPAGE-QUOTE-PROCESS-001. 소스 확장:
  admin_manual                   — 관리자 수동 발행(신규 row · ISSUED 즉시)
  member_custom REQUESTED→ISSUED — 기존 row 조건부 UPDATE(same-row)

권한 강제(_require_admin)는 라우터에서 선행. 여기서는 이미 인증된 admin으로 동작.
가격 정본 = 관리자 입력 unit_amount + billing_unit + term_months/quantity + vat_rate.
클라이언트가 준 supply/vat/total 은 신뢰 0(수신하지 않는다 — 라우터가 body에서 제외).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from services import member_quote_svc as mq_svc
from services.time import now_kst


# STEP 2D-A: admin 화면은 3소스를 함께 본다(회원 자동 + 회원 개별 + 관리자 수동).
# survey_web / 기타 legacy 는 admin 화면에도 노출 금지.
ADMIN_SOURCES = ("member_auto", "member_custom", "admin_manual")


class AdminQuoteError(Exception):
    """도메인 오류. code 로 라우터가 HTTP 로 번역한다."""
    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


# ─ PATCH-1 helpers ────────────────────────────────────────────────────
def _normalize_display_name(value: Optional[str]) -> str:
    """None/빈문자/공백 → 422 DISPLAY_NAME_REQUIRED. 그 외 trim.
    (PATCH-1 : PDF 슬롯 채움을 보증하기 위해 필수화 · 서버 재계산 SoT 규율과 정합)."""
    if value is None:
        raise AdminQuoteError("DISPLAY_NAME_REQUIRED",
                              "상품명(display_name)은 필수입니다.", 422)
    v = str(value).strip()
    if not v:
        raise AdminQuoteError("DISPLAY_NAME_REQUIRED",
                              "상품명(display_name)은 필수입니다.", 422)
    return v


def _require_company_name(supabase, company_id: str) -> str:
    """company_id 로 회사명 재조회. 미존재/공백 → 404 COMPANY_NOT_FOUND.
    (PATCH-1 : company snapshot 이 None 인 채로 quote 를 발행/발송하는 것을 차단)."""
    name = mq_svc._company_name_snapshot(supabase, company_id)
    if not name or not str(name).strip():
        raise AdminQuoteError("COMPANY_NOT_FOUND", "회사를 찾을 수 없습니다.", 404)
    return name


def calc_manual_quote(service_type, sector, tier_code, display_name,
                      billing_unit, term_months, quantity, unit_amount,
                      vat_rate: Optional[float] = 0.1) -> Dict[str, Any]:
    """관리자 수동 견적 계산 — 서버 정본.

    입력 계약 :
      billing_unit  = MONTHLY(term_months>=1) | ONCE(quantity>=1)
      unit_amount   > 0 (원)
      vat_rate      in [0, 1] (기본 0.1)
      display_name  : 표시 문자열(선택; PDF slot 채움)
      service_type / sector / tier_code : 라벨. price_master 조회 없음.

    출력 = single item snapshot (member_auto shape 와 동일 key set — PDF 재사용 정합).
    """
    # PATCH-1 : display_name 필수 (정규화된 값을 item 에 저장).
    display_name = _normalize_display_name(display_name)
    bu = (billing_unit or "").upper()
    try:
        ua = int(unit_amount)
    except (TypeError, ValueError):
        ua = 0
    if ua <= 0:
        raise AdminQuoteError("INVALID_UNIT_AMOUNT", "단가는 0보다 커야 합니다.", 422)
    vr = float(vat_rate if vat_rate is not None else 0.1)
    if not (0.0 <= vr <= 1.0):
        raise AdminQuoteError("INVALID_VAT_RATE", "vat_rate 는 0 이상 1 이하여야 합니다.", 422)

    if bu == "MONTHLY":
        try:
            m = int(term_months if term_months is not None else 0)
        except (TypeError, ValueError):
            m = 0
        if m < 1:
            raise AdminQuoteError("TERM_REQUIRED", "MONTHLY 는 이용기간(1 이상)이 필요합니다.", 422)
        qty, supply = m, ua * m
    elif bu == "ONCE":
        try:
            q = int(quantity if quantity is not None else 0)
        except (TypeError, ValueError):
            q = 0
        if q < 1:
            raise AdminQuoteError("QUANTITY_REQUIRED", "ONCE 는 수량(1 이상)이 필요합니다.", 422)
        m, qty, supply = None, q, ua * q
    else:
        raise AdminQuoteError("BILLING_UNIT_UNSUPPORTED",
                              f"미지원 billing_unit: {bu or '(빈 값)'}", 422)

    vat = round(supply * vr)
    total = supply + vat

    return {
        "price_id": None,                                    # admin_manual 은 price_master 참조 없음
        "service_type": (service_type or "").upper() or None,
        "sector": (sector or "").upper() or None,
        "tier_code": tier_code or None,
        "display_name": display_name,
        "billing_unit": bu,
        "unit_amount": ua,
        "term_months": m,
        "quantity": qty,
        "supply_amount": supply,
        "vat_rate": vr,
        "vat_amount": vat,
        "total_amount": total,
    }


def create_admin_manual(supabase, admin_user_id, company_id, contact_name,
                        service_type, sector, tier_code, display_name,
                        billing_unit, term_months, quantity, unit_amount,
                        vat_rate: Optional[float] = 0.1,
                        memo: Optional[str] = None) -> Dict[str, Any]:
    """admin_manual/ISSUED 신규 견적 발행 (single-item).

    PATCH-1 : company_name 재조회를 _require_company_name 로 강제 (미존재 → 404, insert 0).
    """
    if not company_id:
        raise AdminQuoteError("COMPANY_REQUIRED", "회사 지정이 필요합니다.", 422)
    # PATCH-1 : 회사 존재/이름 스냅샷을 calc 이전에 확인. calc 도중 예외로 insert 이 시도되는 경로 봉쇄.
    company_name = _require_company_name(supabase, company_id)
    item = calc_manual_quote(service_type, sector, tier_code, display_name,
                             billing_unit, term_months, quantity, unit_amount, vat_rate)
    now = now_kst().isoformat()
    base_row = {
        "company_id": company_id,
        "company_name": company_name,
        "created_by": admin_user_id,
        "source": "admin_manual",
        "status_code": "ISSUED",
        "contact_name": mq_svc.normalize_contact_name(contact_name),
        "service_type": item["service_type"],
        "items": [item],
        "supply_amount": item["supply_amount"],
        "vat_amount": item["vat_amount"],
        "total_amount": item["total_amount"],
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    if memo:
        base_row["memo"] = memo
    return mq_svc._insert_quote_with_unique_retry(supabase, base_row)


def issue_custom(supabase, quote_id, service_type, sector, tier_code, display_name,
                 billing_unit, term_months, quantity, unit_amount,
                 vat_rate: Optional[float] = 0.1,
                 memo: Optional[str] = None) -> Dict[str, Any]:
    """member_custom + REQUESTED → ISSUED 전환 (same-row conditional UPDATE).

    조건부 UPDATE (source=member_custom AND status_code=REQUESTED).
      0행 = 이미 ISSUED 되었거나 다른 source → AdminQuoteError("QUOTE_ALREADY_ISSUED", 409)

    보존(SET 미포함, 자동 유지) : quote_no · company_id · company_name ·
      contact_name · survey_data · created_at · created_by · source.
    변경(SET 포함) : items · supply/vat/total · status_code · updated_at · (memo).
    """
    item = calc_manual_quote(service_type, sector, tier_code, display_name,
                             billing_unit, term_months, quantity, unit_amount, vat_rate)
    now = now_kst().isoformat()
    patch: Dict[str, Any] = {
        "items": [item],
        "supply_amount": item["supply_amount"],
        "vat_amount": item["vat_amount"],
        "total_amount": item["total_amount"],
        "status_code": "ISSUED",
        "updated_at": now,
    }
    if memo:
        patch["memo"] = memo
    res = (
        supabase.table("quotes").update(patch)
        .eq("id", quote_id)
        .eq("source", "member_custom")
        .eq("status_code", "REQUESTED")
        .execute()
    )
    if not res.data:
        raise AdminQuoteError("QUOTE_ALREADY_ISSUED",
                              "요청 상태의 개별 견적이 아닙니다.", 409)
    return res.data[0]


def _derive_dates(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """§7 : DB 컬럼 신설 없이 requested_at / issued_at 파생.

    member_auto / admin_manual  : issued_at = created_at (동시 발행)
    member_custom REQUESTED     : requested_at = created_at
    member_custom ISSUED        : requested_at = created_at, issued_at = updated_at
    """
    if not row:
        return row
    src = row.get("source")
    st = row.get("status_code")
    ca = row.get("created_at")
    ua = row.get("updated_at")
    if src == "member_custom":
        row["requested_at"] = ca
        row["issued_at"] = ua if st == "ISSUED" else None
    else:
        row["issued_at"] = ca
    return row


_LIST_COLS_ADMIN = (
    "id, quote_no, service_type, source, status_code, "
    "company_id, company_name, contact_name, "
    "items, supply_amount, vat_amount, total_amount, "
    "created_by, memo, created_at, updated_at"
)


def _match_search(row: Dict[str, Any], needle: str) -> bool:
    n = (needle or "").strip().lower()
    if not n:
        return True
    for k in ("quote_no", "company_name", "contact_name"):
        v = row.get(k)
        if v and n in str(v).lower():
            return True
    return False


def list_admin_quotes(supabase, page: int, page_size: int,
                      source: Optional[str] = None,
                      status_code: Optional[str] = None,
                      search: Optional[str] = None) -> Dict[str, Any]:
    """관리자 견적 목록. ADMIN_SOURCES 만(survey_web 등 legacy 제외).

    필터 : source · status_code · search(quote_no / company_name / contact_name 부분 매칭).
    search 는 응답을 받은 뒤 Python 후속 필터(MVP + FakeSupabase 호환).
    """
    q = (
        supabase.table("quotes")
        .select(_LIST_COLS_ADMIN, count="exact")
        .in_("source", list(ADMIN_SOURCES))
    )
    if source:
        q = q.eq("source", source)
    if status_code:
        q = q.eq("status_code", status_code)
    res = q.order("created_at", desc=True).execute()
    rows = res.data or []
    if search:
        rows = [r for r in rows if _match_search(r, search)]
    total = len(rows) if search else (res.count if res.count is not None else len(rows))
    off = max(0, (page - 1) * page_size)
    page_rows = rows[off:off + page_size]
    items = [_derive_dates(r) for r in page_rows]
    total_pages = (total + page_size - 1) // page_size
    return {"items": items, "total": total, "page": page,
            "page_size": page_size, "total_pages": total_pages}


def get_admin_quote(supabase, quote_id: str) -> Optional[Dict[str, Any]]:
    """관리자 상세 조회. ADMIN_SOURCES 외 source 는 None 반환(라우터가 404 로 번역)."""
    res = (
        supabase.table("quotes").select("*").eq("id", quote_id)
        .in_("source", list(ADMIN_SOURCES)).limit(1).execute()
    )
    if not res.data:
        return None
    return _derive_dates(res.data[0])
