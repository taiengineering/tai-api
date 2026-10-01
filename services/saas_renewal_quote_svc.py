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

from typing import Optional
from uuid import UUID

from schemas.saas_pricing_preview_v2 import SaasPricingPreviewSiteRequestV2
from schemas.saas_quote_v2 import SaasQuoteIssueRequestV2
from services.saas_quote_v2 import SaasQuoteV2Error, issue_saas_quote_v2
from services.saas_quote_site_scope_v2 import QuoteSiteScopeError


_ALLOWED_RENEWAL_MONTHS = frozenset({3, 6, 9, 12})
_MANUAL_RENEWAL_TIERS = frozenset({"MANAGER", "FIELD"})
_PAID_STATUS = frozenset({"PAID", "SUCCESS"})


class SaasRenewalQuoteError(Exception):
    """Renewal Quote Creator 도메인 오류."""

    def __init__(self, code: str, message: str = "", http_status: int = 422) -> None:
        self.code = code
        self.message = message or code
        self.http_status = http_status
        super().__init__(self.message)


def create_renewal_quote(
    supabase,
    *,
    payment_id: str,
    company_id: str,
    user_id: str,
    payment_months: int,
) -> dict:
    """기존 ACTIVE V3 계약 기반 Renewal Frozen Quote 발행.

    DB Read:  payments(1) + contracts(1) + saas_contract_commercial_versions(N)
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

    # ── Step 2: product_type / status 가드 ──────────────────────────────
    if pay.get("product_type") != "SAAS":
        raise SaasRenewalQuoteError("NOT_COMMERCIAL_V3", "V3 SAAS 결제에만 연장이 가능합니다.")
    if (pay.get("status_code") or "") not in _PAID_STATUS:
        raise SaasRenewalQuoteError("NOT_SUCCESSFUL_PAYMENT", "완료된 결제에만 연장이 가능합니다.")

    # ── Step 3: contract 조회 ────────────────────────────────────────────
    contract_id = str(pay.get("contract_id") or "")
    if not contract_id:
        raise SaasRenewalQuoteError("CONTRACT_NOT_FOUND", "계약 정보를 찾을 수 없습니다.")

    ct_res = (
        supabase.table("contracts")
        .select("id, company_id, status_code, service_type, end_date")
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

    # ── Step 3-B: Temporal window guard ────────────────────────────────────────
    from services.saas_commercial_version_time_v2 import contract_end_date_to_effective_at_v2

    as_of = now_kst()
    end_date = contract.get("end_date")
    if end_date:
        contract_end_boundary = contract_end_date_to_effective_at_v2(end_date)
        if as_of >= contract_end_boundary:
            raise SaasRenewalQuoteError(
                "RENEWAL_WINDOW_CLOSED",
                "계약 연장 기간이 종료되었습니다.",
                422,
            )

    # ── Step 4: effective CV 조회 ────────────────────────────────────────
    # as_of already set in Step 3-B
    cv_res = (
        supabase.table("saas_contract_commercial_versions")
        .select("id, version_no, product_tier, worker_capacity, commercial_schema_version, "
                "pricing_mode, effective_from, superseded_at")
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

    # ── Step 5: product_tier 연장 자격 검증 ─────────────────────────────
    product_tier = str(current_cv.get("product_tier") or "")
    if product_tier not in _MANUAL_RENEWAL_TIERS:
        code = (
            "RECURRING_MANAGED_AUTOMATICALLY" if product_tier == ""
            else "CUSTOM_REVIEW_REQUIRED" if product_tier == "CUSTOM"
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
    # re-use existing site scope resolver with DB-authority criteria
    # We build SaasPricingPreviewSiteRequestV2 with placeholder criteria=0,
    # then let resolve_quote_site_scope_v2 reload from DB.
    # BUT resolve_quote_site_scope_v2 raises QUOTE_SITE_DATA_CHANGED if value differs.
    # So we load DB criteria directly and build canonical sites.
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

    # ── Step 9: 기존 V3 quote issue pipeline 호출 ────────────────────────
    worker_capacity = int(current_cv.get("worker_capacity") or 0)
    request = SaasQuoteIssueRequestV2(
        product_tier=product_tier,
        worker_capacity=worker_capacity,
        payment_months=payment_months,
        sites=canonical_sites,
    )

    version_no = int(current_cv.get("version_no") or 0)
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

    return quote
