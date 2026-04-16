"""
app/models/diagnosis_result.py — v1.0.0

BE-06: factory_diagnosis_results.result_data 표준 Pydantic 모델

특이사항:
  - 기존 legacy 키(구 엔진 출력)는 `extra='allow'`로 수용
  - 신규 INSERT 시 schema_version='2026.04' 입력 필수
  - 수동 validate: DiagnosisResultV202604.model_validate(result_data)
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator
from datetime import datetime


class HeadlineModel(BaseModel):
    summary:  str
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]


class ApplicableLawModel(BaseModel):
    code:          str
    name:          str
    applicable:    bool
    threshold_hit: Optional[bool] = None


class DueModel(BaseModel):
    type:    Literal["DAYS", "MONTHS", "ANNUAL", "ONETIME", "ONGOING"]
    value:   Optional[float] = None
    display: str


class PenaltyModel(BaseModel):
    krw:      Optional[int] = None
    criminal: Optional[bool] = None
    type:     Optional[str] = None


class ObligationModel(BaseModel):
    id:             str
    law_ref:        Optional[str] = None
    title:          str
    due:            Optional[DueModel] = None
    penalty:        Optional[PenaltyModel] = None
    risk_level:     Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    is_retroactive: Optional[bool] = None
    evidence:       list[str] = Field(default_factory=list)
    action_url:     Optional[str] = None

    model_config = {"extra": "allow"}


class RiskSummaryModel(BaseModel):
    critical: int = 0
    high:     int = 0
    medium:   int = 0
    low:      int = 0


class WarningModel(BaseModel):
    code:    str
    message: str
    level:   Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"] = "INFO"


class InspectionScheduleModel(BaseModel):
    daily:      Optional[int] = None
    weekly:     Optional[int] = None
    monthly:    Optional[int] = None
    quarterly:  Optional[int] = None
    semiannual: Optional[int] = None
    annual:     Optional[int] = None
    onetime:    Optional[int] = None


class ExposureModel(BaseModel):
    penalty_max_krw:  Optional[int] = None
    criminal_risk:    Optional[bool] = None
    current_exposure: Optional[Literal["HIGH", "MEDIUM", "LOW"]] = None


class NextActionModel(BaseModel):
    type:    str
    label:   str
    benefit: Optional[str] = None


class ROIModel(BaseModel):
    annual_penalty_risk_krw:  Optional[int] = None
    tai_safe_annual_cost_krw: Optional[int] = None
    payback_days:             Optional[int] = None
    risk_reduction_percent:   Optional[float] = None


class DiagnosisResultV202604(BaseModel):
    """
    v2026.04 표준 진단 결과 모델.
    신규 INSERT 시 이 모델로 검증 후 DB에 저장.
    """
    schema_version: Literal["2026.04"]
    tier:   Literal["FREE", "PAID", "PAID1", "PAID2", "PAID3"]
    sector: Literal["BUILDING", "INDUSTRY", "CONSTRUCTION"]
    generated_at: datetime
    valid_until:  Optional[datetime] = None

    headline:         Optional[HeadlineModel] = None
    applicable_laws:  list[ApplicableLawModel] = Field(default_factory=list)
    obligations:      list[ObligationModel]
    risk_summary:     RiskSummaryModel
    warnings:         list[WarningModel] = Field(default_factory=list)
    inspection_schedule: Optional[InspectionScheduleModel] = None
    exposure:         Optional[ExposureModel] = None
    next_actions:     list[NextActionModel] = Field(default_factory=list)
    roi:              Optional[ROIModel] = None

    rule_count_total: int = Field(ge=0, description="전체 룰 수 (조건 미충족 포함)")
    rule_count_shown: int = Field(ge=0, description="적용 룰 수 (obligations 머리수)")

    model_config = {"extra": "allow"}  # legacy 키 허용

    @model_validator(mode="after")
    def validate_rule_count_shown(self) -> DiagnosisResultV202604:
        """rule_count_shown 은 obligations 리스트 길이와 일치해야 함"""
        if self.rule_count_shown != len(self.obligations):
            # 엄격히 raise하지 않고 자동 일치 조정
            self.rule_count_shown = len(self.obligations)
        return self


class DiagnosisResultLegacy(BaseModel):
    """
    구 스킬마 매핑 모델 (읽기 전용).
    DB에서 불러올 때 legacy 키 접근을 위해 사용.
    """
    schema_version: str = "legacy"

    # 기존 키 엄루 (None 허용)
    stage:            Optional[int] = None
    step:             Optional[int] = None
    sector:           Optional[str] = None
    tier:             Optional[str] = None
    summary:          Optional[dict] = None
    applicable_count: Optional[int] = None
    rule_count:       Optional[int] = None
    total_rules_checked: Optional[int] = None
    obligations:      Optional[list] = None
    key_obligations:  Optional[list] = None
    inspection_required: Optional[list] = None
    action_required:  Optional[list] = None
    appointment_required: Optional[list] = None
    report_required:  Optional[list] = None
    warnings:         Optional[list] = None
    urgent_action_items: Optional[list] = None
    construction_specific_tips: Optional[list] = None
    edge_case_warning: Optional[list] = None
    risk_summary:     Optional[dict] = None
    applicable_laws:  Optional[list] = None
    headline_message: Optional[str] = None
    evaluated_at:     Optional[str] = None
    engine_version:   Optional[str] = None

    model_config = {"extra": "allow"}


def parse_result_data(data: dict) -> DiagnosisResultV202604 | DiagnosisResultLegacy:
    """
    result_data dict를 받아 적절한 모델로 매핑.
    schema_version='2026.04' 이면 신규 모델, 아니면 legacy.
    """
    if data.get("schema_version") == "2026.04":
        return DiagnosisResultV202604.model_validate(data)
    return DiagnosisResultLegacy.model_validate(data)
