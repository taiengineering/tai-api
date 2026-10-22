"""schemas/obligation_change.py

WP01-D: 의무 변경관리 요청/응답 스키마.
"""
from __future__ import annotations

from datetime import date as _date
from typing import Optional

from pydantic import BaseModel, field_validator


class ObligationChangeSummaryRequest(BaseModel):
    factory_id: str
    diagnosis_id: str
    site_id: Optional[str] = None


class RemovalPreviewRequest(BaseModel):
    factory_id: str
    inspection_set_id: str
    application_date: Optional[str] = None  # ISO date string, e.g. "2026-11-01"


class ScopeARemovalRequest(BaseModel):
    factory_id: str
    work_schedule_id: str
    reason: str  # 필수, DB 저장 안 함


class ScopeBRemovalRequest(BaseModel):
    factory_id: str
    inspection_set_id: str
    application_date: str  # 필수 ISO date
    reason: str  # 필수, 로그 전용

    @field_validator("application_date")
    @classmethod
    def validate_iso_date(cls, v: str) -> str:
        try:
            _date.fromisoformat(v)
        except ValueError:
            raise ValueError(
                f"application_date 는 YYYY-MM-DD 형식이어야 합니다: {v!r}"
            )
        return v
