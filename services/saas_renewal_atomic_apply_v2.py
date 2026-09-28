"""TAI Safe Pricing V2 — Atomic Prepaid Renewal Persistence Adapter (BE-OBJ10-D-B2).

역할: SaasV2RenewalApplyPlan → 단일 RPC → apply_saas_v2_renewal_atomic.

금지:
  - 직접 table INSERT/UPDATE
  - retry loop
  - pricing 계산
  - datetime.now() 직접 호출
  - contract 날짜 계산
  - legacy renewal helper
  - post-process import

Runtime wiring: DEFERRED_TO_B3
"""
from __future__ import annotations

import json
from typing import Any

from services.saas_renewal_v2_adapter import SaasV2RenewalApplyPlan

_RPC_NAME = "apply_saas_v2_renewal_atomic"

_SUCCESS_STATUSES = frozenset({"APPLIED", "ALREADY_APPLIED"})


class SaasV2RenewalAtomicApplyError(Exception):
    """apply_saas_v2_renewal_plan_atomic failure.

    Attributes:
        code     — RPC 반환 status 코드 또는 'V2_RENEWAL_RPC_ERROR'
        payload  — RPC 반환 full jsonb (가능한 경우)
    """
    def __init__(self, code: str, message: str = "", payload: Any = None) -> None:
        self.code = code
        self.message = message or code
        self.payload = payload
        super().__init__(message or code)


def _serialize_cv(plan: SaasV2RenewalApplyPlan) -> dict:
    """SaasContractCommercialVersionV2 → RPC-safe dict."""
    cv = plan.commercial_bundle.commercial_version
    return cv.model_dump(mode="json")


def _serialize_scopes(plan: SaasV2RenewalApplyPlan) -> list:
    """List[SaasContractSiteScopeV2] → RPC-safe list of dicts."""
    return [scope.model_dump(mode="json") for scope in plan.commercial_bundle.site_scopes]


def apply_saas_v2_renewal_plan_atomic(
    supabase,
    plan: SaasV2RenewalApplyPlan,
) -> dict:
    """SaasV2RenewalApplyPlan을 단일 RPC로 원자 적용한다.

    DB write (via RPC):
      commercial_versions: superseded_at UPDATE 1, INSERT 1
      site_scopes: INSERT N
      contracts: end_date/paid_amount/paid_at/updated_at UPDATE 1
      payments: 0

    Returns:
      {'status': 'APPLIED', ...} or {'status': 'ALREADY_APPLIED', ...}

    Raises:
      SaasV2RenewalAtomicApplyError — status ∉ {APPLIED, ALREADY_APPLIED}
                                      or RPC exception
    """
    cv_payload = _serialize_cv(plan)
    scopes_payload = _serialize_scopes(plan)

    try:
        response = (
            supabase.rpc(
                _RPC_NAME,
                {
                    "p_payment_id":             str(plan.payment_id),
                    "p_contract_id":             str(plan.contract_id),
                    "p_quote_id":                str(plan.quote_id),
                    "p_current_version_no":      plan.current_version_no,
                    "p_new_commercial_version":  cv_payload,
                    "p_site_scopes":             scopes_payload,
                },
            )
            .execute()
        )
    except Exception as exc:
        raise SaasV2RenewalAtomicApplyError(
            "V2_RENEWAL_RPC_ERROR",
            f"RPC {_RPC_NAME} 호출 실패: {exc}",
        ) from exc

    result = response.data
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (ValueError, TypeError):
            raise SaasV2RenewalAtomicApplyError(
                "V2_RENEWAL_RPC_ERROR",
                f"RPC 응답 파싱 실패: {result!r}",
                payload=result,
            )

    if not isinstance(result, dict):
        raise SaasV2RenewalAtomicApplyError(
            "V2_RENEWAL_RPC_ERROR",
            f"RPC 응답이 dict가 아님: {type(result).__name__}",
            payload=result,
        )

    status = result.get("status", "")
    if status not in _SUCCESS_STATUSES:
        raise SaasV2RenewalAtomicApplyError(
            status,
            f"RPC {_RPC_NAME} returned non-success status: {status}",
            payload=result,
        )

    return result
