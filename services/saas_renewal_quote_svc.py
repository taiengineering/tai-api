"""TAI Safe SaaS Renewal Quote Creator — WO-COMM-V3-PAYMENT-MYPAGE-RENEWAL-WIRING-001.

역할:
  기존 V3 ACTIVE 계약 → current CV + site scopes 파생
  → canonical pricing criteria DB reload
  → 기존 V3 quote/pricing pipeline 재사용
  → Frozen Renewal Quote 발행 (survey_data.commercial_v3_renewal 바인딩)

금지:
  - client-supplied contract_id / product_tier / worker_capacity / site scopes / amount
  - 이전 payment snapshot 금액 복사 (현재 pricing policy 재계산)
  - DDL / DB Schema 변경
  - 새 결제 엔진 / 새 pricing engine
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from schemas.saas_pricing_preview_v2 import SaasPricingPreviewSiteRequestV2
from schemas.saas_quote_v2 import SaasQuoteIssueRequestV2
from services.saas_quote_v2 import SaasQuoteV2Error, issue_saas_quote_v2
from services.saas_quote_site_scope_v2 import QuoteSiteScopeError


_ALLOWED_RENEWAL_MONTHS = frozenset({3, 6, 9, 12})
_MANUAL_RENEWAL_TIERS = frozenset({"MANAGER", "FIELD"})
_PAID_STATUS = frozenset({"PAID", "SUCCESS"})
_RENEWAL_SCHEMA_VERSION = "SAAS_CONTRACT_COMMERCIAL_V2"
_ALLOWED_ANCHOR_TYPES = frozenset({"CARD", "RENEWAL"})


class SaasRenewalQuoteError(Exception):
    """Renewal Quote Creator 도메인 오류."""

    def __init__(self, code: str, message: str = "", http_status: int = 422) -> None:
        self.code = code
        self.message = message or code
        self.http_status = http_status
        super().__init__(self.message)


def _parse_paid_at(s) -> datetime:
    """Parse paid_at string → timezone-aware datetime. Raises ValueError if invalid/empty/naive."""
    if not s:
        raise ValueError("paid_at is empty or None")
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"paid_at not parseable: {s!r}") from exc
    if dt.tzinfo is None:
        raise ValueError(f"paid_at has no timezone: {s!r}")
    return dt


def _select_latest_eligible_payment_id(rows: list) -> Optional[str]:
    """Pure helper: CARD/RENEWAL only; strict paid_at; deterministic (paid_at, id) tie-breaker.

    Raises SaasRenewalQuoteError(RENEWAL_STATE_INVALID) if any CARD/RENEWAL row has
    invalid/missing paid_at — do NOT skip and fall back to an older row.
    Returns None if no CARD/RENEWAL rows exist.
    """
    candidates: list = []
    for p in rows:
        ptype = (p.get("payment_type") or "").upper()
        if ptype not in _ALLOWED_ANCHOR_TYPES:
            continue
        paid_at_raw = p.get("paid_at")
        try:
            dt = _parse_paid_at(paid_at_raw)
        except ValueError:
            raise SaasRenewalQuoteError(
                "RENEWAL_STATE_INVALID",
                f"결제 날짜 파싱 오류: {paid_at_raw!r}",
            )
        candidates.append((dt, str(p.get("id") or "")))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][1]


def _get_latest_eligible_payment_id(supabase, contract_id: str) -> Optional[str]:
    """Fetches PAID/SUCCESS SAAS payments for contract; delegates to _select_latest_eligible_payment_id.

    Raises SaasRenewalQuoteError(RENEWAL_STATE_INVALID) if any CARD/RENEWAL row has bad paid_at.
    Returns None if no CARD/RENEWAL payments exist.
    """
    res = (
        supabase.table("payments")
        .select("id, payment_type, paid_at")
        .eq("contract_id", contract_id)
        .eq("product_type", "SAAS")
        .in_("status_code", list(_PAID_STATUS))
        .execute()
    )
    return _select_latest_eligible_payment_id(res.data or [])


def is_renewal_quote_unique_violation(exc: Exception) -> bool:
    """PostgreSQL 23505 unique violation이 uix_quotes_v3_renewal_source_active인지 판정."""
    msg = str(exc)
    return "23505" in msg and "uix_quotes_v3_renewal_source_active" in msg


def _find_existing_renewal_quote(
    supabase, contract_id: str, version_no: int, company_id: str
) -> Optional[dict]:
    """같은 company/contract/version_no의 활성 ISSUED renewal quote 조회 (is_active=true 포함)."""
    res = (
        supabase.table("quotes")
        .select("id, quote_no, items, survey_data, status_code")
        .eq("company_id", company_id)
        .eq("source", "member_auto")
        .eq("service_type", "SAAS")
        .eq("status_code", "ISSUED")
        .eq("is_active", True)
        .execute()
    )
    for q in (res.data or []):
        sd = (q.get("survey_data") or {})
        if not isinstance(sd, dict):
            continue
        renewal_ctx = sd.get("commercial_v3_renewal")
        if not isinstance(renewal_ctx, dict):
            continue
        if (str(renewal_ctx.get("contract_id") or "") == str(contract_id)
                and int(renewal_ctx.get("current_version_no") or -1) == int(version_no)):
            return q
    return None


def create_renewal_quote(
    supabase,
    *,
    payment_id: str,
    company_id: str,
    user_id: str,
    payment_months: int,
) -> dict:
    """기존 ACTIVE V3 계약 기반 Renewal Frozen Quote 발행.

    DB Read:  payments(2) + contracts(1) + saas_contract_commercial_versions(N)
              + saas_contract_site_scopes(N) + factories/construction_sites (per scope)
    DB Write: quotes(1)
    DDL:      0
    Charge:   0

    Returns: quote row dict
    """
    from services.saas_commercial_version_time_v2 import (
        TemporalVersionError,
        find_future_commercial_versions_v2,
        select_effective_commercial_version_v2,
    )
    from services.time import now_kst

    if payment_months not in _ALLOWED_RENEWAL_MONTHS:
        raise SaasRenewalQuoteError(
            "RENEWAL_PAYMENT_MONTHS_INVALID",
            f"payment_months는 3/6/9/12 중 하나여야 합니다: {payment_months}",
        )

    # ── Step 1: payment 조회 + 소유권 확인 ──────────────────────────────
    pay_res = (
        supabase.table("payments")
        .select("id, company_id, contract_id, product_type, payment_type, "
                "status_code, period_months, quote_id")
        .eq("id", payment_id)
        .limit(1)
        .execute()
    )
    pay = (pay_res.data or [None])[0]
    if not pay:
        raise SaasRenewalQuoteError("PAYMENT_NOT_FOUND", "결제를 찾을 수 없습니다.", 404)
    if str(pay.get("company_id") or "") != str(company_id):
        raise SaasRenewalQuoteError("PAYMENT_NOT_OWNED", "결제를 찾을 수 없습니다.", 404)

    # ── Step 2: product_type / status / payment_type 가드 ──────────────
    if pay.get("product_type") != "SAAS":
        raise SaasRenewalQuoteError("NOT_COMMERCIAL_V3", "V3 SAAS 결제에만 연장이 가능합니다.")
    if (pay.get("status_code") or "") not in _PAID_STATUS:
        raise SaasRenewalQuoteError("NOT_SUCCESSFUL_PAYMENT", "완료된 결제에만 연장이 가능합니다.")
    if (pay.get("payment_type") or "").upper() not in _ALLOWED_ANCHOR_TYPES:
        raise SaasRenewalQuoteError(
            "NOT_COMMERCIAL_V3",
            "CARD 또는 RENEWAL 결제에만 연장이 가능합니다.",
        )

    # ── Step 3: contract 조회 ────────────────────────────────────────────
    contract_id = str(pay.get("contract_id") or "")
    if not contract_id:
        raise SaasRenewalQuoteError("CONTRACT_NOT_FOUND", "계약 정보를 찾을 수 없습니다.")

    ct_res = (
        supabase.table("contracts")
        .select("id, company_id, status_code, service_type, is_active, end_date")
        .eq("id", contract_id)
        .limit(1)
        .execute()
    )
    contract = (ct_res.data or [None])[0]
    if not contract or str(contract.get("company_id") or "") != str(company_id):
        raise SaasRenewalQuoteError("CONTRACT_NOT_FOUND", "계약 정보를 찾을 수 없습니다.", 404)
    if contract.get("status_code") != "ACTIVE":
        raise SaasRenewalQuoteError("CONTRACT_NOT_ACTIVE", "활성 계약에만 연장이 가능합니다.")
    if contract.get("service_type") != "SAAS":
        raise SaasRenewalQuoteError("CONTRACT_NOT_SAAS", "SaaS 계약에만 연장이 가능합니다.")
    if contract.get("is_active") is not True:
        raise SaasRenewalQuoteError("CONTRACT_NOT_ACTIVE", "활성 계약에만 연장이 가능합니다.")

    # ── Step 3.5: payment must be latest eligible for contract ──────────────
    latest_pid = _get_latest_eligible_payment_id(supabase, contract_id)
    if latest_pid != payment_id:
        raise SaasRenewalQuoteError("NOT_CURRENT_PAYMENT", "최신 결제에만 연장이 가능합니다.", 409)

    # ── Step 3-B: Temporal window guard ────────────────────────────────────────
    from services.saas_commercial_version_time_v2 import contract_end_date_to_effective_at_v2

    as_of = now_kst()
    end_date = contract.get("end_date")
    if not end_date:
        raise SaasRenewalQuoteError(
            "RENEWAL_END_DATE_REQUIRED",
            "계약 마감일 정보가 없어 연장이 불가합니다.",
            422,
        )
    try:
        contract_end_boundary = contract_end_date_to_effective_at_v2(end_date)
        if as_of >= contract_end_boundary:
            raise SaasRenewalQuoteError(
                "RENEWAL_WINDOW_CLOSED",
                "계약 연장 기간이 종료되었습니다.",
                422,
            )
    except SaasRenewalQuoteError:
        raise
    except Exception:
        raise SaasRenewalQuoteError(
            "RENEWAL_STATE_INVALID",
            "계약 날짜 파싱 오류.",
            422,
        )

    # ── Step 4: effective CV 조회 ────────────────────────────────────────
    cv_res = (
        supabase.table("saas_contract_commercial_versions")
        .select("id, version_no, product_tier, worker_capacity, commercial_schema_version, "
                "payment_months, pricing_mode, effective_from, superseded_at")
        .eq("contract_id", contract_id)
        .execute()
    )
    all_cvs = cv_res.data or []
    try:
        current_cv = select_effective_commercial_version_v2(all_cvs, as_of)
    except TemporalVersionError as exc:
        if exc.code == "TEMPORAL_CURRENT_NOT_FOUND":
            raise SaasRenewalQuoteError("CURRENT_CV_NOT_FOUND", "현재 계약 버전을 확인할 수 없습니다.")
        if exc.code == "TEMPORAL_CURRENT_AMBIGUOUS":
            raise SaasRenewalQuoteError("CURRENT_CV_AMBIGUOUS", "현재 계약 버전이 중복됩니다.")
        raise

    # ── Step 4-A: commercial_schema_version 검증 ──────────────────────────
    cv_schema = str(current_cv.get("commercial_schema_version") or "")
    if cv_schema != _RENEWAL_SCHEMA_VERSION:
        raise SaasRenewalQuoteError(
            "RENEWAL_STATE_INVALID",
            f"상업계약 스키마 버전이 지원되지 않습니다: {cv_schema}",
        )

    # ── Step 4-B: current CV payment_months 검증 (0/missing = invalid) ──────────────────────────
    cv_payment_months = int(current_cv.get("payment_months") or 0)
    if cv_payment_months == 1:
        raise SaasRenewalQuoteError(
            "RECURRING_MANAGED_AUTOMATICALLY",
            "정기결제 계약은 수동 연장이 불가합니다.",
        )
    if cv_payment_months not in _ALLOWED_RENEWAL_MONTHS:
        raise SaasRenewalQuoteError(
            "RENEWAL_STATE_INVALID",
            f"현재 계약의 결제 주기가 연장 불가 상태입니다: {cv_payment_months}",
        )

    # ── Step 5: product_tier 연장 자격 검증 ─────────────────────────────
    product_tier = str(current_cv.get("product_tier") or "")
    if product_tier not in _MANUAL_RENEWAL_TIERS:
        code = (
            "CUSTOM_REVIEW_REQUIRED" if product_tier == "CUSTOM"
            else "NOT_COMMERCIAL_V3"
        )
        raise SaasRenewalQuoteError(code, f"수동 연장이 불가한 상품입니다: {product_tier}")

    # ── Step 6: 이미 예약된 renewal CV 가드 ─────────────────────────────
    future_cvs = find_future_commercial_versions_v2(all_cvs, as_of)
    if future_cvs:
        raise SaasRenewalQuoteError(
            "RENEWAL_ALREADY_SCHEDULED",
            "이미 예약된 연장이 있습니다.",
            409,
        )

    # ── Step 7: site scopes 조회 ─────────────────────────────────────────
    cv_id = str(current_cv.get("id") or "")
    ss_res = (
        supabase.table("saas_contract_site_scopes")
        .select("entity_type, entity_id, sector")
        .eq("commercial_version_id", cv_id)
        .execute()
    )
    scopes = ss_res.data or []
    if not scopes:
        raise SaasRenewalQuoteError("SITE_SCOPES_EMPTY", "계약 사업장 정보가 없습니다.")

    # ── Step 8: canonical criteria DB reload ────────────────────────────
    from services.saas_quote_site_scope_v2 import (
        _load_factory,
        _load_construction_site,
        _canonical_criteria,
        QuoteSiteScopeError,
        _FACTORY_SECTORS,
    )

    canonical_sites = []
    for scope in scopes:
        entity_type = scope.get("entity_type") or ""
        entity_id_str = str(scope.get("entity_id") or "")
        sector = str(scope.get("sector") or "")

        if sector in _FACTORY_SECTORS:
            row = _load_factory(supabase, entity_id_str)
        else:
            row = _load_construction_site(supabase, entity_id_str)

        if not row or str(row.get("company_id") or "") != str(company_id):
            raise SaasRenewalQuoteError(
                "SITE_SCOPE_INVALID",
                "사업장 정보를 확인할 수 없습니다.",
            )

        canonical_value = _canonical_criteria(sector, row)
        if canonical_value is None or float(canonical_value) < 0:
            raise SaasRenewalQuoteError(
                "SITE_CRITERIA_REQUIRED",
                "사업장 규모 정보를 먼저 보완해 주세요.",
            )

        canonical_sites.append(
            SaasPricingPreviewSiteRequestV2(
                entity_id=UUID(entity_id_str),
                sector=sector,
                criteria_value=canonical_value,
            )
        )

    # ── Step 8-B: 기존 활성 renewal quote 조회 (idempotency) ─────────────
    version_no = int(current_cv.get("version_no") or 0)
    existing_rq = _find_existing_renewal_quote(supabase, contract_id, version_no, company_id)
    if existing_rq:
        existing_pm = None
        try:
            items = existing_rq.get("items") or []
            if items and isinstance(items[0], dict):
                snap_data = items[0].get("pricing_snapshot") or {}
                existing_pm = int(snap_data.get("payment_months") or 0)
        except Exception:  # noqa: BLE001
            existing_pm = None

        if existing_pm is not None and existing_pm == payment_months:
            return existing_rq  # 동일 조건 → 기존 quote 반환 (idempotent)
        else:
            raise SaasRenewalQuoteError(
                "RENEWAL_QUOTE_ALREADY_ISSUED",
                "동일 계약 버전에 대해 이미 연장 견적이 발행되었습니다.",
                409,
            )

    # ── Step 9: 기존 V3 quote issue pipeline 호출 ────────────────────────
    worker_capacity = int(current_cv.get("worker_capacity") or 0)
    request = SaasQuoteIssueRequestV2(
        product_tier=product_tier,
        worker_capacity=worker_capacity,
        payment_months=payment_months,
        sites=canonical_sites,
    )

    server_survey_data = {
        "commercial_v3_renewal": {
            "contract_id": contract_id,
            "current_version_no": version_no,
            "origin_payment_id": payment_id,
        }
    }

    try:
        quote = issue_saas_quote_v2(
            supabase, request, user_id, company_id,
            server_survey_data=server_survey_data,
        )
    except SaasQuoteV2Error:
        raise
    except QuoteSiteScopeError:
        raise
    except Exception as exc:
        if is_renewal_quote_unique_violation(exc):
            # 23505 race: re-read existing quote
            existing = _find_existing_renewal_quote(supabase, contract_id, version_no, company_id)
            if existing:
                ex_pm = None
                try:
                    items = existing.get("items") or []
                    if items and isinstance(items[0], dict):
                        ex_pm = int((items[0].get("pricing_snapshot") or {}).get("payment_months") or 0)
                except Exception:  # noqa: BLE001
                    pass
                if ex_pm is not None and ex_pm == payment_months:
                    return existing
            raise SaasRenewalQuoteError(
                "RENEWAL_QUOTE_ALREADY_ISSUED",
                "동일 계약 버전에 대해 이미 연장 견적이 발행되었습니다.",
                409,
            )
        raise

    return quote


def create_member_renewal_quote(
    supabase,
    *,
    user_id: str,
    company_id: str,
    payment_months: int,
) -> dict:
    """회원 권한 기반 Renewal Quote 발행 — client는 payment_months만 제공.

    server가 company_id로 active V3 contract를 파생하고,
    latest eligible payment를 파생하여 create_renewal_quote()를 호출한다.

    금지:
      - client-supplied contract_id / payment_id / product_tier / amount / site scopes
    """
    from services.member_commercial_svc import get_member_commercial_contract

    if payment_months not in _ALLOWED_RENEWAL_MONTHS:
        raise SaasRenewalQuoteError(
            "RENEWAL_PAYMENT_MONTHS_INVALID",
            f"payment_months는 3/6/9/12 중 하나여야 합니다: {payment_months}",
        )

    ctx = get_member_commercial_contract(supabase, company_id)
    if ctx.get("state") != "ACTIVE":
        error_code = ctx.get("error_code") or "CONTRACT_NOT_ACTIVE"
        raise SaasRenewalQuoteError(
            error_code if error_code in {"NO_ACTIVE_SAAS_CONTRACT"} else "CONTRACT_NOT_ACTIVE",
            "활성 V3 계약이 없습니다.",
            422,
        )

    contract = ctx["contract"]
    contract_id = str(contract.get("id") or "")
    if not contract_id:
        raise SaasRenewalQuoteError("CONTRACT_NOT_FOUND", "계약 정보를 찾을 수 없습니다.", 404)

    # CUSTOM 계약은 수동 갱신 자동화 대상이 아님 — early reject
    cv = ctx.get("commercial_version") or {}
    product_tier = str(cv.get("product_tier") or "")
    if product_tier == "CUSTOM":
        raise SaasRenewalQuoteError(
            "CUSTOM_REVIEW_REQUIRED",
            "맞춤형 계약은 담당자에게 문의해 주세요.",
            422,
        )

    payment_id = _get_latest_eligible_payment_id(supabase, contract_id)
    if not payment_id:
        raise SaasRenewalQuoteError(
            "PAYMENT_NOT_FOUND",
            "갱신 가능한 결제 내역이 없습니다.",
            422,
        )

    return create_renewal_quote(
        supabase,
        payment_id=payment_id,
        company_id=company_id,
        user_id=user_id,
        payment_months=payment_months,
    )
