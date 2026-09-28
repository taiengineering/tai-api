"""TAI Safe SaaS Quote V2 — Schema 계약.

이 모듈은 데이터 구조와 validation 계약만 정의한다.
- DB I/O: 0
- 가격 계산: 0
- Runtime wiring: 0
- 클라이언트 입력 금지: company_id, created_by, source, status_code,
  pricing_mode, base_amount, base_band_code, supply_amount, vat_amount,
  total_amount, pricing_snapshot
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel

from schemas.saas_pricing_preview_v2 import SaasPricingPreviewRequestV2

SAAS_QUOTE_SCHEMA_VERSION = "SAAS_QUOTE_V2"

_DISPLAY_NAMES: dict[str, str] = {
    "MANAGER": "TAI Safe 관리자형",
    "FIELD": "TAI Safe 현장참여형",
}


# ── Issue Request ─────────────────────────────────────────────────────────────

class SaasQuoteIssueRequestV2(SaasPricingPreviewRequestV2):
    """SaaS V2 견적 발행 요청.

    extra=forbid 는 부모 SaasPricingPreviewRequestV2 에서 상속.
    가격 권위값 없음. company_id / created_by / source / status 없음.
    """

    contact_name: Optional[str] = None


# ── Quote Item ────────────────────────────────────────────────────────────────

class SaasQuoteSnapshotItemV2(BaseModel):
    """발행 당시 동결 Composite Item.

    - tier_code = None (Product Tier ≠ Compliance Base tier)
    - price_id = None (다중 price_master 합성)
    - PDF 호환 필수 필드 포함: display_name, billing_unit, unit_amount,
      quantity, supply_amount, vat_amount, total_amount
    """

    # Version
    quote_schema_version: str

    # PDF 호환 필수
    display_name: str
    billing_unit: str
    unit_amount: int
    quantity: int
    supply_amount: int
    vat_amount: int
    total_amount: int

    # V2 식별 및 분리
    service_type: str
    price_id: None
    tier_code: None

    # 사업장 Sector
    sector: Optional[str]
    sectors: List[str]

    # 상업적 파라미터
    product_tier: str
    pricing_mode: str
    policy_version: str
    worker_capacity: int
    term_months: int

    # VAT 호환
    vat_rate: float
    vat_rate_bps: int

    # 불변 증거
    pricing_input: dict
    pricing_snapshot: dict
