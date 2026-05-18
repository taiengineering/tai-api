"""Legal Adapter API — Project legal engine results to runtime tasks.

Registered in router_registry/runtime_bridge.py
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from services.legal_adapter import project_rules

router = APIRouter(prefix="/runtime/legal-adapter", tags=["runtime"])


class ProjectRequest(BaseModel):
    tenant_id: str
    facility_id: str
    matched_rules: list[dict] = Field(..., min_length=1)
    trace_id: Optional[str] = None


@router.post("/project")
async def project_legal_rules(body: ProjectRequest):
    try:
        result = await project_rules(
            tenant_id=body.tenant_id,
            facility_id=body.facility_id,
            matched_rules=body.matched_rules,
            trace_id=body.trace_id,
        )
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
