from datetime import date, datetime
from typing import Annotated, Any, List, Optional, Union

from pydantic import AliasChoices, AfterValidator, BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt


# ── WO-SAFE-LEGAL-CST-CANONICAL-IMPLEMENT-001 STEP3: 작업 canonical numeric 전용 strict 경계 ──
#   NULL=unknown / 0=actual zero. bool·문자열·array·object·음수 거부. 기존 필드 coercion 불변.
def _work_canon_nonneg(v):
    if v is None:
        return v
    if v < 0:
        raise ValueError("0 이상이어야 합니다")
    return v


# StrictInt/StrictFloat: bool·numeric string·coercion 거부. AfterValidator: 음수 거부.
WorkCanonNum = Annotated[Union[StrictInt, StrictFloat], AfterValidator(_work_canon_nonneg)]


class SiteCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    company_id: Optional[str] = None
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
    site_address: Optional[str] = Field(None, validation_alias=AliasChoices("site_address", "address"))
    site_address_detail: Optional[str] = None
    site_sido: Optional[str] = None
    site_sigungu: Optional[str] = None
    latitude: Optional[float] = Field(None, description="WGS84 위도 (예: 37.5665)")
    longitude: Optional[float] = Field(None, description="WGS84 경도 (예: 126.9780)")
    start_date: Optional[date] = None
    end_date: Optional[date] = Field(None, validation_alias=AliasChoices("end_date", "planned_end_date"))
    manager_id: Optional[str] = None
    status_code: Optional[str] = "PLANNED"
    notes: Optional[str] = Field(None, validation_alias=AliasChoices("notes", "memo"))


class SitePatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    site_name: Optional[str] = None
    site_type: Optional[str] = None
    contract_amount: Optional[float] = None
    total_workers: Optional[int] = None
    direct_workers: Optional[int] = None
    subcon_workers: Optional[int] = None
    site_address: Optional[str] = Field(None, validation_alias=AliasChoices("site_address", "address"))
    site_address_detail: Optional[str] = None
    site_sido: Optional[str] = None
    site_sigungu: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = Field(None, validation_alias=AliasChoices("end_date", "planned_end_date"))
    manager_id: Optional[str] = None
    status_code: Optional[str] = None
    notes: Optional[str] = Field(None, validation_alias=AliasChoices("notes", "memo"))


class ProcessCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    process_master_id: Optional[str] = None
    kcsc_process_id: Optional[str] = None
    work_type_code: Optional[str] = None
    work_type_label: Optional[str] = None
    process_name: str
    construction_type: Optional[str] = None
    planned_start: Optional[date] = Field(None, validation_alias=AliasChoices("planned_start", "planned_start_date"))
    planned_end: Optional[date] = Field(None, validation_alias=AliasChoices("planned_end", "planned_end_date"))
    worker_count: Optional[int] = 0
    is_high_risk: Optional[bool] = Field(False, validation_alias=AliasChoices("is_high_risk", "is_hazardous"))
    sort_order: Optional[int] = 0
    notes: Optional[str] = Field(None, validation_alias=AliasChoices("notes", "memo"))


class ProcessPatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    process_name: Optional[str] = None
    kcsc_process_id: Optional[str] = None
    work_type_code: Optional[str] = None
    planned_start: Optional[date] = Field(None, validation_alias=AliasChoices("planned_start", "planned_start_date"))
    planned_end: Optional[date] = Field(None, validation_alias=AliasChoices("planned_end", "planned_end_date"))
    actual_start: Optional[date] = None
    actual_end: Optional[date] = None
    progress_rate: Optional[int] = None
    worker_count: Optional[int] = None
    is_high_risk: Optional[bool] = Field(None, validation_alias=AliasChoices("is_high_risk", "is_hazardous"))
    status_code: Optional[str] = None
    sort_order: Optional[int] = None
    notes: Optional[str] = Field(None, validation_alias=AliasChoices("notes", "memo"))


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
    # WO-CST-CANONICAL STEP3: 실제 작업 canonical 속성 5개(strict; default None). omitted/None→INSERT 부재, false/0→보존.
    work_height_m: Optional[WorkCanonNum] = None
    has_truck_loading_unloading: Optional[StrictBool] = None
    truck_loading_height_m: Optional[WorkCanonNum] = None
    has_manual_heavy_handling: Optional[StrictBool] = None
    manual_handling_weight_kg: Optional[WorkCanonNum] = None


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
    # WO-CST-CANONICAL STEP3: 실제 작업 canonical 속성 5개(strict; explicit-null clear는 라우터 sparse에서 처리).
    work_height_m: Optional[WorkCanonNum] = None
    has_truck_loading_unloading: Optional[StrictBool] = None
    truck_loading_height_m: Optional[WorkCanonNum] = None
    has_manual_heavy_handling: Optional[StrictBool] = None
    manual_handling_weight_kg: Optional[WorkCanonNum] = None


class PtwPatch(BaseModel):
    ptw_status: str
    ptw_approved_by: Optional[str] = None


class WorkerCreate(BaseModel):
    """건설 작업자 등록 입력 (LEDGER §19 통합).

    화면(construction-worker-list)이 보내는 필드명을 1급으로 받는다. 등록 시
    worker_registry(통합 명부) + construction_workers(현장배치)를 동시 생성하기 위한 입력이며,
    종전처럼 construction_workers 에만 직접 쓰지 않는다. 종전 서버 필드명
    (worker_phone·join_date·safety_edu_date·notes)도 alias 로 수용해 하위호환을 유지한다.
    """
    model_config = ConfigDict(populate_by_name=True)

    worker_name: str
    phone: Optional[str] = Field(default=None, validation_alias=AliasChoices("phone", "worker_phone"))
    worker_type: Optional[str] = "DIRECT"
    job_type: Optional[str] = None
    company_name: Optional[str] = None
    hire_date: Optional[date] = Field(default=None, validation_alias=AliasChoices("hire_date", "join_date"))
    safety_training_date: Optional[date] = Field(default=None, validation_alias=AliasChoices("safety_training_date", "safety_edu_date"))
    safety_training_hours: Optional[float] = Field(default=None, validation_alias=AliasChoices("safety_training_hours", "safety_edu_hours"))
    memo: Optional[str] = Field(default=None, validation_alias=AliasChoices("memo", "notes"))
    entry_status: Optional[str] = "OFFSITE"


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
