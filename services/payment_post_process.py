"""결제 완료 후처리 — 계약 자동 생성 + 알림 발송.

[2026-07-29 P2-4] 결제 성공 시 automation 이벤트(payment.success) 발화 결선.
  발화는 automation_svc.fire 위임. 규칙이 없으면 무동작이며, 예외는 삼켜서
  결제 후처리(계약 생성·알림)에 절대 영향을 주지 않는다(_fire_automation).

[2026-09-04] 계약 자동생성 판정을 positive allowlist 로 정리.
  기존 _should_auto_contract 는 product_type 무관 plan_code 만 있으면 계약을 만들어,
  진단(DIAGNOSIS) 결제가 service_type=SAAS 계약으로 둔갑했다(1건 실측: contract 88ec1537).
  실측(payments inventory): DIAGNOSIS + plan_code 는 97건이 계약 없음이 정상,
  계약 붙은 건 이번 사고 1건뿐. SAAS 아닌데 plan_code 로 계약 생성에 의존하는 정상 writer 없음.
  → 신규 계약 자동생성은 product_type in SAAS_PRODUCT_TYPES 일 때만 True.
  plan_code 단독 fallback 제거(재발 구조 제거). 기존 contract_id 연결/renewal 경로는 무변경.
"""
from __future__ import annotations

import logging
import random
from datetime import date, datetime
from typing import Any, Dict, Optional

from dateutil.relativedelta import relativedelta

from db.supabase_client import get_supabase
from services.payment_helpers import SAAS_PRODUCT_TYPES, now_iso
from services.time import business_today, now_kst

logger = logging.getLogger(__name__)

PAID_STATUS_CODES = frozenset({"PAID", "SUCCESS"})

PLAN_MAP = {
    "BUILDING_LITE": {"sector": "FACILITY", "level": 1},
    "BUILDING_BASIC": {"sector": "FACILITY", "level": 2},
    "BUILDING_STANDARD": {"sector": "FACILITY", "level": 3},
    "BUILDING_CUSTOM": {"sector": "FACILITY", "level": 4},
    "INDUSTRY_STARTER_V2": {"sector": "INDUSTRIAL", "level": 1},
    "INDUSTRY_BUSINESS_V2": {"sector": "INDUSTRIAL", "level": 2},
    "INDUSTRY_PRO": {"sector": "INDUSTRIAL", "level": 3},
    "INDUSTRY_CUSTOM_V2": {"sector": "INDUSTRIAL", "level": 4},
    "CONSTRUCTION_STANDARD_V2": {"sector": "CONSTRUCTION", "level": 1},
    "CONSTRUCTION_PREMIUM_V2": {"sector": "CONSTRUCTION", "level": 2},
    "CONSTRUCTION_CUSTOM_V2": {"sector": "CONSTRUCTION", "level": 3},
}


def _fire_automation(event_type: str, payload: Dict[str, Any], trigger_ref: Optional[str] = None) -> None:
    """automation 이벤트 발화(베스트에포트). 규칙 없으면 무동작, 예외는 삼킨다."""
    try:
        from services.automation_svc import fire
        fire(event_type, payload, trigger_ref=trigger_ref)
    except Exception as e:  # noqa: BLE001
        logger.warning("[AUTOMATION] %s 발화 실패: %s", event_type, e)


def _gen_contract_no() -> str:
    return f"CON-{now_kst().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"


def _contract_end_date(start: date, period_months: int) -> date:
    return start + relativedelta(months=period_months)


def _should_auto_contract(pay: dict) -> bool:
    """신규 SaaS 계약 자동생성 대상 판정 (positive allowlist).

    계약(구독)은 SaaS 상품(SAAS_PRODUCT_TYPES)에서만 자동 생성한다.
    진단(DIAGNOSIS) 등 1회성 상품은 plan_code 가 있어도 계약을 만들지 않는다.
    (기존 plan_code 단독 fallback 은 진단→SAAS 계약 둔갑의 재발 구조라 제거)
    기존 contract_id 연결 결제는 이 함수 이전 단계에서 activate/renewal 로 분기된다.
    """
    if pay.get("contract_id"):
        return False
    if not pay.get("company_id"):
        return False
    product_type = pay.get("product_type") or ""
    return product_type in SAAS_PRODUCT_TYPES


def _parse_contract_date(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _activate_existing_contract(sb, pay: dict, contract_id: str) -> None:
    now = now_iso()
    update: dict[str, Any] = {
        "status_code": "ACTIVE",
        "is_active": True,
        "paid_amount": float(pay.get("total_amount") or 0),
        "paid_at": pay.get("paid_at") or now,
        "updated_at": now,
    }
    period_months = pay.get("period_months")
    if period_months:
        start = business_today()
        update["start_date"] = start.isoformat()
        update["end_date"] = _contract_end_date(start, int(period_months)).isoformat()
    sb.table("contracts").update(update).eq("id", contract_id).execute()


def _extend_contract_for_renewal(sb, pay: dict, contract_id: str) -> None:
    """기간연장: 기존 end_date 이후부터 period_months 만큼 연장."""
    ct_res = sb.table("contracts").select("end_date, start_date, status_code").eq("id", contract_id).limit(1).execute()
    if not ct_res.data:
        logger.warning("Renewal contract %s not found", contract_id)
        return

    contract = ct_res.data[0]
    period_months = int(pay.get("period_months") or 1)
    current_end = _parse_contract_date(contract.get("end_date"))
    base_start = current_end if current_end and current_end >= business_today() else business_today()
    new_end = _contract_end_date(base_start, period_months)
    now = now_iso()

    update: dict[str, Any] = {
        "status_code": "ACTIVE",
        "is_active": True,
        "end_date": new_end.isoformat(),
        "paid_amount": float(pay.get("total_amount") or 0),
        "paid_at": pay.get("paid_at") or now,
        "updated_at": now,
    }
    if pay.get("plan_code"):
        update["plan_code"] = pay["plan_code"]
    sb.table("contracts").update(update).eq("id", contract_id).execute()


def _expire_other_active_contracts(sb, company_id: str, contract_id: str) -> None:
    sb.table("contracts").update(
        {"status_code": "EXPIRED", "is_active": False, "updated_at": now_iso()}
    ).eq("company_id", company_id).neq("id", contract_id).eq("status_code", "ACTIVE").execute()


def _create_contract_from_payment(sb, pay: dict) -> Optional[str]:
    plan_code = (pay.get("plan_code") or "INDUSTRY_PRO").upper()
    period_months = int(pay.get("period_months") or 12)
    start = business_today()
    end = _contract_end_date(start, period_months)
    now = now_iso()

    contract_row: dict[str, Any] = {
        "contract_no": _gen_contract_no(),
        "company_id": pay["company_id"],
        "plan_code": plan_code,
        "status_code": "ACTIVE",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "service_type": "SAAS",
        "contract_amount": float(pay.get("supply_amount") or 0),
        "vat_amount": float(pay.get("vat_amount") or 0),
        "total_amount": float(pay.get("total_amount") or 0),
        "paid_amount": float(pay.get("total_amount") or 0),
        "paid_at": pay.get("paid_at") or now,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
        "memo": f"자동생성 — 결제 {str(pay.get('id', ''))[:8]}",
    }
    if pay.get("quote_id"):
        contract_row["quote_id"] = pay["quote_id"]

    ct_res = sb.table("contracts").insert(contract_row).execute()
    if not ct_res.data:
        logger.error("Failed to create contract for payment %s", pay.get("id"))
        return None
    return ct_res.data[0]["id"]


def send_payment_notification(pay: dict, plan_code: str, plan_info: dict) -> None:
    """SMS + Email + 인앱 결제 완료 알림."""
    sb = get_supabase()
    user_id = pay.get("user_id")
    user: dict[str, Any] = {}
    if user_id:
        user_res = sb.table("users").select("name, phone, email").eq("id", user_id).limit(1).execute()
        if user_res.data:
            user = user_res.data[0]

    company_name = ""
    if pay.get("company_id"):
        company_res = (
            sb.table("companies")
            .select("name")
            .eq("id", pay["company_id"])
            .limit(1)
            .execute()
        )
        if company_res.data:
            company_name = company_res.data[0].get("name") or ""

    sector_kr = {"FACILITY": "건물", "INDUSTRIAL": "산업", "CONSTRUCTION": "건설"}.get(
        plan_info.get("sector", ""), ""
    )
    total = int(float(pay.get("total_amount") or 0))

    # ── SMS ──
    phone = user.get("phone")
    if phone:
        try:
            from services.notification_engine.runtime_compat import compat_send_sms

            sms_text = (
                f"[TAI Safe] {user.get('name', '')}님, 결제가 완료되었습니다.\n"
                f"플랜: {sector_kr} {plan_code}\n"
                f"금액: {total:,}원\n"
                f"지금 바로 이용하세요 → safe.taieng.co.kr"
            )
            compat_send_sms(
                phone,
                sms_text,
                event_type="PAYMENT_SUCCESS",
                source_engine="payment_post_process",
                user_id=user_id,
                company_id=pay.get("company_id"),
                title="결제 완료",
                source_entity_id=str(pay.get("id", "")),
            )
        except Exception as e:
            logger.error("SMS send failed: %s", e)

    # ── Email (Gmail SMTP) ──
    email = user.get("email")
    if email:
        try:
            from utils.email_sender import send_email, payment_success_email

            subject, html, text = payment_success_email(
                user_name=user.get("name", ""),
                company_name=company_name,
                plan_code=plan_code,
                total_amount=total,
                sector_kr=sector_kr,
            )
            send_email(to=email, subject=subject, body_html=html, body_text=text)
        except Exception as e:
            logger.error("Email send failed: %s", e)

    # ── 인앱 알림 ──
    body = (
        f"{company_name + ' ' if company_name else ''}{sector_kr} 플랜 결제가 완료되었습니다. "
        "safe.taieng.co.kr에서 이용을 시작하세요."
    ).strip()
    try:
        sb.table("notification_queue").insert({
            "user_id": user_id,
            "company_id": pay.get("company_id"),
            "event_type": "PAYMENT_SUCCESS",
            "title": "결제 완료",
            "body": body,
            "channel": "INAPP",
            "status": "PENDING",
        }).execute()
    except Exception as e:
        logger.warning("notification_queue insert failed, skipping in-app: %s", e)

    # ── Slack 매출 알림 (#tai-ops, 베스트에포트) ──
    try:
        from services.slack_dispatcher import ops
        product = pay.get("product_type") or ""
        plan_label = f"{sector_kr} {plan_code}".strip() if sector_kr else (plan_code or product or "결제")
        detail = (
            f"상품: {plan_label}" + (f" ({product})" if product else "")
            + f"\n금액: {total:,}원"
            + f"\n구매자: {user.get('name') or '-'} / 회사: {company_name or '-'}"
            + f"\n연락처: {user.get('phone') or '-'} / 이메일: {user.get('email') or '-'}"
            + f"\n결제ID: {str(pay.get('id', ''))[:8]}"
        )
        ops(f"💰 결제 완료 · {plan_label} · {total:,}원", detail)
    except Exception as e:
        logger.error("Slack sales notify failed: %s", e)


def on_payment_success_sync(payment_id: str) -> None:
    """결제 성공 시 계약 자동생성 + 알림 (동기)."""
    sb = get_supabase()
    pay_res = sb.table("payments").select("*").eq("id", payment_id).limit(1).execute()
    if not pay_res.data:
        logger.warning("Payment %s not found, skip post-process", payment_id)
        return

    pay = pay_res.data[0]
    status = pay.get("status_code")
    if status not in PAID_STATUS_CODES:
        logger.warning("Payment %s status=%s, skip post-process", payment_id, status)
        return

    plan_code = (pay.get("plan_code") or "INDUSTRY_PRO").upper()
    plan_info = PLAN_MAP.get(plan_code, {"sector": "INDUSTRIAL", "level": 3})

    # [P2-4] 결제 성공 automation 이벤트 발화(모든 성공 경로 공통 지점: 카드성공·수동활성화).
    _fire_automation("payment.success", {
        "payment_id": payment_id,
        "company_id": pay.get("company_id"),
        "user_id": pay.get("user_id"),
        "plan_code": plan_code,
        "product_type": pay.get("product_type"),
        "total_amount": pay.get("total_amount"),
        "status": status,
    }, trigger_ref=payment_id)

    existing_contract_id = pay.get("contract_id")
    if existing_contract_id:
        if (pay.get("payment_type") or "").upper() == "RENEWAL":
            _extend_contract_for_renewal(sb, pay, existing_contract_id)
            logger.info("Payment %s renewed contract %s", payment_id, existing_contract_id)
        else:
            _activate_existing_contract(sb, pay, existing_contract_id)
            logger.info("Payment %s activated contract %s", payment_id, existing_contract_id)
        send_payment_notification(pay, plan_code, plan_info)
        return

    if not _should_auto_contract(pay):
        send_payment_notification(pay, plan_code, plan_info)
        return

    contract_id = _create_contract_from_payment(sb, pay)
    if not contract_id:
        return

    sb.table("payments").update(
        {"contract_id": contract_id, "updated_at": now_iso()}
    ).eq("id", payment_id).execute()

    _expire_other_active_contracts(sb, pay["company_id"], contract_id)
    logger.info(
        "Contract %s created for payment %s, plan=%s",
        contract_id,
        payment_id,
        plan_code,
    )
    send_payment_notification(pay, plan_code, plan_info)


async def on_payment_success(payment_id: str) -> None:
    """결제 성공 후처리 (async 라우터용)."""
    on_payment_success_sync(payment_id)
