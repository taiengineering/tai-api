"""자동 세금계산서 오케스트레이터 (WO-TAX-INVOICE-AUTO-01 STEP 2).

역할: 얇은 helper — 재사용 앵커만 조립.
  1) payment authoritative read
  2) evaluate_eligibility(sb, payment)  ← 기존
  3) create_request(sb, system_user, payment, source=AUTO_PAYMENT)  ← 기존 (멱등)
  4) process_tax_invoice_request(sb, request_id, supply_date, actor)  ← 기존 processor

금지: 새 발행/새 eligibility/새 세액계산/Popbill 직접호출/새 lock/새 재시도 큐. 모두 위임.

Fail-soft 계약:
  - 최상위 예외는 반드시 삼킴(호출측 payment_post_process / 라우터로 전파 금지).
  - INVOICE_LIVE OFF (processor 423) 는 정상 흐름 — request/audit 만 남기고 outcome=GATED.
  - 결제/환불/알림/계약 후처리에 영향 0 (O11/M6 원칙).

Idempotency:
  - create_request 자체가 UNIQUE(payment_id, doc_type) 로 dedup + 활성상태 재사용.
  - 이미 ISSUED/PROCESSING 인 request 는 processor 호출 없이 NOOP.
  - 중복 payment.success / 재시도 / 고객 재클릭 → ORIGINAL 최대 1.

Trigger:
  - PAYMENT_SUCCESS: on_payment_success_sync 훅에서 호출.
  - CUSTOMER_REQUEST: POST /payments/{id}/tax-invoice/request 후 호출.
  둘 다 같은 orchestrator 사용 (extra idempotent select 는 감내). ORIGINAL 1 보장.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from services.time import business_today, parse_external_datetime, to_kst

log = logging.getLogger(__name__)

# outcome enum (문자열)
OUTCOME_NOOP = "NOOP"                              # 조기 종료 (proof_type/method 등 자동 대상 아님)
OUTCOME_ELIGIBLE_DENIED = "ELIGIBLE_DENIED"        # eligibility DENY (예: CARD/CASH_RECEIPT/이미발행)
OUTCOME_ELIGIBLE_REVIEW = "ELIGIBLE_REVIEW"        # eligibility REVIEW_REQUIRED
OUTCOME_REQUEST_CREATED_ONLY = "REQUEST_CREATED_ONLY"  # request 만 확보, processor 스킵(이미 ISSUED/PROCESSING)
OUTCOME_ISSUED = "ISSUED"                          # processor 성공 → ISSUED
OUTCOME_GATED = "GATED"                            # INVOICE_LIVE OFF (423)
OUTCOME_PROCESSOR_FAILED = "PROCESSOR_FAILED"      # processor 4xx/5xx (request FAILED 로 기록됨)
OUTCOME_ERROR = "ERROR"                            # 예상 밖 예외 (fail-soft 삼킴)


def _audit_auto(event: str, payment_id: Optional[str], trigger: str,
                extra: Optional[Dict[str, Any]] = None,
                actor_id: Optional[str] = None) -> None:
    try:
        from services import audit_svc
        after = {"trigger": trigger}
        if extra:
            after.update(extra)
        audit_svc.record(event, "payment", entity_id=payment_id, actor_id=actor_id, after=after)
    except Exception:  # noqa: BLE001 — audit 실패는 orchestrator 결과에 영향 없음
        pass


def _resolve_supply_date(payment: Dict[str, Any]) -> str:
    """자동 경로 supply_date: payment.paid_at 의 KST 날짜, 없으면 business_today().

    프론트/사용자 입력 금지 — 자동 경로 SoT.
    """
    paid = payment.get("paid_at")
    if paid:
        try:
            return to_kst(parse_external_datetime(str(paid).replace("Z", "+00:00"))).strftime("%Y-%m-%d")
        except Exception:  # noqa: BLE001
            pass
    return business_today().strftime("%Y-%m-%d")


def _load_payment(sb, payment_id: str) -> Optional[Dict[str, Any]]:
    from services.tax_invoice_request_svc import _PAYMENT_COLS
    try:
        res = sb.table("payments").select(_PAYMENT_COLS).eq("id", payment_id).limit(1).execute()
        data = res.data or []
        return data[0] if data else None
    except Exception:  # noqa: BLE001
        return None


def maybe_auto_issue_tax_invoice(sb, payment_id: str, trigger: str,
                                 actor_id: Optional[str] = None) -> Dict[str, Any]:
    """자동 세금계산서 오케스트레이터.

    Args:
        sb: supabase client (주입).
        payment_id: 결제 id.
        trigger: "PAYMENT_SUCCESS" | "CUSTOMER_REQUEST" | ... (audit 라벨).
        actor_id: 이 trigger 를 유발한 사용자 id (audit 용, 기록만).

    Returns:
        {"outcome": <OUTCOME_*>, "reason": str|None,
         "request_id": str|None, "invoice_id": str|None}

    Raises: 없음(모두 삼킴).
    """
    from services.tax_invoice_request_svc import (
        MemberTaxError, canonical_payment_instrument, create_request, evaluate_eligibility,
    )

    result: Dict[str, Any] = {"outcome": OUTCOME_NOOP, "reason": None,
                              "request_id": None, "invoice_id": None}
    try:
        # 1) payment authoritative read
        payment = _load_payment(sb, payment_id)
        if not payment:
            result["reason"] = "PAYMENT_NOT_FOUND"
            return result

        # 2) 사전 필터 — proof_type / method 로 자동 대상 아니면 조기 NOOP (audit 노이즈 감소)
        proof = str(payment.get("proof_type") or "").upper()
        method = canonical_payment_instrument(payment.get("pg_method"))
        if proof != "TAX_INVOICE":
            result["reason"] = "PROOF_NOT_TAX_INVOICE"
            return result
        if method == "CARD":
            result["reason"] = "PAYMENT_METHOD_CARD"
            return result

        # 3) eligibility (중앙 판정)
        elig = evaluate_eligibility(sb, payment)
        decision = str(elig.get("decision") or "").upper()
        reason_code = elig.get("reason_code")
        if decision == "DENY":
            _audit_auto("AUTO_TAX_INVOICE_DENIED", payment_id, trigger,
                        {"reason_code": reason_code}, actor_id)
            result.update({"outcome": OUTCOME_ELIGIBLE_DENIED, "reason": reason_code})
            return result
        if decision == "REVIEW_REQUIRED":
            _audit_auto("AUTO_TAX_INVOICE_REVIEW", payment_id, trigger,
                        {"reason_code": reason_code}, actor_id)
            result.update({"outcome": OUTCOME_ELIGIBLE_REVIEW, "reason": reason_code})
            return result
        if decision != "ALLOW":
            result["reason"] = "UNKNOWN_DECISION"
            return result

        # 4) create_request (system user, source 는 trigger 별)
        system_user = {"id": None, "company_id": payment.get("company_id")}
        source = "AUTO_PAYMENT"  # AUTO_SAAS 는 예비 — 이번 orchestrator 는 AUTO_PAYMENT 만 사용
        try:
            row, _created = create_request(sb, system_user, payment, source)
        except MemberTaxError as e:
            # eligibility ALLOW 였는데 create_request 가 DENY/REVIEW 를 반환하는 경우
            # (경합: 다른 트랜잭션에서 이미 ledger insert 등)
            _audit_auto("AUTO_TAX_INVOICE_CREATE_FAILED", payment_id, trigger,
                        {"code": e.code, "http": e.status_code}, actor_id)
            result.update({"outcome": OUTCOME_ELIGIBLE_DENIED, "reason": e.code})
            return result

        request_id = row.get("id")
        result["request_id"] = request_id
        status = str(row.get("status") or "").upper()

        # 5) 이미 ISSUED / PROCESSING → processor 재호출 금지 (idempotent)
        if status in ("ISSUED", "PROCESSING"):
            result.update({"outcome": OUTCOME_REQUEST_CREATED_ONLY, "reason": status})
            if status == "ISSUED":
                result["invoice_id"] = row.get("tax_invoice_id")
            return result

        # 6) processor 위임 (REQUESTED / FAILED → 재발행 시도)
        try:
            from services.tax_invoice_processor_svc import ProcessorError, process_tax_invoice_request
        except Exception as e:  # noqa: BLE001
            log.warning("[AUTO_TAX] processor import 실패: %s", e)
            result.update({"outcome": OUTCOME_ERROR, "reason": "PROCESSOR_IMPORT"})
            return result

        supply_date = _resolve_supply_date(payment)
        try:
            issued_row, outcome = process_tax_invoice_request(sb, request_id, supply_date, actor_id)
        except ProcessorError as e:
            code = getattr(e, "code", None) or ""
            if code == "INVOICE_GATED" or e.status_code == 423:
                _audit_auto("AUTO_TAX_INVOICE_GATED", payment_id, trigger,
                            {"request_id": request_id}, actor_id)
                result.update({"outcome": OUTCOME_GATED, "reason": "INVOICE_GATED"})
                return result
            # processor 가 이미 request 를 FAILED 로 mark 함
            _audit_auto("AUTO_TAX_INVOICE_PROCESSOR_FAILED", payment_id, trigger,
                        {"request_id": request_id, "code": code, "http": e.status_code}, actor_id)
            result.update({"outcome": OUTCOME_PROCESSOR_FAILED, "reason": code or "UNKNOWN"})
            return result

        result.update({"outcome": OUTCOME_ISSUED, "reason": outcome,
                       "invoice_id": (issued_row or {}).get("tax_invoice_id")})
        _audit_auto("AUTO_TAX_INVOICE_ISSUED", payment_id, trigger,
                    {"request_id": request_id, "invoice_id": result["invoice_id"]}, actor_id)
        return result

    except Exception as e:  # noqa: BLE001 — 최종 fail-soft 방벽
        log.warning("[AUTO_TAX] orchestrator 실패 payment=%s trigger=%s: %s",
                    payment_id, trigger, e)
        _audit_auto("AUTO_TAX_INVOICE_ERROR", payment_id, trigger,
                    {"error": str(e)[:300]}, actor_id)
        return {"outcome": OUTCOME_ERROR, "reason": str(e)[:200],
                "request_id": None, "invoice_id": None}
