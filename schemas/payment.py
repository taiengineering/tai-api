"""결제 API Pydantic 스키마.

규칙: docs/DEV_RULES_SERVICE_LAYER.md STEP 2
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, field_validator


class PrepareBody(BaseModel):
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
        return v.strip()

    @field_validator("product_type")
    @classmethod
    def product_type_valid(cls, v: str) -> str:
        # 프론트 호환: DIAG_BUILDING/DIAG_INDUSTRY/DIAG_CONSTRUCTION → DIAGNOSIS
        if v.startswith("DIAG_"):
            v = "DIAGNOSIS"
        allowed = {
            "DIAGNOSIS",
            "SAAS_CONSTRUCTION",
            "SAAS_FACILITY",
            "SAAS_BUILDING",
            "EXPERT",
            "REPAIR",
            "CONSULTING",
            "INAPP",
        }
        if v not in allowed:
            raise ValueError(f"product_type 값이 유효하지 않습니다. 허용: {allowed}")
        return v


class VbankPrepareBody(BaseModel):
    """VBANK 전용 결제 준비 Body — 연결 서비스(선임/컨설팅/수선) 전용"""

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


class ManualConfirmBody(BaseModel):
    payment_id: str
    contract_id: str


class CancelBody(BaseModel):
    reason: Optional[str] = "사용자 요청"
    cancelled_by: Optional[str] = None


class BillingPrepareBody(BaseModel):
    user_id: str
    product_type: str
    amount: int
    goodname: str
    plan_code: Optional[str] = None
    period_months: int = 1
    company_id: Optional[str] = None
    buyername: Optional[str] = "고객"
    buyertel: Optional[str] = "00000000000"
    buyeremail: Optional[str] = None


class BillingReturnBody(BaseModel):
    oid: str
    authToken: str
    authUrl: str
    resultCode: Optional[str] = None
    resultMsg: Optional[str] = None
    cardNumber: Optional[str] = None
    cardCode: Optional[str] = None


class BillingChargeBody(BaseModel):
    subscription_id: str
    amount: Optional[int] = None
    goodname: Optional[str] = None


class BillingCancelBody(BaseModel):
    reason: Optional[str] = "사용자 요청"
    cancelled_by: Optional[str] = None
