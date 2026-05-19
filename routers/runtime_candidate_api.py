"""Runtime Candidate API — CRUD + Activate for 점검항목관리.

Registered in router_registry/runtime_bridge.py
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from db.supabase_client import get_supabase
from services.runtime_activation_service import activate_candidate

router = APIRouter(prefix="/runtime/candidates", tags=["runtime-candidate"])


# ----- List -----
@router.get("")
async def list_candidates(
    tenant_id: str = Query(...),
    facility_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    candidate_type: Optional[str] = Query(None),
    source_engine: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    sb = get_supabase()
    q = sb.table("runtime_candidate").select(
        "*, runtime_candidate_document_req(id, document_type, title), "
        "runtime_candidate_evidence_req(id, evidence_type, title), "
        "runtime_candidate_schedule(id, schedule_type, recurrence_rule, suggested_due_date)"
    ).eq("tenant_id", tenant_id)
    if facility_id:
        q = q.eq("facility_id", facility_id)
    if status:
        q = q.eq("status", status)
    if candidate_type:
        q = q.eq("candidate_type", candidate_type)
    if source_engine:
        q = q.eq("source_engine", source_engine)
    q = q.order("created_at", desc=True).range(offset, offset + limit - 1)
    res = q.execute()
    return {"ok": True, "candidates": res.data or [], "count": len(res.data or [])}


# ----- Get -----
@router.get("/{candidate_id}")
async def get_candidate(candidate_id: str):
    sb = get_supabase()
    res = sb.table("runtime_candidate").select(
        "*, runtime_candidate_document_req(*), "
        "runtime_candidate_evidence_req(*), "
        "runtime_candidate_schedule(*)"
    ).eq("id", candidate_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"ok": True, "candidate": res.data[0]}


# ----- Patch -----
class CandidateUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None  # pending_review, approved, rejected


@router.patch("/{candidate_id}")
async def update_candidate(candidate_id: str, body: CandidateUpdateRequest):
    sb = get_supabase()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "status" in updates and updates["status"] not in ("pending_review", "approved", "rejected"):
        raise HTTPException(status_code=400, detail="Invalid status transition")
    res = sb.table("runtime_candidate").update(updates).eq("id", candidate_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"ok": True, "candidate": res.data[0]}


# ----- Activate -----
class ActivateRequest(BaseModel):
    assignee_id: Optional[str] = None
    recurrence_rule: Optional[str] = None
    next_due_date: Optional[str] = None
    custom_title: Optional[str] = None
    custom_description: Optional[str] = None
    selected_document_ids: list[str] = Field(default_factory=list)
    selected_evidence_ids: list[str] = Field(default_factory=list)


@router.post("/{candidate_id}/activate")
async def activate(candidate_id: str, body: ActivateRequest):
    try:
        result = await activate_candidate(
            candidate_id=candidate_id,
            assignee_id=body.assignee_id,
            recurrence_rule=body.recurrence_rule,
            next_due_date=body.next_due_date,
            custom_title=body.custom_title,
            custom_description=body.custom_description,
            selected_document_ids=body.selected_document_ids,
            selected_evidence_ids=body.selected_evidence_ids,
        )
        return {"ok": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
