from datetime import date
from typing import Optional

from pydantic import BaseModel


class AssetPatchBody(BaseModel):
    last_inspection_date: Optional[date] = None
    next_inspection_date: Optional[date] = None
    equipment_model_id: Optional[str] = None
    model_id: Optional[str] = None
    is_legal_target: Optional[bool] = None
    is_operating: Optional[bool] = None
    repair_date: Optional[str] = None
