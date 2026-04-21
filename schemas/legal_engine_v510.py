from typing import List, Optional

from pydantic import BaseModel, Field


class DiagnoseStep2Body(BaseModel):
    factory_id: str
    diagnosis_id: Optional[str] = None
    processes: List[str] = Field(default_factory=list)
    construction_types: List[str] = Field(default_factory=list)
    construction_work_types: List[str] = Field(default_factory=list)
