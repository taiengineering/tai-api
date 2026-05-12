"""Simulation 스키마 v1.0.0"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class ScenarioIn(BaseModel):
    scenario_name: str
    industry_code: Optional[str] = None
    worker_count: Optional[int] = None
    hazardous_materials: List[str] = []
    pressure_vessels: List[str] = []
    fire_facilities: List[str] = []
    contractor_exists: bool = False
    construction_started: bool = False
    accident_occurred: bool = False
    shutdown: bool = False
    facility_types: List[str] = []
    equipment: List[str] = []
    additional_inputs: Dict[str, Any] = {}
    created_by: Optional[str] = None

class RunSimulationIn(BaseModel):
    scenario_id: str
