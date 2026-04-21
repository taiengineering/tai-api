from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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
