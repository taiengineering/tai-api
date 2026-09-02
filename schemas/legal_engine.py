from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DiagnoseStep1Body(BaseModel):
    factory_id: Optional[str] = Field(None)
    sector: str = Field(...)
    input: Optional[Dict[str, Any]] = Field(default_factory=dict)
    building_use_type: Optional[str] = None
    employee_count: Optional[int] = None
    floor_area: Optional[float] = None
    worker_count: Optional[int] = None
    total_floor_area: Optional[float] = None
    electric_capacity: Optional[float] = None
    floor_count: Optional[int] = None
    contract_amount_eok: Optional[float] = Field(
        None,
        description="공사금액 단위: 억원(1억=100,000,000원). 예) 150억원 공사 → 150 입력. "
        "원화(원) 단위로 입력하면 판정 오류 발생.",
    )
    ksic_major: Optional[str] = None
    facility_type: Optional[str] = None
    elevator_count: Optional[int] = Field(None)
    gas_capacity_kg: Optional[float] = Field(None)
    gas_capacity_m3: Optional[float] = Field(None)
    boiler_capacity_kw: Optional[float] = Field(None)
    annual_energy_toe: Optional[float] = Field(None)
    has_high_pressure_gas: Optional[bool] = Field(None)
    has_boiler: Optional[bool] = Field(None)
    has_hazardous_material: Optional[bool] = Field(None)
    has_chemical_substance: Optional[bool] = Field(None)
    construction_type: Optional[str] = None
    direct_workers: Optional[int] = None
    subcon_workers: Optional[int] = None
    electrical_capacity_kw: Optional[float] = None
    has_tunnel_bridge: Optional[bool] = None
    has_blasting: Optional[bool] = None
    has_crane: Optional[bool] = None
    has_high_work: Optional[bool] = Field(None)


class DiagnoseStep2Body(BaseModel):
    factory_id: Optional[str] = None
    diagnosis_id: Optional[str] = None
    sector: Optional[str] = None
    construction_work_types: List[str] = Field(default_factory=list)
    work_type_codes: List[str] = Field(default_factory=list)
    kcsc_process_ids: List[str] = Field(default_factory=list)
    processes: List[Dict[str, Any]] = Field(default_factory=list)
    construction_types: List[str] = Field(default_factory=list)


class DiagnoseStep3Body(BaseModel):
    factory_id: str = Field(...)
    diagnosis_id: Optional[str] = None
    equipments: List[Dict[str, Any]] = Field(default_factory=list)
    kcsc_work_ids: List[str] = Field(default_factory=list)


# WO-DUAL-IND-STEP2-IMPLEMENT-001 GATE-4A: SAFE INDUSTRIAL 공식 LEG 진입 request.
# input = SAFE MANUFACTURING 화면에서 직접 확보 가능한 canonical field 13 (신규 alias 0).
# 기존 6(canonical exact 대응) + GATE-3 신규 7. UI None=미override(asset 유지), false/0/""=override.
class SafeIndustrialConsumerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ksic_major: Optional[str] = None
    worker_count: Optional[int] = None
    electric_capacity: Optional[float] = None
    has_high_pressure_gas: Optional[bool] = None
    has_chemical_substance: Optional[bool] = None
    has_boiler: Optional[bool] = None

    building_use_type: Optional[str] = None
    has_safety_manager: Optional[bool] = None
    work_height_m: Optional[float] = None
    has_truck_loading_unloading: Optional[bool] = None
    truck_loading_height_m: Optional[float] = None
    has_manual_heavy_handling: Optional[bool] = None
    manual_handling_weight_kg: Optional[float] = None


class SafeIndustrialLegBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factory_id: str
    input: SafeIndustrialConsumerInput


class SafeConstructionConsumerInput(BaseModel):
    """SAFE CONSTRUCTION 진단 시 사용자 명시 override(RUNTIME14). extra=forbid.
    None=미override, false/0=명시값. 위험작업/규제 boolean + numeric + has_subcontractor.
    """
    model_config = ConfigDict(extra="forbid")

    has_excavation: Optional[bool] = None
    has_demolition: Optional[bool] = None
    has_tower_crane: Optional[bool] = None
    has_confined_space: Optional[bool] = None
    has_asbestos_demo: Optional[bool] = None
    has_blasting: Optional[bool] = None
    has_diving: Optional[bool] = None
    work_height_m: Optional[float] = None
    has_truck_loading_unloading: Optional[bool] = None
    truck_loading_height_m: Optional[float] = None
    has_manual_heavy_handling: Optional[bool] = None
    manual_handling_weight_kg: Optional[float] = None
    has_chemical_substance: Optional[bool] = None
    has_subcontractor: Optional[bool] = None
    has_asbestos: Optional[bool] = None
    has_gas: Optional[bool] = None
    has_high_pressure_gas: Optional[bool] = None
    has_water_tank: Optional[bool] = None
    is_energy_intensive: Optional[bool] = None
    is_multi_use: Optional[bool] = None


class SafeConstructionLegBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str
    input: SafeConstructionConsumerInput
