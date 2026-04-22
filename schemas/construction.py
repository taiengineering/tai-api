from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class SiteCreate(BaseModel):
    company_id: str
    site_name: str
    site_code: Optional[str] = None
    site_type: str = "BUILDING"
    contract_amount: Optional[float] = Field(
        None,
        description="공사 도급금액. 단위: 억원(1억=100,000,000원). "
        "예) 150억원 공사 → 150 입력. "
        "원화(원) 단위 입력 시 안전관리자 선임 의무 판정 오류 발생.",
    )
    total_workers: Optional[int] = 0
    direct_workers: Optional[int] = 0
    subcon_workers: Optional[int] = 0
    site_address: Optional[str] = None
    site_address_detail: Optional[str] = None
    site_sido: Optional[str] = None
    site_sigungu: Optional[str] = None
    latitude: Optional[float] = Field(None, description="WGS84 위도 (예: 37.5665)")
    longitude: Optional[float] = Field(None, description="WGS84 경도 (예: 126.9780)")
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    manager_id: Optional[str] = None
    status_code: Optional[str] = "PLANNED"
    notes: Optional[str] = None


class SitePatch(BaseModel):
    site_name: Optional[str] = None
    site_type: Optional[str] = None
    contract_amount: Optional[float] = None
    total_workers: Optional[int] = None
    direct_workers: Optional[int] = None
    subcon_workers: Optional[int] = None
    site_address: Optional[str] = None
    site_address_detail: Optional[str] = None
    site_sido: Optional[str] = None
    site_sigungu: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    manager_id: Optional[str] = None
    status_code: Optional[str] = None
    notes: Optional[str] = None


class ProcessCreate(BaseModel):
    process_master_id: Optional[str] = None
    kcsc_process_id: Optional[str] = None
    work_type_code: Optional[str] = None
    work_type_label: Optional[str] = None
    process_name: str
    construction_type: Optional[str] = None
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    worker_count: Optional[int] = 0
    is_high_risk: Optional[bool] = False
    sort_order: Optional[int] = 0
    notes: Optional[str] = None


class ProcessPatch(BaseModel):
    process_name: Optional[str] = None
    kcsc_process_id: Optional[str] = None
    work_type_code: Optional[str] = None
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    actual_start: Optional[date] = None
    actual_end: Optional[date] = None
    progress_rate: Optional[int] = None
    worker_count: Optional[int] = None
    is_high_risk: Optional[bool] = None
    status_code: Optional[str] = None
    sort_order: Optional[int] = None
    notes: Optional[str] = None


class WorkCreate(BaseModel):
    process_id: Optional[str] = None
    work_master_id: Optional[str] = None
    work_name: str
    work_date: date
    work_time_start: Optional[str] = None
    work_time_end: Optional[str] = None
    work_location: Optional[str] = None
    assigned_manager_id: Optional[str] = None
    subcontractor_id: Optional[str] = None
    special_work_type: Optional[str] = None
    hazard_codes: Optional[str] = None
    ppe_required: Optional[str] = None
    worker_count: Optional[int] = 0
    notes: Optional[str] = None


class WorkPatch(BaseModel):
    work_name: Optional[str] = None
    work_date: Optional[date] = None
    work_time_start: Optional[str] = None
    work_time_end: Optional[str] = None
    work_location: Optional[str] = None
    assigned_manager_id: Optional[str] = None
    subcontractor_id: Optional[str] = None
    special_work_type: Optional[str] = None
    hazard_codes: Optional[str] = None
    ppe_required: Optional[str] = None
    worker_count: Optional[int] = None
    status_code: Optional[str] = None
    notes: Optional[str] = None


class PtwPatch(BaseModel):
    ptw_status: str
    ptw_approved_by: Optional[str] = None


class WorkerCreate(BaseModel):
    user_id: Optional[str] = None
    worker_name: Optional[str] = None
    worker_phone: Optional[str] = None
    worker_type: Optional[str] = "SUBCON"
    subcontractor_id: Optional[str] = None
    role_code: Optional[str] = None
    join_date: Optional[date] = None
    certification_codes: Optional[str] = None
    safety_edu_date: Optional[date] = None
    safety_edu_hours: Optional[int] = 0
    notes: Optional[str] = None


class WorkerPatch(BaseModel):
    worker_name: Optional[str] = None
    worker_phone: Optional[str] = None
    worker_type: Optional[str] = None
    subcontractor_id: Optional[str] = None
    role_code: Optional[str] = None
    join_date: Optional[date] = None
    leave_date: Optional[date] = None
    certification_codes: Optional[str] = None
    health_check_date: Optional[date] = None
    health_check_result: Optional[str] = None
    safety_edu_date: Optional[date] = None
    safety_edu_hours: Optional[int] = None
    notes: Optional[str] = None


class EntryPatch(BaseModel):
    entry_status: str


class InspectionCreate(BaseModel):
    work_id: Optional[str] = None
    process_id: Optional[str] = None
    inspection_date: Optional[datetime] = None
    inspector_id: Optional[str] = None
    inspection_type: Optional[str] = "BEFORE_WORK"
    checklist_items: Optional[Any] = None
    overall_result: Optional[str] = None
    defect_count: Optional[int] = 0
    defect_items: Optional[Any] = None
    corrective_action: Optional[str] = None
    corrective_deadline: Optional[date] = None
    photo_urls: Optional[List[str]] = None
    notes: Optional[str] = None


class InspectionPatch(BaseModel):
    inspection_type: Optional[str] = None
    checklist_items: Optional[Any] = None
    overall_result: Optional[str] = None
    defect_count: Optional[int] = None
    defect_items: Optional[Any] = None
    corrective_action: Optional[str] = None
    corrective_deadline: Optional[date] = None
    photo_urls: Optional[List[str]] = None
    notes: Optional[str] = None


class CorrectivePatch(BaseModel):
    corrective_status: str
    corrective_action: Optional[str] = None


class SafetyManagerBody(BaseModel):
    site_type: str
    contract_amount: float
    total_workers: int
