from typing import Optional

from pydantic import BaseModel, Field


class DisclaimerBody(BaseModel):
    auth_token: str = Field(..., description="본인인증 auth_token")
    agreed: bool = Field(..., description="true이어야 진단 실행 가능")
    ip_address: Optional[str] = Field(None, description="FE에서 수집한 제출자 IP")
    user_agent: Optional[str] = Field(None, description="User-Agent")


class DiagnosisRunBody(BaseModel):
    auth_token: str = Field(..., description="본인인증 auth_token")
    disclaimer_log_id: str = Field(..., description="면책 동의 ID (POST /diagnosis/disclaimer 반환값)")
    sector: str = Field(..., description="BUILDING | INDUSTRIAL | CONSTRUCTION | SPECIAL_FACILITY")
    floor_area: Optional[float] = Field(None, description="바닥면적(㎡) — BUILDING")
    total_floor_area: Optional[float] = Field(None, description="연면적(㎡)")
    contract_amount_eok: Optional[float] = Field(None, description="공사금액(억원) — CONSTRUCTION")
    user_tier: Optional[str] = Field(None, description="산업(INDUSTRIAL) 사용자 선택 티어")
    direct_workers: Optional[int] = None
    subcon_workers: Optional[int] = None
    worker_count: Optional[int] = None
    employee_count: Optional[int] = None
    ksic_major: Optional[str] = None
    building_use_type: Optional[str] = None
    construction_type: Optional[str] = Field(None, description="음/토/건축/기능 등")
    region: Optional[str] = None
    payment_ref: Optional[str] = Field(None, description="유료 결제 참조 번호 (무료이면 생략)")
    invoice_requested: bool = Field(False, description="세금계산서 요청 여부")
    invoice_biz_no: Optional[str] = Field(None, description="세금계산서 사업자등록번호")
    invoice_email: Optional[str] = Field(None, description="세금계산서 수신 이메일")
    invoice_company_name: Optional[str] = Field(None, description="세금계산서 상호")
    factory_id: Optional[str] = Field(None, description="SaaS 사업장 ID — 있으면 Binding Engine 호출")
    company_id: Optional[str] = Field(None, description="SaaS tenant(회사) ID — factory_id와 함께 사용")


class UpgradeBody(BaseModel):
    auth_token: str = Field(..., description="본인인증 auth_token")
    public_token: str = Field(..., description="기존 진단 public_token")
    target_tier_code: str = Field(..., description="업그레이드 목표 티어")
    payment_ref: str = Field(..., description="결제 참조 번호")
    invoice_requested: bool = Field(False, description="세금계산서 요청 여부")
    invoice_biz_no: Optional[str] = Field(None, description="세금계산서 사업자등록번호")
    invoice_email: Optional[str] = Field(None, description="세금계산서 수신 이메일")
    invoice_company_name: Optional[str] = Field(None, description="세금계산서 상호")
