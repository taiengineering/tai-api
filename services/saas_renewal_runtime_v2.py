"""TAI Safe Pricing V2 — Renewal Runtime Branch Wiring (BE-OBJ10-D-B3).

역할:
  classify_renewal_runtime_route — V2 / LEGACY / INVALID / NOT_RENEWAL 분기 판정
  apply_saas_v2_renewal_runtime  — V2 Atomic Renewal 단일 RPC 파이프라인

핵심 invariant:
  ONE RENEWAL PAYMENT = EXACTLY ONE CONTRACT MUTATION PATH
  V2 경로 내부: _extend_contract_for_renewal call count = 0
  LEGACY 경로 내부: apply_saas_v2_renewal_runtime call count = 0

금지:
  - contracts UPDATE 직접
  - saas_contract_commercial_versions UPDATE / INSERT 직접
  - saas_contract_site_scopes INSERT 직접
  - datetime.now() 직접 호출
  - price_master / pricing composer 재계산
  - V2 실패 후 legacy fallback
  - 무한 retry loop

Imports from saas_renewal_v2_adapter / saas_renewal_atomic_apply_v2 / member_quote_svc:
  circular-import 방지를 위해 모두 lazy (함수 내부에서만 import).

Production mutation = 0 (B3 단계에서 실제 DB DDL / 배포 없음).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Routing Constants ─────────────────────────────────────────────────────────

_RENEWAL_TYPE = "RENEWAL"
_V2_PRODUCT_TYPE = "SAAS"

# Legacy allowlist — must stay in sync with payment_helpers.SAAS_PRODUCT_TYPES
_LEGACY_PRODUCT_TYPES = frozenset({
    "SAAS_CONSTRUCTION",
    "SAAS_INDUSTRY",
    "SAAS_FACILITY",
    "SAAS_BUILDING",
})

_PAID_STATUS_CODES = frozenset({"PAID", "SUCCESS"})


# ── Domain Error ──────────────────────────────────────────────────────────────

class SaasV2RenewalRuntimeError(Exception):
    """V2 Renewal Runtime domain error (fail-closed).

    Callers must NOT fall back to legacy extension on this error.

    code values:
      V2_RUNTIME_PAYMENT_INVALID          — payment field validation failure
      V2_RUNTIME_CONTRACT_NOT_FOUND       — contract_id not found
      V2_RUNTIME_CONTRACT_MISMATCH        — company_id mismatch
      V2_RUNTIME_CONTRACT_NOT_ACTIVE      — status_code != ACTIVE
      V2_RUNTIME_CONTRACT_NOT_SAAS        — service_type != SAAS
      V2_RUNTIME_END_DATE_REQUIRED        — contract.end_date IS NULL
      V2_RUNTIME_TARGET_AMBIGUOUS         — multiple CVs with same renewal_payment_id
      V2_RUNTIME_TARGET_CONTRACT_MISMATCH — target CV contract_id != pay.contract_id
      V2_RUNTIME_TARGET_VERSION_INVALID   — target CV version_no < 2 or parse error
      V2_RUNTIME_SOURCE_NOT_FOUND         — source CV (version_no-1) not found
      V2_RUNTIME_TEMPORAL_CURRENT_NOT_FOUND — no effective CV at paid_at
      V2_RUNTIME_TEMPORAL_CURRENT_AMBIGUOUS — multiple effective CVs at paid_at
      V2_RUNTIME_ROUTE_INVALID            — RENEWAL but unrecognized product_type
      V2_RUNTIME_CONTRACT_EXPIRED         — paid_at >= contract end boundary
    """

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


# ── Classifier ────────────────────────────────────────────────────────────────

def classify_renewal_runtime_route(pay: dict) -> str:
    """Map renewal payment to routing bucket.

    Returns one of:
      'V2'          — product_type=SAAS, payment_type=RENEWAL
      'LEGACY'      — product_type in legacy allowlist, payment_type=RENEWAL
      'INVALID'     — payment_type=RENEWAL, product_type not in any allowlist
      'NOT_RENEWAL' — payment_type != RENEWAL

    Note: This is a pure discriminator. It does NOT validate plan_code, quote_id,
    or other fields — those are V2 fail-closed guards inside apply_saas_v2_renewal_runtime.
    """
    if (pay.get("payment_type") or "").upper() != _RENEWAL_TYPE:
        return "NOT_RENEWAL"
    product = pay.get("product_type") or ""
    if product == _V2_PRODUCT_TYPE:
        return "V2"
    if product in _LEGACY_PRODUCT_TYPES:
        return "LEGACY"
    return "INVALID"


# ── V2 Runtime Entry ──────────────────────────────────────────────────────────

def apply_saas_v2_renewal_runtime(supabase, pay: dict) -> dict:
    """V2 Atomic Renewal Runtime — single B2 RPC pipeline.

    DB Read:  saas_contract_commercial_versions (target lookup + all CVs)
              contracts (first-apply path)
              quotes (via member_quote_svc)
    DB Write: single RPC only (via apply_saas_v2_renewal_plan_atomic)

    Returns:
        {'status': 'APPLIED', ...} or {'status': 'ALREADY_APPLIED', ...}

    Raises:
        SaasV2RenewalRuntimeError          — payment / contract validation failure
        SaasRenewalV2AdapterError          — plan build failure (propagated, not wrapped)
        SaasV2RenewalAtomicApplyError      — atomic RPC failure (propagated)

    Invariant:
        _extend_contract_for_renewal call count = 0 in this path.
        Max atomic RPC calls = 2 (normal + 1 race recovery).
        No unbounded retry loop.
    """
    _validate_v2_payment_guards(pay)
    payment_id = str(pay["id"])

    # ── Replay path: B2 UNIQUE invariant → at most 1 target CV ──────
    target_cv = _lookup_target_cv(supabase, payment_id)
    if target_cv is not None:
        logger.info("[B3-REPLAY] payment=%s target_version=%s",
                    payment_id, target_cv.get("version_no"))
        return _run_replay(supabase, pay, target_cv)

    # ── First apply path ────────────────────────────────────────────
    try:
        return _run_first_apply(supabase, pay)
    except Exception as first_exc:
        # One-time race recovery: peer callback may have committed between
        # our target lookup (none) and plan/RPC execution.
        recovered_target = _lookup_target_cv(supabase, payment_id)
        if recovered_target is not None:
            logger.info("[B3-RACE-RECOVER] payment=%s recovered_version=%s",
                        payment_id, recovered_target.get("version_no"))
            return _run_replay(supabase, pay, recovered_target)
        raise  # no target found — propagate original error


# ── Internal Helpers ──────────────────────────────────────────────────────────

def _validate_v2_payment_guards(pay: dict) -> None:
    """V2 fail-closed pre-checks.

    None of these failures fall back to legacy extension.
    """
    inv = "V2_RUNTIME_PAYMENT_INVALID"
    if (pay.get("payment_type") or "").upper() != _RENEWAL_TYPE:
        raise SaasV2RenewalRuntimeError(inv,
            f"payment_type must be RENEWAL: {pay.get('payment_type')!r}")
    if pay.get("product_type") != _V2_PRODUCT_TYPE:
        raise SaasV2RenewalRuntimeError(inv,
            f"product_type must be SAAS: {pay.get('product_type')!r}")
    if (pay.get("status_code") or "") not in _PAID_STATUS_CODES:
        raise SaasV2RenewalRuntimeError(inv,
            f"status_code must be PAID/SUCCESS: {pay.get('status_code')!r}")
    if pay.get("plan_code") is not None:
        raise SaasV2RenewalRuntimeError(inv,
            f"plan_code must be NULL for V2 renewal: {pay.get('plan_code')!r}")
    if not pay.get("contract_id"):
        raise SaasV2RenewalRuntimeError("V2_RUNTIME_CONTRACT_NOT_FOUND",
            "contract_id is required for V2 renewal.")
    if not pay.get("quote_id"):
        raise SaasV2RenewalRuntimeError(inv, "quote_id is required for V2 renewal.")
    if not pay.get("company_id"):
        raise SaasV2RenewalRuntimeError(inv, "company_id is required for V2 renewal.")
    if not pay.get("user_id"):
        raise SaasV2RenewalRuntimeError(inv, "user_id is required for V2 renewal.")
    if not pay.get("paid_at"):
        raise SaasV2RenewalRuntimeError(inv, "paid_at is required for V2 renewal.")


def _lookup_target_cv(supabase, payment_id: str) -> Optional[dict]:
    """Find CV with renewal_payment_id = payment_id.

    B2 UNIQUE index guarantees 0 or 1 rows.
    """
    res = (
        supabase.table("saas_contract_commercial_versions")
        .select("*")
        .eq("renewal_payment_id", payment_id)
        .execute()
    )
    rows = res.data or []
    if not rows:
        return None
    if len(rows) > 1:
        raise SaasV2RenewalRuntimeError(
            "V2_RUNTIME_TARGET_AMBIGUOUS",
            f"Multiple CVs with renewal_payment_id={payment_id}: count={len(rows)}",
        )
    return rows[0]


def _parse_dt_aware(raw, field_name: str) -> datetime:
    """Parse ISO string or datetime to timezone-aware datetime."""
    from dateutil import parser as dateutil_parser

    if isinstance(raw, datetime):
        dt = raw
    elif isinstance(raw, str):
        try:
            dt = dateutil_parser.isoparse(raw)
        except Exception as exc:
            raise SaasV2RenewalRuntimeError(
                "V2_RUNTIME_TARGET_VERSION_INVALID",
                f"{field_name} parse failed: {raw!r}",
            ) from exc
    else:
        raise SaasV2RenewalRuntimeError(
            "V2_RUNTIME_TARGET_VERSION_INVALID",
            f"{field_name} unexpected type: {type(raw)!r}",
        )
    if dt.tzinfo is None:
        raise SaasV2RenewalRuntimeError(
            "V2_RUNTIME_TARGET_VERSION_INVALID",
            f"{field_name} must be timezone-aware: {raw!r}",
        )
    return dt


def _run_replay(supabase, pay: dict, target_cv: dict) -> dict:
    """Replay path: target CV already exists for this payment.

    Boundary = target.effective_from  (NOT contract.end_date — prevents double extension).
    Source    = CV with version_no = target.version_no - 1.
    """
    target_contract_id = str(target_cv.get("contract_id") or "")
    pay_contract_id = str(pay.get("contract_id") or "")
    if target_contract_id != pay_contract_id:
        raise SaasV2RenewalRuntimeError(
            "V2_RUNTIME_TARGET_CONTRACT_MISMATCH",
            f"target CV contract_id={target_contract_id} != pay contract_id={pay_contract_id}",
        )

    target_version_no = target_cv.get("version_no")
    if not isinstance(target_version_no, int) or target_version_no < 2:
        raise SaasV2RenewalRuntimeError(
            "V2_RUNTIME_TARGET_VERSION_INVALID",
            f"target CV version_no={target_version_no}: must be integer >= 2",
        )

    source_version_no = target_version_no - 1
    src_res = (
        supabase.table("saas_contract_commercial_versions")
        .select("*")
        .eq("contract_id", pay_contract_id)
        .eq("version_no", source_version_no)
        .limit(1)
        .execute()
    )
    src_rows = src_res.data or []
    if not src_rows:
        raise SaasV2RenewalRuntimeError(
            "V2_RUNTIME_SOURCE_NOT_FOUND",
            f"Source CV not found: contract={pay_contract_id}, version_no={source_version_no}",
        )

    requested_effective_at = _parse_dt_aware(
        target_cv.get("effective_from"), "target CV effective_from"
    )
    return _build_and_apply(supabase, pay, src_rows[0], requested_effective_at)


def _run_first_apply(supabase, pay: dict) -> dict:
    """First apply path: derive boundary from contract.end_date (KST midnight)."""
    from dateutil import parser as dateutil_parser
    from services.saas_commercial_version_time_v2 import (
        TemporalVersionError,
        contract_end_date_to_effective_at_v2,
        select_effective_commercial_version_v2,
    )

    contract_id = str(pay["contract_id"])
    company_id = str(pay["company_id"])

    # Contract read
    ct_res = (
        supabase.table("contracts")
        .select("id, company_id, status_code, service_type, end_date")
        .eq("id", contract_id)
        .limit(1)
        .execute()
    )
    ct_rows = ct_res.data or []
    if not ct_rows:
        raise SaasV2RenewalRuntimeError(
            "V2_RUNTIME_CONTRACT_NOT_FOUND",
            f"contract_id={contract_id} not found.",
        )
    contract = ct_rows[0]

    if str(contract.get("company_id") or "") != company_id:
        raise SaasV2RenewalRuntimeError(
            "V2_RUNTIME_CONTRACT_MISMATCH",
            f"contract.company_id={contract.get('company_id')} != pay.company_id={company_id}",
        )
    if contract.get("status_code") != "ACTIVE":
        raise SaasV2RenewalRuntimeError(
            "V2_RUNTIME_CONTRACT_NOT_ACTIVE",
            f"contract status_code={contract.get('status_code')!r}: must be ACTIVE",
        )
    if contract.get("service_type") != "SAAS":
        raise SaasV2RenewalRuntimeError(
            "V2_RUNTIME_CONTRACT_NOT_SAAS",
            f"contract service_type={contract.get('service_type')!r}: must be SAAS",
        )
    if not contract.get("end_date"):
        raise SaasV2RenewalRuntimeError(
            "V2_RUNTIME_END_DATE_REQUIRED",
            "contract.end_date is required for V2 renewal.",
        )

    # Parse paid_at (timezone-aware required)
    paid_at_str = str(pay["paid_at"])
    try:
        paid_at_dt = dateutil_parser.isoparse(paid_at_str)
    except Exception as exc:
        raise SaasV2RenewalRuntimeError(
            "V2_RUNTIME_PAYMENT_INVALID",
            f"paid_at parse failed: {paid_at_str!r}",
        ) from exc
    if paid_at_dt.tzinfo is None:
        raise SaasV2RenewalRuntimeError(
            "V2_RUNTIME_PAYMENT_INVALID",
            f"paid_at must be timezone-aware: {paid_at_str!r}",
        )

    # D-01: Temporal expiration guard — paid_at must be before contract end boundary
    contract_end_boundary = contract_end_date_to_effective_at_v2(
        contract["end_date"]
    )
    if paid_at_dt >= contract_end_boundary:
        raise SaasV2RenewalRuntimeError(
            "V2_RUNTIME_CONTRACT_EXPIRED",
            f"Renewal rejected: paid_at {paid_at_dt.isoformat()} >= contract end boundary {contract_end_boundary.isoformat()}",
        )

    # All CVs for this contract
    all_cv_res = (
        supabase.table("saas_contract_commercial_versions")
        .select("*")
        .eq("contract_id", contract_id)
        .execute()
    )
    all_cvs = all_cv_res.data or []

    # Temporal current selection — exactly 1 required (fail-closed on 0 or 2+)
    try:
        source_cv = select_effective_commercial_version_v2(all_cvs, paid_at_dt)
    except TemporalVersionError as exc:
        if exc.code == "TEMPORAL_CURRENT_NOT_FOUND":
            raise SaasV2RenewalRuntimeError(
                "V2_RUNTIME_TEMPORAL_CURRENT_NOT_FOUND",
                f"No effective CV at paid_at={paid_at_dt}: {exc}",
            ) from exc
        if exc.code == "TEMPORAL_CURRENT_AMBIGUOUS":
            raise SaasV2RenewalRuntimeError(
                "V2_RUNTIME_TEMPORAL_CURRENT_AMBIGUOUS",
                f"Ambiguous effective CVs at paid_at={paid_at_dt}: {exc}",
            ) from exc
        raise

    # Boundary: contract.end_date → Asia/Seoul 00:00 (reuse D-01 computed value)
    requested_effective_at = contract_end_boundary
    return _build_and_apply(supabase, pay, source_cv, requested_effective_at)


def _build_and_apply(supabase, pay: dict, source_cv: dict,
                     requested_effective_at: datetime) -> dict:
    """Load frozen quote → build apply plan → call B2 atomic RPC.

    DB Write: 0 here — all mutations inside apply_saas_v2_renewal_plan_atomic.
    """
    # Lazy imports: saas_renewal_v2_adapter → payment_post_process (PAID_STATUS_CODES)
    # Importing here (inside function) avoids circular import at module load time.
    import services.member_quote_svc as member_quote_svc
    from services.saas_renewal_v2_adapter import build_saas_v2_renewal_apply_plan
    from services.saas_renewal_atomic_apply_v2 import apply_saas_v2_renewal_plan_atomic

    quote = member_quote_svc.get_member_quote(supabase, str(pay["quote_id"]))
    if not quote:
        raise SaasV2RenewalRuntimeError(
            "V2_RUNTIME_PAYMENT_INVALID",
            f"quote not found: quote_id={pay['quote_id']}",
        )

    plan = build_saas_v2_renewal_apply_plan(
        pay,
        quote=quote,
        current_cv=source_cv,
        requested_effective_at=requested_effective_at,
    )
    return apply_saas_v2_renewal_plan_atomic(supabase, plan)
