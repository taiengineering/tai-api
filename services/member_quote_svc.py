"""회원 견적 Core 서비스 — 가격계산·번호생성·저장·조회.

WO-MYPAGE-QUOTE-PROCESS-001 STEP 2A.
가격 SoT = price_master(service_type+sector+tier_code+is_active). 금액은 전부 서버 파생.
소유권 경계(require_company_id/_ensure_own_company/scoped_list_company)는 라우터가 강제하고,
이 서비스는 이미 해소된 company_id/created_by 를 받아 동작한다.
"""
from __future__ import annotations

import secrets
from typing import Any, Dict, Optional

from services.time import now_kst

MEMBER_SOURCES = ("member_auto", "member_custom")


class MemberQuoteError(Exception):
    """도메인 오류. code 로 라우터가 HTTP 로 번역한다."""
    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _fetch_price_row(supabase, service_type: str, sector: str, tier_code: str) -> Optional[Dict[str, Any]]:
    # tier_code 는 service_type 간 유일하지 않다 → 3키 + is_active 로 조회
    res = (
        supabase.table("price_master")
        .select("id, service_type, sector, tier_code, criteria_type, billing_unit, "
                "amount, vat_rate, vat_included, display_name, is_active")
        .eq("service_type", service_type).eq("sector", sector)
        .eq("tier_code", tier_code).eq("is_active", True)
        .limit(1).execute()
    )
    return res.data[0] if res.data else None


def calc_quote(supabase, service_type: str, sector: str, tier_code: str,
               term_months: Optional[int]) -> Dict[str, Any]:
    """price_master 로부터 서버 계산. 클라이언트 금액은 절대 신뢰하지 않는다."""
    service_type = (service_type or "").upper()
    sector = (sector or "").upper()
    tier_code = (tier_code or "").upper()

    row = _fetch_price_row(supabase, service_type, sector, tier_code)
    if not row:
        raise MemberQuoteError("PRICE_NOT_FOUND",
                               f"가격을 찾을 수 없습니다: {service_type}/{sector}/{tier_code}", 404)

    amount = int(row.get("amount") or 0)
    billing_unit = (row.get("billing_unit") or "").upper()

    # CUSTOM: 자동견적 금지 → 개별견적 유도 (실측상 CUSTOM 행은 amount=0)
    if amount <= 0 or tier_code.endswith("_CUSTOM"):
        raise MemberQuoteError("CUSTOM_QUOTE_REQUIRED",
                               "맞춤 견적 대상입니다. 개별 견적으로 요청하세요.", 409)

    if billing_unit == "MONTHLY":
        try:
            months = int(term_months) if term_months is not None else 0
        except (TypeError, ValueError):
            months = 0
        if months < 1:
            raise MemberQuoteError("TERM_REQUIRED", "SaaS 견적은 term_months(1 이상)가 필요합니다.", 422)
        quantity, supply = months, amount * months
    elif billing_unit == "ONCE":
        months, quantity, supply = None, 1, amount   # 기간 배수 금지
    else:
        raise MemberQuoteError("BILLING_UNIT_UNSUPPORTED", f"미지원 billing_unit: {billing_unit}", 422)

    # VAT — price_master row 기준. 하드코딩 금지.
    if bool(row.get("vat_included")):
        raise MemberQuoteError("VAT_INCLUDED_UNSUPPORTED",
                               "vat_included=true 역산 규칙 없음 — HARD STOP.", 422)
    vat_rate = float(row.get("vat_rate") or 0)
    vat = round(supply * vat_rate)
    total = supply + vat

    return {
        "price_id": row["id"], "service_type": service_type, "sector": sector,
        "tier_code": tier_code, "display_name": row.get("display_name"),
        "billing_unit": billing_unit, "unit_amount": amount, "term_months": months,
        "quantity": quantity, "supply_amount": supply,
        "vat_rate": vat_rate, "vat_amount": vat, "total_amount": total,
    }


def _snapshot_item(c: Dict[str, Any]) -> Dict[str, Any]:
    # 발행 당시 가격 snapshot(정본) — 이후 price_master.amount 변경돼도 기존 견적 불변.
    # PDF 가 이 item 을 정본으로 읽도록 금액 3종(supply/vat/total) 모두 고정.
    return {k: c[k] for k in ("price_id", "service_type", "sector", "tier_code",
                              "display_name", "billing_unit", "unit_amount",
                              "term_months", "quantity", "supply_amount",
                              "vat_rate", "vat_amount", "total_amount")}


def _gen_quote_no_candidate() -> str:
    """QT-YYYYMMDD-XXXXXXXX. 매 시도 새 후보."""
    return f"QT-{now_kst().strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"


def _is_quote_no_conflict(exc: Exception) -> bool:
    """오직 quotes.quote_no UNIQUE(23505 + quotes_quote_no_key)만 True.
    다른 23505·FK·검증·DB장애는 False → retry 금지."""
    parts = []
    for attr in ("code", "message", "details", "hint", "constraint"):
        v = getattr(exc, attr, None)
        if v:
            parts.append(str(v))
    if getattr(exc, "args", None):
        parts.append(str(exc.args[0]))
    blob = " ".join(parts) + " " + str(exc)
    return ("23505" in blob) and (("quotes_quote_no_key" in blob) or ("quote_no" in blob))


def _insert_quote_with_unique_retry(supabase, base_row: Dict[str, Any], retries: int = 5) -> Dict[str, Any]:
    """quote_no 를 매 시도 새로 생성해 INSERT. quote_no UNIQUE 충돌만 재시도.
    그 외 오류는 즉시 전파(retry 0). 소진 시 controlled MemberQuoteError(503)."""
    for _ in range(max(1, retries)):
        row = dict(base_row)
        row["quote_no"] = _gen_quote_no_candidate()
        try:
            res = supabase.table("quotes").insert(row).execute()
        except Exception as exc:  # noqa: BLE001
            if _is_quote_no_conflict(exc):
                continue
            raise
        if not res.data:
            raise MemberQuoteError("INSERT_FAILED", "견적 저장 실패", 500)
        return res.data[0]
    raise MemberQuoteError("QUOTE_NO_CONFLICT", "견적번호 생성 재시도 소진", 503)


def _company_name_snapshot(supabase, company_id) -> Optional[str]:
    """발급 당시 수신 회사명 고정(내부결재 첨부 문서). 이후 회사명 변경돼도 불변.
    best-effort — 회사행 없으면 None(발급 자체는 막지 않음)."""
    if not company_id:
        return None
    try:
        r = supabase.table("companies").select("name").eq("id", company_id).limit(1).execute()
        return r.data[0].get("name") if r.data else None
    except Exception:
        return None


def create_auto_quote(supabase, company_id, created_by, service_type, sector, tier_code, term_months):
    calc = calc_quote(supabase, service_type, sector, tier_code, term_months)  # 서버 재계산
    now = now_kst().isoformat()
    base_row = {
        "company_id": company_id, "company_name": _company_name_snapshot(supabase, company_id),
        "created_by": created_by, "source": "member_auto", "status_code": "ISSUED",
        "service_type": calc["service_type"], "items": [_snapshot_item(calc)],
        "supply_amount": calc["supply_amount"], "vat_amount": calc["vat_amount"],
        "total_amount": calc["total_amount"], "is_active": True, "created_at": now, "updated_at": now,
    }
    return _insert_quote_with_unique_retry(supabase, base_row)


def create_custom_quote(supabase, company_id, created_by, service_type, sector, request_title, request_detail):
    now = now_kst().isoformat()
    base_row = {
        "company_id": company_id, "company_name": _company_name_snapshot(supabase, company_id),
        "created_by": created_by, "source": "member_custom", "status_code": "REQUESTED",
        "service_type": (service_type or "").upper() or None,
        "items": [], "supply_amount": 0, "vat_amount": 0, "total_amount": 0,
        # 요청내용: survey_data 를 member_custom 네임스페이스로(설문 흐름과 형태 충돌 없음) + memo 요약
        "survey_data": {"member_custom": {"sector": (sector or "").upper() or None,
                                          "request_title": request_title, "request_detail": request_detail}},
        "memo": f"[개별견적] {request_title}", "is_active": True, "created_at": now, "updated_at": now,
    }
    return _insert_quote_with_unique_retry(supabase, base_row)


_LIST_COLS = ("id, quote_no, service_type, status_code, source, items, "
              "supply_amount, vat_amount, total_amount, created_by, created_at")


def list_member_quotes(supabase, company_id: Optional[str], page: int, page_size: int) -> Dict[str, Any]:
    q = supabase.table("quotes").select(_LIST_COLS, count="exact").in_("source", list(MEMBER_SOURCES))
    if company_id:  # None(ALL) 이면 회사 필터 생략, 그 외엔 자사만
        q = q.eq("company_id", company_id)
    off = (page - 1) * page_size
    res = q.order("created_at", desc=True).range(off, off + page_size - 1).execute()
    return {"items": res.data or [], "total": res.count or 0, "page": page,
            "page_size": page_size, "total_pages": ((res.count or 0) + page_size - 1) // page_size}


def get_member_quote(supabase, quote_id: str) -> Optional[Dict[str, Any]]:
    res = (supabase.table("quotes").select("*").eq("id", quote_id)
           .in_("source", list(MEMBER_SOURCES)).limit(1).execute())
    return res.data[0] if res.data else None
