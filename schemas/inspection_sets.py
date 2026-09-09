from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


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
    # WO-SAAS-OPERATION-CYCLE-SETTER-001: 사용자 확정 운영주기(cycle)만. 법정주기 해석 아님.
    cycle_unit: str
    cycle_value: int
