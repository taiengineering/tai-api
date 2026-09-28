"""TAI Safe SaaS Atomic Contract Apply V2 — RPC Adapter.

역할:
  SaasV2ApplyPlan을 apply_saas_v2_contract_atomic Postgres RPC
  1 call로 원자적으로 영구화한다.

금지:
  - Sequential Python-side DB INSERT/UPDATE (0)
  - apply_saas_v2_contract_atomic 외 RPC 호출 (0)
  - Python-side retry / partial rollback (0)
  - Router import (0)
  - Price engine import (0)

DB write = 0 (모든 write는 Postgres 함수 내부)
"""
from __future__ import annotations

from services.saas_payment_success_v2_adapter import SaasV2ApplyPlan


# ── Domain Error ──────────────────────────────────────────────────────────────

class SaasV2AtomicApplyError(Exception):
    """V2 Atomic Apply RPC 도메인 오류.

    code values:
      V2_RPC_ERROR            — supabase.rpc() 호출 자체 실패 또는 비정상 반환 타입
      V2_PAYMENT_NOT_FOUND    — 결제 행 없음
      V2_PAYMENT_NOT_PAID     — 결제 상태 미충족
      V2_ATOMIC_PARTIAL_STATE — 부분 적용 상태 탐지 (fail-closed, 3 경로)
      V2_CONTRACT_ID_MISMATCH — p_contract_row.id ≠ p_commercial_version.contract_id
      V2_VERSION_NO_INVALID   — commercial version_no ≠ 1
      V2_UNEXPECTED_STATUS    — RPC가 반환한 알 수 없는 status 코드
    """

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


# ── Terminal Status Codes ─────────────────────────────────────────────────────

_TERMINAL_STATUSES: frozenset[str] = frozenset({"APPLIED", "ALREADY_APPLIED"})


# ── Entry Point ───────────────────────────────────────────────────────────────

def apply_saas_v2_contract_plan_atomic(supabase, plan: SaasV2ApplyPlan) -> dict:
    """SaasV2ApplyPlan을 apply_saas_v2_contract_atomic RPC로 원자적으로 저장.

    DB write = 0 (Postgres 함수 내부에서 처리)
    RPC call = 1 (1 call = 1 transaction)

    Args:
      supabase  — service_role Supabase client (caller 제공)
      plan      — build_saas_v2_payment_success_apply_plan 반환값

    Returns:
      dict with 'status' in {'APPLIED', 'ALREADY_APPLIED'}

    Raises:
      SaasV2AtomicApplyError on any non-terminal status or RPC exception.
    """
    cv_dict = plan.commercial_bundle.commercial_version.model_dump(mode="json")
    scopes_list = [s.model_dump(mode="json") for s in plan.commercial_bundle.site_scopes]

    try:
        result = supabase.rpc(
            "apply_saas_v2_contract_atomic",
            {
                "p_payment_id":         str(plan.payment_id),
                "p_contract_row":       plan.contract_row,
                "p_commercial_version": cv_dict,
                "p_site_scopes":        scopes_list,
            },
        ).execute()
    except Exception as exc:
        raise SaasV2AtomicApplyError(
            "V2_RPC_ERROR",
            f"apply_saas_v2_contract_atomic RPC 호출 실패: {exc}",
        ) from exc

    data = result.data
    if not isinstance(data, dict):
        raise SaasV2AtomicApplyError(
            "V2_RPC_ERROR",
            f"RPC 반환값이 dict가 아닙니다: {type(data).__name__}",
        )

    status = data.get("status") or ""
    if status not in _TERMINAL_STATUSES:
        raise SaasV2AtomicApplyError(
            status or "V2_UNEXPECTED_STATUS",
            f"apply_saas_v2_contract_atomic 비정상 상태: {data}",
        )

    return data
