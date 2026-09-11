from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field


class AnchorBody(BaseModel):
    anchor_date: Optional[str] = None
    schedule_anchor_date: Optional[str] = None
    last_inspection_date: Optional[str] = None


class BulkAnchorBody(BaseModel):
    factory_id: str
    anchor_date: str


class AnchorBulkItem(BaseModel):
    id: str
    schedule_anchor_date: str
    last_inspection_date: Optional[str] = None


class AnchorBulkPatchBody(BaseModel):
    items: list[AnchorBulkItem]


class ManualInspectionSetBody(BaseModel):
    factory_id: str
    inspection_set_name: str
    inspection_category: str = "GENERAL"
    template_id: Optional[str] = None
    cycle_value: int = 1
    cycle_unit: str = "month"
    cycle_base_type: str = "LAST_INSPECTION"
    description: Optional[str] = None


class InspectionSetPatchBody(BaseModel):
    is_active: Optional[bool] = None
    schedule_anchor_date: Optional[str] = None
    last_inspection_date: Optional[str] = None
    assignee_user_id: Optional[str] = None
    description: Optional[str] = None


class OperationCycleBody(BaseModel):
    # WO-SAAS-OPERATION-CYCLE-SETTER-001 (+PATCH-1A): 사용자 확정 운영주기(cycle)만. 법정주기 해석 아님.
    # strict int — Pydantic 의 bool→int / "1"→int / 1.0→int coercion 을 차단(true/false/"1"/1.0 → 422).
    cycle_unit: str
    cycle_value: Annotated[int, Field(strict=True, ge=1)]


class OperationTimeRuleBody(BaseModel):
    """WO-SAFE-OPERATION-TIME-BACKEND-V1-001 — operator-aware OPERATION rule (LEGAL 아님).

    dedicated endpoint 전용. /operation-cycle(cycle_unit/value only) 과 분리.
    """
    version: str = "v1"
    source: str  # LEGAL_DEFAULT | USER_EDITED
    operator: str  # EVERY | WITHIN | BEFORE | UNTIL
    value: Annotated[Optional[int], Field(default=None, strict=True, ge=1)] = None
    unit: Optional[str] = None
    basis_date: Optional[str] = None  # YYYY-MM-DD
    basis_text: Optional[str] = None
    month: Annotated[Optional[int], Field(default=None, strict=True, ge=1, le=12)] = None
    day: Annotated[Optional[int], Field(default=None, strict=True, ge=1, le=31)] = None
    create_schedule: bool = False
