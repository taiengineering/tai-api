"""Persistence 스키마 v1.0.0"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class SnapshotIn(BaseModel):
    facility_id: str
    evaluation_context_id: Optional[str] = None

class ReEvalIn(BaseModel):
    facility_id: str
    trigger_type: str
    trigger_detail: Dict[str, Any] = {}

class DriftCheckIn(BaseModel):
    facility_id: str

class ScheduleInstanceIn(BaseModel):
    facility_id: str
    schedule_type: str
    schedule_key: str
    next_due_date: Optional[str] = None
    schedule_activation_id: Optional[str] = None
