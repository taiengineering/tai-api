"""TAI Safe SaaS Entitlement Gate V2 — Pure Product Entitlement Domain Gate.

판정 대상:
  현재 Product Tier에서 요청한 SaaS 기능을 사용할 권한이 있는가?

금지:
  - DB I/O
  - Commercial Fit / Site Scope / Worker Capacity 판정
  - 가격 계산 (amount / VAT / payment)
  - plan_code / contract_level / tier sort_order 의존
  - V1 tier_payment_gate_svc 의존
  - datetime.now() 직접 호출
  - Router wiring
  - CUSTOM 자동 전체허용
"""
from __future__ import annotations

from typing import List, Set

from schemas.saas_entitlement_v2 import (
    ENTITLEMENT_CANONICAL_ORDER,
    SaasEntitlementBatchDecisionV2,
    SaasEntitlementCode,
    SaasEntitlementContextV2,
    SaasEntitlementDecisionV2,
)

# ── Canonical Tier Entitlement Sets ──────────────────────────────────────────

MANAGER_ENTITLEMENTS: tuple[SaasEntitlementCode, ...] = (
    "COMPLIANCE_CORE",
)

_FIELD_SPECIFIC: tuple[SaasEntitlementCode, ...] = (
    "FIELD_TBM",
    "FIELD_RA",
    "FIELD_INSPECTION",
    "FIELD_SIGN",
    "FIELD_HAZARD_REPORT",
)

FIELD_ENTITLEMENTS: tuple[SaasEntitlementCode, ...] = (
    *MANAGER_ENTITLEMENTS,
    *_FIELD_SPECIFIC,
)

_MANAGER_SET: frozenset[SaasEntitlementCode] = frozenset(MANAGER_ENTITLEMENTS)
_FIELD_SET: frozenset[SaasEntitlementCode] = frozenset(FIELD_ENTITLEMENTS)

_CANONICAL_ORDER_INDEX = {code: i for i, code in enumerate(ENTITLEMENT_CANONICAL_ORDER)}


# ── Gate Error ────────────────────────────────────────────────────────────────

class SaasEntitlementGateError(Exception):
    """Entitlement Gate domain invariant violation.

    code values:
      DUPLICATE_REQUESTED_ENTITLEMENT
    """

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


# ── Internal Helpers ──────────────────────────────────────────────────────────

def _canonical_sorted(codes: frozenset[SaasEntitlementCode]) -> List[SaasEntitlementCode]:
    return sorted(codes, key=lambda c: _CANONICAL_ORDER_INDEX[c])


def _resolve_effective(context: SaasEntitlementContextV2) -> List[SaasEntitlementCode]:
    if context.product_tier == "MANAGER":
        return list(MANAGER_ENTITLEMENTS)
    if context.product_tier == "FIELD":
        return list(FIELD_ENTITLEMENTS)
    # CUSTOM
    if context.custom_entitlements is None:
        return []
    return _canonical_sorted(frozenset(context.custom_entitlements))


# ── Public API ────────────────────────────────────────────────────────────────

def resolve_effective_entitlements_v2(
    context: SaasEntitlementContextV2,
) -> List[SaasEntitlementCode]:
    """Tier에 대한 effective entitlement set을 canonical order로 반환.

    CUSTOM + None → [] (context unresolved indication)
    """
    return _resolve_effective(context)


def evaluate_saas_entitlement_v2(
    context: SaasEntitlementContextV2,
    requested_entitlement: SaasEntitlementCode,
) -> SaasEntitlementDecisionV2:
    """단일 Entitlement 판정."""
    effective = _resolve_effective(context)

    if context.product_tier == "CUSTOM" and context.custom_entitlements is None:
        status = "CUSTOM_CONTEXT_REQUIRED"
    elif requested_entitlement in effective:
        status = "ALLOWED"
    else:
        status = "DENIED"

    return SaasEntitlementDecisionV2(
        product_tier=context.product_tier,
        requested_entitlement=requested_entitlement,
        status=status,
        effective_entitlements=effective,
    )


def evaluate_saas_entitlements_v2(
    context: SaasEntitlementContextV2,
    requested_entitlements: List[SaasEntitlementCode],
) -> SaasEntitlementBatchDecisionV2:
    """복수 Entitlement 판정. 입력 순서와 무관하게 canonical order로 결과 반환."""
    seen: Set[SaasEntitlementCode] = set()
    for code in requested_entitlements:
        if code in seen:
            raise SaasEntitlementGateError(
                "DUPLICATE_REQUESTED_ENTITLEMENT",
                f"요청 Entitlement 중복: {code}",
            )
        seen.add(code)

    effective = _resolve_effective(context)
    canonical_requested = _canonical_sorted(frozenset(requested_entitlements))

    decisions: List[SaasEntitlementDecisionV2] = []
    for code in canonical_requested:
        if context.product_tier == "CUSTOM" and context.custom_entitlements is None:
            status = "CUSTOM_CONTEXT_REQUIRED"
        elif code in effective:
            status = "ALLOWED"
        else:
            status = "DENIED"

        decisions.append(SaasEntitlementDecisionV2(
            product_tier=context.product_tier,
            requested_entitlement=code,
            status=status,
            effective_entitlements=effective,
        ))

    return SaasEntitlementBatchDecisionV2(
        product_tier=context.product_tier,
        decisions=decisions,
        effective_entitlements=effective,
    )
