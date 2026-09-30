"""TAI Safe SaaS Initial Payment V2 Runtime — Frozen Quote → Atomic Contract.

역할: product_type=SAAS 초기 결제 성공 후 Frozen Quote → apply plan → Atomic RPC.
Replay: payment.contract_id 존재 → same UUID override → ALREADY_APPLIED.
Race recovery: V2_CONTRACT_ID_MISMATCH + peer-stored contract_id 존재 → 1회 재시도.

금지:
  - _create_contract_from_payment 호출
  - _activate_existing_contract 호출
  - _expire_other_active_contracts 호출
  - contracts/commercial_versions/site_scopes Python INSERT/UPDATE
  - 가격 재계산
  - V2_CONTRACT_ID_MISMATCH 외 validation error retry
  - atomic RPC 3회 이상 호출
"""
from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Optional

import services.member_quote_svc as member_quote_svc
from services.payment_post_process import PAID_STATUS_CODES, _gen_contract_no
from services.saas_contract_atomic_apply_v2 import (
    SaasV2AtomicApplyError,
    apply_saas_v2_contract_plan_atomic,
)
from services.saas_payment_success_v2_adapter import (
    SaasPaymentSuccessV2AdapterError,
    build_saas_v2_payment_success_apply_plan,
)
from services.time import business_today

logger = logging.getLogger(__name__)

_RACE_RECOVERY_CODE = "V2_CONTRACT_ID_MISMATCH"


class SaasInitialPaymentRuntimeV2Error(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


def _load_quote(sb, pay: dict) -> dict:
    quote_id = pay.get("quote_id")
    if not quote_id:
        raise SaasInitialPaymentRuntimeV2Error(
            "V2_INIT_NO_QUOTE_ID",
            "product_type=SAAS 초기 결제에 quote_id가 없습니다.",
        )
    quote = member_quote_svc.get_member_quote(sb, str(quote_id))
    if not quote:
        raise SaasInitialPaymentRuntimeV2Error(
            "V2_INIT_QUOTE_NOT_FOUND",
            f"견적을 찾을 수 없습니다: {quote_id}",
        )
    return quote


def _build_plan(sb, pay: dict, quote: dict, contract_id_override: Optional[uuid.UUID]):
    start: date = business_today()
    return build_saas_v2_payment_success_apply_plan(
        pay,
        quote=quote,
        start=start,
        contract_no=_gen_contract_no(),
        contract_id_override=contract_id_override,
    )


def apply_saas_v2_initial_payment_runtime(sb, pay: dict) -> dict:
    """SAAS 초기 결제 → Atomic Contract 영구화.

    Returns dict with 'status' in {'APPLIED', 'ALREADY_APPLIED'}.
    Fail-closed: validation error → raise (legacy fallback 진입 금지).
    """
    payment_id = str(pay.get("id") or "")

    if pay.get("plan_code") is not None:
        raise SaasInitialPaymentRuntimeV2Error(
            "V2_INIT_PLAN_CODE_FORBIDDEN",
            f"product_type=SAAS 초기 결제는 plan_code=None 필수: {pay.get('plan_code')!r}",
        )

    quote = _load_quote(sb, pay)

    # Replay: use stored contract_id as override
    existing_cid: Optional[uuid.UUID] = None
    stored = pay.get("contract_id")
    if stored:
        try:
            existing_cid = uuid.UUID(str(stored))
        except (ValueError, AttributeError):
            logger.warning("[V2_INIT] payment=%s invalid stored contract_id=%r", payment_id, stored)

    plan = _build_plan(sb, pay, quote, contract_id_override=existing_cid)

    # First atomic call
    try:
        result = apply_saas_v2_contract_plan_atomic(sb, plan)
        logger.info("[V2_INIT] payment=%s contract=%s atomic_calls=1 status=%s",
                    payment_id, plan.contract_id, result.get("status"))
        return result
    except SaasV2AtomicApplyError as exc:
        if exc.code != _RACE_RECOVERY_CODE:
            logger.error("[V2_INIT] payment=%s atomic_error=%s (no retry)", payment_id, exc.code)
            raise SaasInitialPaymentRuntimeV2Error(exc.code, exc.message) from exc

        # Race recovery: re-fetch payment.contract_id
        try:
            pay_res = sb.table("payments").select("contract_id").eq("id", payment_id).limit(1).execute()
            refetched_cid_raw = (pay_res.data[0].get("contract_id") if pay_res.data else None)
        except Exception as refetch_exc:
            logger.error("[V2_INIT] payment=%s race-refetch failed: %s", payment_id, refetch_exc)
            raise SaasInitialPaymentRuntimeV2Error(exc.code, exc.message) from exc

        if not refetched_cid_raw:
            logger.error("[V2_INIT] payment=%s MISMATCH but no peer contract_id — no retry", payment_id)
            raise SaasInitialPaymentRuntimeV2Error(exc.code, exc.message) from exc

        try:
            peer_cid = uuid.UUID(str(refetched_cid_raw))
        except (ValueError, AttributeError):
            logger.error("[V2_INIT] payment=%s refetched cid invalid UUID: %r", payment_id, refetched_cid_raw)
            raise SaasInitialPaymentRuntimeV2Error(exc.code, exc.message) from exc

        logger.info("[V2_INIT] payment=%s race-recovery peer_contract=%s rebuild+retry", payment_id, peer_cid)
        recovery_plan = _build_plan(sb, pay, quote, contract_id_override=peer_cid)

        # Second (final) atomic call
        try:
            result = apply_saas_v2_contract_plan_atomic(sb, recovery_plan)
            logger.info("[V2_INIT] payment=%s contract=%s atomic_calls=2 status=%s",
                        payment_id, recovery_plan.contract_id, result.get("status"))
            return result
        except SaasV2AtomicApplyError as exc2:
            logger.error("[V2_INIT] payment=%s recovery-atomic-error=%s (no third retry)", payment_id, exc2.code)
            raise SaasInitialPaymentRuntimeV2Error(exc2.code, exc2.message) from exc2
