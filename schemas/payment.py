"""결제 API Pydantic 스키마.

규칙: docs/DEV_RULES_SERVICE_LAYER.md STEP 2

v2.1 (2026-04-28)
  - BillingPrepareBody: plan_name + model_validator(goodname→plan_name) 추가
  - plan_code를 str 필수로 변경 (subscriptions.plan_code NOT NULL)

v2.0 (2026-04-27)
  매뉴얼 기반 전면 재정리 — docs/INICIS_INTEGRATION_SPEC.md 참조
  - BillingReturnBody: 이니시스 빌키발급 결과 파라미터 반영
  - RefundBody: 취소/환불 API용 스키마 추가
  - PartialRefundBody: 부분취소 스키마 추가
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, field_validator, model_validator


class PrepareBody(BaseModel):
    """단건결제 준비 — POST /payments/inicis/prepare"""
    user_id: str
    product_type: str
    amount: int
    goodname: str
    company_id: Optional[str] = None
    contract_id: Optional[str] = None
    quote_id: Optional[str] = None
    plan_code: Optional[str] = None
    period_months: Optional[int] = None
    payment_type: Optional[str] = "CARD"
    buyername: Optional[str] = "고객"
    buyertel: Optional[str] = "00000000000"
    buyeremail: Optional[str] = None
    return_url: Optional[str] = None
    close_url: Optional[str] = None

    @field_validator("user_id")
    @classmethod
    def user_id_required(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("user_id는 필수값입니다. 로그인 후 결제해주세요.")
        v = v.strip()
        try:
            UUID(v)
        except (ValueError, AttributeError):
            v = str(uuid4())
        return v

    @field_validator("product_type")
    @classmethod
    def product_type_valid(cls, v: str) -> str:
        if v.startswith("DIAG_"):
            v = "DIAGNOSIS"
        allowed = {
            "DIAGNOSIS",
            "SAAS_CONSTRUCTION",
            "SAAS_FACILITY",
            "SAAS_BUILDING",
            "SAAS_INDUSTRY",
            "EXPERT",
            "REPAIR",
            "CONSULTING",
            "INAPP",
        }
        if v not in allowed:
            raise ValueError(f"product_type 값이 유효하지 않습니다. 허용: {allowed}")
        return v


class VbankPrepareBody(BaseModel):
    """VBANK 전용 결제 준비 — 연결 서비스(선임/컨설팅/수선) 전용"""
    user_id: Optional[str] = None
    auth_token: Optional[str] = None
    public_token: Optional[str] = None
    product_type: str
    amount: int
    goodname: str
    matching_contract_id: Optional[str] = None
    company_id: Optional[str] = None
    buyername: Optional[str] = "고객"
    buyertel: Optional[str] = "00000000000"
    buyeremail: Optional[str] = None
    vbank_expire_min: int = 4320

    @field_validator("product_type")
    @classmethod
    def validate_vbank_product(cls, v: str) -> str:
        allowed = {"EXPERT", "CONSULTING", "REPAIR", "DIAGNOSIS"}
        if v not in allowed:
            raise ValueError(f"VBANK product_type 허용: {allowed}")
        return v


class DiagnosisVbankPrepareBody(BaseModel):
    """유료 진단 가상계좌 발급 준비."""
    auth_token: Optional[str] = None
    public_token: Optional[str] = None
    amount: int
    goodname: str = "유료 법령진단"
    buyername: Optional[str] = "고객"
    buyertel: Optional[str] = "00000000000"
    buyeremail: Optional[str] = None
    invoice_requested: bool = False
    invoice_biz_no: Optional[str] = None
    invoice_email: Optional[str] = None


# ── 구독(빌링) 스키마 ──────────────────────────────────────────────────

class BillingPrepareBody(BaseModel):
    """빌링키 발급 준비 — POST /payments/inicis/billing/prepare

    v2.1: goodname → plan_name fallback 추가.
    프론트 결제 페이지가 goodname을 보내므로 plan_name으로 자동 매핑.
    """
    user_id: str
    product_type: str
    amount: int
    goodname: str
    plan_code: str = "BASIC"
    plan_name: Optional[str] = None
    period_months: int = 1
    company_id: Optional[str] = None
    factory_id: Optional[str] = None
    buyername: Optional[str] = "고객"
    buyertel: Optional[str] = "00000000000"
    buyeremail: Optional[str] = None

    @model_validator(mode="after")
    def resolve_plan_name(self):
        """goodname → plan_name fallback. 핸들러가 body.plan_name을 참조."""
        if not self.plan_name and self.goodname:
            self.plan_name = self.goodname
        return self


class BillingReturnBody(BaseModel):
    """빌링키 발급 결과 — 이니시스 returnUrl POST 파라미터.

    매뉴얼: https://manual.inicis.com/pay/bill.html STEP2
    resultCode: "SUCCESS" = 성공 (단건 "0000"과 다름)
    billkey: AES256 암호화된 빌링키 → 복호화 필요
    """
    resultCode: str
    resultMessage: Optional[str] = None
    mid: Optional[str] = None
    orderId: Optional[str] = None
    authkey: Optional[str] = None
    tid: Optional[str] = None
    merchantRedirectData: Optional[str] = None
    billkey: Optional[str] = None
    billkeyDate: Optional[str] = None
    billkeyTime: Optional[str] = None
    cardNumber: Optional[str] = None
    cardCode: Optional[str] = None
    cardCompanyName: Optional[str] = None
    cardType: Optional[str] = None
    cardTypeName: Optional[str] = None
    cardKind: Optional[str] = None
    cardKindName: Optional[str] = None
    hashData: Optional[str] = None


class BillingChargeBody(BaseModel):
    """빌링 승인(과금) 요청 — POST /payments/inicis/billing/charge"""
    subscription_id: str
    amount: Optional[int] = None
    goodname: Optional[str] = None


class BillingCancelBody(BaseModel):
    """구독 해지 — POST /subscriptions/{id}/cancel"""
    reason: Optional[str] = "사용자 요청"
    cancelled_by: Optional[str] = None


# ── 취소/환불 스키마 ───────────────────────────────────────────────────

class RefundBody(BaseModel):
    """전체 취소 — POST /payments/{payment_id}/refund

    매뉴얼: https://manual.inicis.com/pay/cancel.html
    """
    reason: str = "사용자 요청"
    cancelled_by: Optional[str] = None


class PartialRefundBody(BaseModel):
    """부분 취소 — POST /payments/{payment_id}/partial-refund"""
    amount: int
    reason: str = "사용자 요청"
    cancelled_by: Optional[str] = None


# ── 기타 ──────────────────────────────────────────────────────────────

class ManualConfirmBody(BaseModel):
    payment_id: str
    contract_id: str
    by: Optional[str] = None  # 수동활성화 처리자(감사 actor). 프론트에서 'admin' 전달.


class CancelBody(BaseModel):
    reason: Optional[str] = "사용자 요청"
    cancelled_by: Optional[str] = None
