"""Runtime Evaluator 스키마 v1.0.0"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class EvaluationContextIn(BaseModel):
    company_id: Optional[str] = None
    facility_id: Optional[str] = None
    industry_code: Optional[str] = None
    worker_count: Optional[int] = None
    hazardous_materials: List[str] = []
    equipment: List[str] = []
    pressure_vessels: List[str] = []
    fire_facilities: List[str] = []
    contractors: List[str] = []
    process_types: List[str] = []
    accident_occurred: bool = False
    construction_started: bool = False
    shutdown: bool = False
    additional_inputs: Dict[str, Any] = {}
    created_by: Optional[str] = None

class EvaluateIn(BaseModel):
    context_id: str
