"""Test Payment Router — 시험결제 최소 라우터.

법령진단 1회성 10,000원 + SaaS 구독 10,000원/월.
각 산업 섹터(INDUSTRIAL, BUILDING, CONSTRUCTION)별.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional

from db.supabase_client import get_supabase
from services.payment_helpers import load_template

log = logging.getLogger(__name__)
router = APIRouter(prefix="/payments/test", tags=["시험결제"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _order_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now(timezone.utc).strftime('%y%m%d%H%M%S')}_{uuid4().hex[:6]}"


# ── 페이지 ──────────────────────────────────────────────────

@router.get("/checkout", response_class=HTMLResponse)
def test_checkout_page():
    """시험결제 테스트 페이지."""
    return HTMLResponse(content=load_template("test_checkout.html"), status_code=200)


# ── 진단 1회성 결제 ────────────────────────────────────────

class DiagTestBody(BaseModel):
    sector: str = Field(..., description="INDUSTRIAL | BUILDING | CONSTRUCTION")
    goodname: str = "TAI Safe 진단"
    buyername: str = "시험사용자"
    buyertel: str = "01000000000"
    buyeremail: str = "test@taieng.co.kr"


@router.post("/diagnosis")
def test_diagnosis_pay(body: DiagTestBody):
    """진단 시험결제 10,000원 1회성.

    payments + diagnosis_purchases 레코드 생성 후 결제 대기 상태.
    KG이니시스 승인 후 실제 PG 연동 예정.
    """
    sb = get_supabase()
    order_id = _order_id("TDIAG")
    amount = 10000
    supply = 9091  # 10000 / 1.1
    vat = 909

    # 1) payments 레코드
    pay_row = {
        "payment_method": "CARD",
        "payment_type": "ONE_TIME",
        "product_type": "DIAGNOSIS",
        "plan_code": f"DIAG_{body.sector}_TEST",
        "supply_amount": supply,
        "vat_amount": vat,
        "total_amount": amount,
        "inicis_order_id": order_id,
        "status_code": "READY",
        "memo": f"시험결제: {body.sector} 진단",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    resp = sb.table("payments").insert(pay_row).execute()
    if not resp.data:
        raise HTTPException(500, detail="payments insert failed")
    payment = resp.data[0]

    # 2) diagnosis_purchases 레코드
    diag_row = {
        "sector": body.sector,
        "step": 99,  # 시험결제 구분용
        "step_label": "시험결제",
        "price": amount,
        "status": "READY",
        "payment_method": "CARD",
        "created_at": _now_iso(),
    }
    sb.table("diagnosis_purchases").insert(diag_row).execute()

    log.info("[TEST_DIAG] sector=%s oid=%s amount=%s", body.sector, order_id, amount)
    return {
        "ok": True,
        "data": {
            "payment_id": payment["id"],
            "order_id": order_id,
            "sector": body.sector,
            "amount": amount,
            "status": "READY",
            "message": f"{body.sector} 진단 시험결제 준비 완료. KG이니시스 승인 후 PG 연동 예정.",
        },
    }


# ── 구독 결제 ────────────────────────────────────────────

class SubsTestBody(BaseModel):
    sector: str = Field(..., description="INDUSTRIAL | BUILDING | CONSTRUCTION")
    plan_code: str = "IND_TEST"
    goodname: str = "TAI Safe 구독"
    buyername: str = "시험사용자"
    buyertel: str = "01000000000"
    buyeremail: str = "test@taieng.co.kr"


@router.post("/subscribe")
def test_subscribe_pay(body: SubsTestBody):
    """구독 시험결제 10,000원/월.

    subscriptions + payments 레코드 생성 후 결제 대기 상태.
    KG이니시스 승인 후 빌링키 발급 연동 예정.
    """
    sb = get_supabase()
    order_id = _order_id("TSUB")
    amount = 10000
    supply = 9091
    vat = 909

    sector_names = {
        "INDUSTRIAL": "제조업",
        "BUILDING": "건축물",
        "CONSTRUCTION": "건설업",
    }
    plan_name = f"TAI Safe {sector_names.get(body.sector, body.sector)} 시험구독"

    # 1) subscriptions 레코드
    subs_row = {
        "product_type": "SAAS_FACILITY",
        "plan_code": body.plan_code,
        "plan_name": plan_name,
        "amount": amount,
        "supply_amount": supply,
        "vat_amount": vat,
        "billing_cycle": "MONTHLY",
        "status": "READY",
        "inicis_order_id": order_id,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    resp = sb.table("subscriptions").insert(subs_row).execute()
    if not resp.data:
        raise HTTPException(500, detail="subscriptions insert failed")
    subscription = resp.data[0]

    # 2) payments 레코드 (초회 결제)
    pay_row = {
        "payment_method": "BILLING",
        "payment_type": "RECURRING",
        "product_type": "SAAS_FACILITY",
        "plan_code": body.plan_code,
        "supply_amount": supply,
        "vat_amount": vat,
        "total_amount": amount,
        "inicis_order_id": order_id,
        "status_code": "READY",
        "is_recurring": True,
        "subscription_id": subscription["id"],
        "charge_cycle": 1,
        "memo": f"시험구독: {body.sector} 월 {amount}원",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    resp2 = sb.table("payments").insert(pay_row).execute()
    payment = resp2.data[0] if resp2.data else {}

    log.info("[TEST_SUB] sector=%s plan=%s oid=%s amount=%s", body.sector, body.plan_code, order_id, amount)
    return {
        "ok": True,
        "data": {
            "subscription_id": subscription["id"],
            "payment_id": payment.get("id"),
            "order_id": order_id,
            "sector": body.sector,
            "plan_code": body.plan_code,
            "plan_name": plan_name,
            "amount": amount,
            "billing_cycle": "MONTHLY",
            "status": "READY",
            "message": f"{body.sector} 구독 시험결제 준비 완료. KG이니시스 승인 후 빌링키 발급 연동 예정.",
        },
    }


# ── 시험결제 내역 조회 ────────────────────────────────────

@router.get("/history")
def test_payment_history():
    """시험결제 내역 조회."""
    sb = get_supabase()
    resp = (
        sb.table("payments")
        .select("id, inicis_order_id, product_type, plan_code, total_amount, status_code, is_recurring, created_at, memo")
        .like("inicis_order_id", "TDIAG_%")
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    diag_list = resp.data or []

    resp2 = (
        sb.table("payments")
        .select("id, inicis_order_id, product_type, plan_code, total_amount, status_code, is_recurring, subscription_id, created_at, memo")
        .like("inicis_order_id", "TSUB_%")
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    subs_list = resp2.data or []

    return {
        "ok": True,
        "data": {
            "diagnosis_payments": diag_list,
            "subscription_payments": subs_list,
            "total": len(diag_list) + len(subs_list),
        },
    }
