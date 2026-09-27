"""TAI Safe SaaS Entitlement V2 — Input/Output Contract.

이 모듈은 데이터 구조와 validation 계약만 정의한다.
- DB I/O: 0
- 가격 계산: 0
- Commercial Fit: 0
- Runtime wiring: 0
"""
from __future__ import annotations

from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator

from schemas.saas_pricing_v2 import ProductTier

# ── Canonical Type Definitions ────────────────────────────────────────────────

SaasEntitlementCode = Literal[
    "COMPLIANCE_CORE",
    "FIELD_TBM",
    "FIELD_RA",
    "FIELD_INSPECTION",
    "FIELD_SIGN",
    "FIELD_HAZARD_REPORT",
]

SaasEntitlementDecisionStatus = Literal[
    "ALLOWED",
    "DENIED",
    "CUSTOM_CONTEXT_REQUIRED",
]

# Canonical entitlement order — 정렬 기준
ENTITLEMENT_CANONICAL_ORDER: List[SaasEntitlementCode] = [
    "COMPLIANCE_CORE",
    "FIELD_TBM",
    "FIELD_RA",
    "FIELD_INSPECTION",
    "FIELD_SIGN",
    "FIELD_HAZARD_REPORT",
]


# ── Input: Entitlement Context ────────────────────────────────────────────────

class SaasEntitlementContextV2(BaseModel):
    """Product Tier + CUSTOM 계약별 explicit 권한 목록."""

    product_tier: ProductTier
    custom_entitlements: Optional[List[SaasEntitlementCode]] = None

    @model_validator(mode="after")
    def _validate_context(self) -> "SaasEntitlementContextV2":
        if self.product_tier in ("MANAGER", "FIELD"):
            if self.custom_entitlements is not None:
                raise ValueError(
                    f"product_tier={self.product_tier}에는 custom_entitlements를 설정할 수 없습니다."
                )
        if self.product_tier == "CUSTOM" and self.custom_entitlements is not None:
            seen: set = set()
            for code in self.custom_entitlements:
                if code in seen:
                    raise ValueError(
                        f"custom_entitlements 중복: {code}"
                    )
                seen.add(code)
        return self


# ── Output: Single Entitlement Decision ──────────────────────────────────────

class SaasEntitlementDecisionV2(BaseModel):
    """단일 Entitlement 판정 결과."""

    product_tier: ProductTier
    requested_entitlement: SaasEntitlementCode
    status: SaasEntitlementDecisionStatus
    effective_entitlements: List[SaasEntitlementCode]


# ── Output: Batch Entitlement Decision ───────────────────────────────────────

class SaasEntitlementBatchDecisionV2(BaseModel):
    """복수 Entitlement 판정 결과."""

    product_tier: ProductTier
    decisions: List[SaasEntitlementDecisionV2]
    effective_entitlements: List[SaasEntitlementCode]
