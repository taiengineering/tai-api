"""Pydantic 스키마 — 매칭 / 수수료 (routers/matching 분리)."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, field_validator


class MatchingRequestBody(BaseModel):
    user_id: str
    expert_type: str
    title: str

    company_id: Optional[str] = None
    factory_id: Optional[str] = None
    service_regions: Optional[List[str]] = None
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None
    start_date: Optional[str] = None
    duration_months: Optional[int] = None
    description: Optional[str] = None
    requirements: Optional[dict] = None
    source: Optional[str] = "SITE"

    @field_validator("expert_type")
    @classmethod
    def check_expert_type(cls, v: str) -> str:
        if v not in {"EXPERT", "CONSULTING", "REPAIR"}:
            raise ValueError("expert_type은 EXPERT/CONSULTING/REPAIR 중 하나여야 합니다.")
        return v


class StatusUpdateBody(BaseModel):
    status: str
    memo: Optional[str] = None


class MatchResultCreateBody(BaseModel):
    request_id: str
    expert_user_id: str
    supplier_type: str
    supplier_id: str
    rank_no: int = 1
    match_score: Optional[float] = None


class ProposalBody(BaseModel):
    proposal_title: str
    proposal_content: str
    proposal_amount: int
    proposal_period: int
    proposal_note: Optional[str] = None


class CommissionBody(BaseModel):
    service_type: str
    fee_rate: float
    period_min: Optional[int] = None
    period_max: Optional[int] = None
    amount_min: Optional[int] = None
    amount_max: Optional[int] = None
    description: Optional[str] = None
    is_active: bool = True

    @field_validator("service_type")
    @classmethod
    def check_service_type(cls, v: str) -> str:
        if v not in {"EXPERT", "CONSULTING", "REPAIR"}:
            raise ValueError("service_type은 EXPERT/CONSULTING/REPAIR 중 하나여야 합니다.")
        return v

    @field_validator("fee_rate")
    @classmethod
    def check_fee_rate(cls, v: float) -> float:
        if not (0 < v <= 100):
            raise ValueError("fee_rate는 0 초과 100 이하여야 합니다.")
        return v


class CalcBody(BaseModel):
    service_type: str
    contract_amount: int
    period_months: Optional[int] = 1
