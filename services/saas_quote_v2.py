"""TAI Safe SaaS Quote V2 — Issue Domain Service.

역할:
  Issue Request
  → Site Scope 검증 (소유권·섹터·가격기준 Canonicalization)
  → 서버 재가격계산 (Preview V2, Canonical Request 사용)
  → Pricing Status Gate
  → Snapshot 검증
  → Frozen Composite Item 구성
  → quotes INSERT (기존 V1 retry helper 재사용)

금지:
  - 가격 수식 직접 작성 (uplift / worker 누진 / VAT / term discount)
  - pricing_resolver_svc 직접 호출
  - saas_pricing_composer_v2 직접 호출
  - Client preview snapshot 신뢰
  - Contract / Subscription / Payment 생성
  - DDL / DB Schema 변경
"""
from __future__ import annotations

from typing import List

from pydantic import ValidationError

import services.member_quote_svc as member_quote_svc
from schemas.saas_pricing_v2 import SaasPricingSnapshotV2
from schemas.saas_quote_v2 import (
    SAAS_QUOTE_SCHEMA_VERSION,
    SaasQuoteIssueRequestV2,
    SaasQuoteSnapshotItemV2,
    _DISPLAY_NAMES,
)
from services.saas_pricing_composer_v2 import SaasPricingCalculationResult
from services.saas_pricing_preview_v2 import _SECTOR_ENTITY_TYPE, preview_saas_price_v2
from services.saas_quote_site_scope_v2 import QuoteSiteScopeError, resolve_quote_site_scope_v2
from services.time import now_kst


# ── Domain Error ──────────────────────────────────────────────────────────────

class SaasQuoteV2Error(Exception):
    """Quote V2 도메인 invariant violation.

    code values:
      QUOTE_PRICING_NOT_READY       — TERM_DISCOUNT_UNRESOLVED
      CUSTOM_QUOTE_REQUIRED         — product_tier=CUSTOM
      COMPLIANCE_BASE_QUOTE_REQUIRED — legacy compliance custom band
      QUOTE_SNAPSHOT_INVALID        — snapshot 정합성 오류
      COMPANY_SNAPSHOT_REQUIRED     — 회사명 미확인
    """

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


# ── Internal Helpers ──────────────────────────────────────────────────────────

def _validate_snapshot_against_request(
    snap: SaasPricingSnapshotV2,
    request: SaasQuoteIssueRequestV2,
) -> None:
    """Snapshot ↔ Request 교차검증. 불일치 시 QUOTE_SNAPSHOT_INVALID."""
    if snap.product_tier != request.product_tier:
        raise SaasQuoteV2Error(
            "QUOTE_SNAPSHOT_INVALID",
            f"product_tier 불일치: snap={snap.product_tier}, req={request.product_tier}",
        )
    if snap.worker.capacity != request.worker_capacity:
        raise SaasQuoteV2Error(
            "QUOTE_SNAPSHOT_INVALID",
            f"worker.capacity 불일치: snap={snap.worker.capacity}, req={request.worker_capacity}",
        )
    if snap.payment_months != request.payment_months:
        raise SaasQuoteV2Error(
            "QUOTE_SNAPSHOT_INVALID",
            f"payment_months 불일치: snap={snap.payment_months}, req={request.payment_months}",
        )
    if snap.pricing_mode != "STANDARD":
        raise SaasQuoteV2Error(
            "QUOTE_SNAPSHOT_INVALID",
            f"pricing_mode=STANDARD 아님: {snap.pricing_mode}",
        )
    req_set = {(_SECTOR_ENTITY_TYPE[s.sector], str(s.entity_id), s.sector) for s in request.sites}
    snap_set = {(str(site.entity_type), str(site.entity_id), str(site.sector)) for site in snap.sites}
    if req_set != snap_set:
        raise SaasQuoteV2Error(
            "QUOTE_SNAPSHOT_INVALID",
            f"site identity/sector 불일치: req={req_set}, snap={snap_set}",
        )


def _canonical_sites(request: SaasQuoteIssueRequestV2) -> list:
    """canonical order (sector ASC, entity_id ASC) pricing_input sites."""
    return sorted(
        request.sites,
        key=lambda s: (s.sector, str(s.entity_id)),
    )


def _build_pricing_input(request: SaasQuoteIssueRequestV2) -> dict:
    """발행 당시 가격 요청 사실 증거 (금액 없음)."""
    return {
        "product_tier": request.product_tier,
        "worker_capacity": request.worker_capacity,
        "payment_months": request.payment_months,
        "sites": [
            {
                "entity_id": str(s.entity_id),
                "sector": s.sector,
                "criteria_value": s.criteria_value,
            }
            for s in _canonical_sites(request)
        ],
    }


def _build_sectors(request: SaasQuoteIssueRequestV2):
    """(sector, sectors) — 단일 sector이면 sector=해당값, 복수면 None."""
    unique = sorted(set(s.sector for s in request.sites))
    sector = unique[0] if len(unique) == 1 else None
    return sector, unique


def _build_quote_item(
    snap: SaasPricingSnapshotV2,
    request: SaasQuoteIssueRequestV2,
) -> SaasQuoteSnapshotItemV2:
    """READY Snapshot → Frozen Composite Quote Item."""
    sector, sectors = _build_sectors(request)
    pricing_input = _build_pricing_input(request)
    snap_dict = snap.model_dump(mode="json")

    return SaasQuoteSnapshotItemV2(
        quote_schema_version=SAAS_QUOTE_SCHEMA_VERSION,
        display_name=_DISPLAY_NAMES[request.product_tier],
        billing_unit="MONTHLY",
        unit_amount=snap.monthly_supply_amount,
        quantity=snap.payment_months,
        supply_amount=snap.prepaid_supply_amount,
        vat_amount=snap.vat_amount,
        total_amount=snap.total_amount,
        service_type="SAAS",
        price_id=None,
        tier_code=None,
        sector=sector,
        sectors=sectors,
        product_tier=request.product_tier,
        pricing_mode=snap.pricing_mode,
        policy_version=snap.policy_version,
        worker_capacity=snap.worker.capacity,
        payment_months=snap.payment_months,
        vat_rate=snap.vat_rate_bps / 10000,
        vat_rate_bps=snap.vat_rate_bps,
        pricing_input=pricing_input,
        pricing_snapshot=snap_dict,
    )


# ── Gate Entry Point ──────────────────────────────────────────────────────────

def issue_saas_quote_v2(
    supabase,
    request: SaasQuoteIssueRequestV2,
    user_id: str,
    company_id: str,
) -> dict:
    """SaaS V2 자동견적 발행.

    DB Read: companies (company_name), price_master (via Preview V2)
    DB Write: quotes (1 row)
    Contract: 0. Payment: 0. Subscription: 0.
    """
    # ── Step 1: 회사명 스냅샷 ──────────────────────────────────────────
    company_name = member_quote_svc._company_name_snapshot(supabase, company_id)
    if not company_name:
        raise SaasQuoteV2Error(
            "COMPANY_SNAPSHOT_REQUIRED",
            "회사명을 확인할 수 없어 견적을 발행할 수 없습니다.",
        )

    # ── Step 1.5: Site Scope — 소유권·섹터·가격기준 Canonicalization ──
    canonical_sites = resolve_quote_site_scope_v2(supabase, company_id, request.sites)
    canonical_request = request.model_copy(update={"sites": canonical_sites})

    # ── Step 2: 서버 재가격계산 (Canonical Request 사용) ──────────────
    preview = preview_saas_price_v2(supabase, canonical_request)

    # ── Step 3: Pricing Status Gate ───────────────────────────────────
    if preview.status == "TERM_DISCOUNT_UNRESOLVED":
        raise SaasQuoteV2Error(
            "QUOTE_PRICING_NOT_READY",
            "기간할인율이 미확정 상태입니다. 자동견적을 발행할 수 없습니다.",
        )
    if preview.status == "CUSTOM_REQUIRED":
        raise SaasQuoteV2Error(
            "CUSTOM_QUOTE_REQUIRED",
            "맞춤 요금제는 자동견적 발행이 불가합니다. 별도견적을 요청해 주세요.",
        )
    if preview.status == "COMPLIANCE_BASE_QUOTE_REQUIRED":
        raise SaasQuoteV2Error(
            "COMPLIANCE_BASE_QUOTE_REQUIRED",
            "해당 사업장은 별도 기준가 확인이 필요합니다. 별도견적을 요청해 주세요.",
        )

    # ── Step 4: READY 검증 ────────────────────────────────────────────
    if preview.status != "READY":
        raise SaasQuoteV2Error(
            "QUOTE_SNAPSHOT_INVALID",
            f"예상하지 못한 Preview status: {preview.status}",
        )

    # ── Step 5: Calculation strict validation ─────────────────────────
    try:
        calc = SaasPricingCalculationResult.model_validate(preview.calculation)
    except (ValidationError, Exception) as exc:
        raise SaasQuoteV2Error("QUOTE_SNAPSHOT_INVALID", str(exc)) from exc

    if calc.status != "READY":
        raise SaasQuoteV2Error(
            "QUOTE_SNAPSHOT_INVALID",
            f"calculation.status=READY 아님: {calc.status}",
        )

    if calc.snapshot is None:
        raise SaasQuoteV2Error("QUOTE_SNAPSHOT_INVALID", "READY calculation의 snapshot이 None입니다.")

    snap: SaasPricingSnapshotV2 = calc.snapshot

    # ── Step 6: Snapshot ↔ Canonical Request 교차검증 ───────────────
    _validate_snapshot_against_request(snap, canonical_request)

    # ── Step 7: Frozen Composite Item 구성 (Canonical Request 기준) ──
    item = _build_quote_item(snap, canonical_request)

    # ── Step 8: Quote Row 구성 및 INSERT ─────────────────────────────
    now = now_kst().isoformat()
    base_row = {
        "company_id": company_id,
        "company_name": company_name,
        "created_by": user_id,
        "source": "member_auto",
        "status_code": "ISSUED",
        "contact_name": member_quote_svc.normalize_contact_name(request.contact_name),
        "service_type": "SAAS",
        "items": [item.model_dump(mode="json")],
        "supply_amount": snap.prepaid_supply_amount,
        "vat_amount": snap.vat_amount,
        "total_amount": snap.total_amount,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }

    return member_quote_svc._insert_quote_with_unique_retry(supabase, base_row)
