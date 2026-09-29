"""TAI Safe SaaS Entitlement Runtime V2 — DB → Entitlement Decision.

역할:
  company_id + as_of
  → ACTIVE SaaS contracts 조회 (service_type=SAAS, status_code=ACTIVE, is_active=true)
  → 단일 contract 확인
  → saas_contract_commercial_versions 전체 조회
  → select_effective_commercial_version_v2() → 현재 CV
  → product_tier → SaasEntitlementContextV2
  → evaluate_saas_entitlement_v2()

금지:
  - plan_code 사용
  - contract_level 사용
  - price_master 사용
  - Commercial Fit 호출
  - 가격 계산 / 결제
  - Router wiring
  - LEG router 수정
  - DDL / migration / production write
  - datetime.now() 직접 호출
  - superseded_at IS NULL LIMIT 1 shortcut
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List

from schemas.saas_entitlement_v2 import (
    SaasEntitlementCode,
    SaasEntitlementContextV2,
    SaasEntitlementDecisionV2,
)
from services.saas_commercial_version_time_v2 import (
    TemporalVersionError,
    select_effective_commercial_version_v2,
)
from services.saas_entitlement_gate_v2 import evaluate_saas_entitlement_v2


# ── Domain Error ──────────────────────────────────────────────────────────────

class SaasEntitlementRuntimeError(Exception):
    """Entitlement Runtime domain error (fail-closed).

    code values:
      NO_ACTIVE_SAAS_CONTRACT        — company_id에 활성 SaaS 계약 없음
      AMBIGUOUS_ACTIVE_SAAS_CONTRACT — 활성 SaaS 계약 2건 이상
      CURRENT_CV_NOT_FOUND           — as_of 시점 effective CV 없음
      CURRENT_CV_AMBIGUOUS           — as_of 시점 effective CV 2건 이상
      CURRENT_CV_SCHEMA_INVALID      — CV product_tier 필드 파싱 불가
    """

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


# ── Resolution Result ─────────────────────────────────────────────────────────

@dataclass
class SaasEntitlementResolutionV2:
    """Runtime DB 조회 + temporal 선택 결과.

    Fields:
      contract_id           — ACTIVE SaaS 계약 id
      commercial_version_no — as_of 시점 effective CV version_no
      product_tier          — CV.product_tier ("MANAGER" | "FIELD" | "CUSTOM")
      context               — Entitlement Domain Gate 입력 컨텍스트
    """
    contract_id: str
    commercial_version_no: int
    product_tier: str
    context: SaasEntitlementContextV2


@dataclass
class SaasEntitlementRuntimeDecisionV2:
    """Runtime 전체 판정 결과.

    Fields:
      contract_id           — ACTIVE SaaS 계약 id
      commercial_version_no — as_of 시점 effective CV version_no
      product_tier          — CV.product_tier
      decision              — Entitlement Domain Gate 판정 결과
    """
    contract_id: str
    commercial_version_no: int
    product_tier: str
    decision: SaasEntitlementDecisionV2


# ── Internal ──────────────────────────────────────────────────────────────────

_VALID_PRODUCT_TIERS = frozenset({"MANAGER", "FIELD", "CUSTOM"})


def _get(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _fetch_active_saas_contracts(supabase, company_id: str) -> List[dict]:
    res = (
        supabase.table("contracts")
        .select("id, company_id, service_type, status_code")
        .eq("company_id", company_id)
        .eq("service_type", "SAAS")
        .eq("status_code", "ACTIVE")
        .eq("is_active", True)
        .execute()
    )
    return res.data or []


def _fetch_all_cvs(supabase, contract_id: str) -> List[dict]:
    res = (
        supabase.table("saas_contract_commercial_versions")
        .select("*")
        .eq("contract_id", contract_id)
        .execute()
    )
    return res.data or []


def _context_from_cv(cv: Any) -> SaasEntitlementContextV2:
    """CV → SaasEntitlementContextV2. CUSTOM → custom_entitlements=None (fail-closed)."""
    product_tier = _get(cv, "product_tier")
    if product_tier not in _VALID_PRODUCT_TIERS:
        raise SaasEntitlementRuntimeError(
            "CURRENT_CV_SCHEMA_INVALID",
            f"CV product_tier 파싱 불가: {product_tier!r}",
        )
    return SaasEntitlementContextV2(product_tier=product_tier, custom_entitlements=None)


# ── Public Functions ──────────────────────────────────────────────────────────

def resolve_saas_entitlement_context_v2(
    supabase,
    company_id: str,
    as_of: datetime,
) -> SaasEntitlementResolutionV2:
    """company_id + as_of → SaasEntitlementResolutionV2 (DB Read only).

    DB Read:  contracts (ACTIVE SaaS) + saas_contract_commercial_versions
    DB Write: 0

    Raises:
      SaasEntitlementRuntimeError(NO_ACTIVE_SAAS_CONTRACT)
      SaasEntitlementRuntimeError(AMBIGUOUS_ACTIVE_SAAS_CONTRACT)
      SaasEntitlementRuntimeError(CURRENT_CV_NOT_FOUND)
      SaasEntitlementRuntimeError(CURRENT_CV_AMBIGUOUS)
      SaasEntitlementRuntimeError(CURRENT_CV_SCHEMA_INVALID)
    """
    # Step 1: ACTIVE SaaS contract — exactly 1
    contracts = _fetch_active_saas_contracts(supabase, company_id)
    if not contracts:
        raise SaasEntitlementRuntimeError(
            "NO_ACTIVE_SAAS_CONTRACT",
            f"company_id={company_id}에 활성 SaaS 계약 없음",
        )
    if len(contracts) > 1:
        raise SaasEntitlementRuntimeError(
            "AMBIGUOUS_ACTIVE_SAAS_CONTRACT",
            f"company_id={company_id} 활성 SaaS 계약 {len(contracts)}건 — 중복 불허",
        )
    contract_id = str(_get(contracts[0], "id") or "")

    # Step 2: All CVs — full sequence (no shortcut)
    all_cvs = _fetch_all_cvs(supabase, contract_id)

    # Step 3: Temporal selection — canonical, exactly 1
    try:
        current_cv = select_effective_commercial_version_v2(all_cvs, as_of)
    except TemporalVersionError as exc:
        if exc.code == "TEMPORAL_CURRENT_NOT_FOUND":
            raise SaasEntitlementRuntimeError(
                "CURRENT_CV_NOT_FOUND",
                f"as_of={as_of} 시점 effective CV 없음: {exc}",
            ) from exc
        raise SaasEntitlementRuntimeError(
            "CURRENT_CV_AMBIGUOUS",
            f"as_of={as_of} 시점 effective CV 중복: {exc}",
        ) from exc

    # Step 4: product_tier → context (CUSTOM → fail-closed sentinel)
    context = _context_from_cv(current_cv)
    version_no = int(_get(current_cv, "version_no") or 0)

    return SaasEntitlementResolutionV2(
        contract_id=contract_id,
        commercial_version_no=version_no,
        product_tier=context.product_tier,
        context=context,
    )


def evaluate_saas_entitlement_runtime_v2(
    supabase,
    company_id: str,
    as_of: datetime,
    requested_entitlement: SaasEntitlementCode,
) -> SaasEntitlementRuntimeDecisionV2:
    """company_id + as_of + requested_entitlement → Runtime Entitlement Decision.

    DB Read:  contracts + saas_contract_commercial_versions
    DB Write: 0

    Raises:
      SaasEntitlementRuntimeError — contract / CV 조회 실패
    """
    resolution = resolve_saas_entitlement_context_v2(supabase, company_id, as_of)
    decision = evaluate_saas_entitlement_v2(resolution.context, requested_entitlement)

    return SaasEntitlementRuntimeDecisionV2(
        contract_id=resolution.contract_id,
        commercial_version_no=resolution.commercial_version_no,
        product_tier=resolution.product_tier,
        decision=decision,
    )
