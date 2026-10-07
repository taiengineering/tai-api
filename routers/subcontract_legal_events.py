"""
Subcontract Legal Event API
Art.35~37 건설산업기본법 하도급 법적 이벤트 source management.
DRAFT → CONFIRMED → VOID lifecycle. Hard DELETE = 0.
"""
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from routers.subcontractors import _ensure_sub_own, _ensure_site_own
from services.subcontract_legal_event_source.store import (
    list_events,
    create_draft,
    update_draft,
    confirm_event,
    void_event,
)

router = APIRouter(
    prefix="/construction/subcontractors",
    tags=["subcontract-legal-events"],
)


class LegalEventCreate(BaseModel):
    event_type: str
    obligated_actor_company_id: Optional[str] = None
    counterparty_company_id: Optional[str] = None
    occurred_at: Optional[str] = None
    basis_type: Optional[str] = None
    adjustment_reason: Optional[str] = None
    original_amount: Optional[float] = None
    adjusted_amount: Optional[float] = None
    notice_type: Optional[str] = None
    notice_received_at: Optional[str] = None
    inspection_completed_at: Optional[str] = None
    design_conformance_confirmed: Optional[bool] = None
    notice_event_id: Optional[str] = None
    scope_description: Optional[str] = None
    evidence_ref: Optional[str] = None


class LegalEventPatch(BaseModel):
    obligated_actor_company_id: Optional[str] = None
    counterparty_company_id: Optional[str] = None
    occurred_at: Optional[str] = None
    basis_type: Optional[str] = None
    adjustment_reason: Optional[str] = None
    original_amount: Optional[float] = None
    adjusted_amount: Optional[float] = None
    notice_type: Optional[str] = None
    notice_received_at: Optional[str] = None
    inspection_completed_at: Optional[str] = None
    design_conformance_confirmed: Optional[bool] = None
    notice_event_id: Optional[str] = None
    scope_description: Optional[str] = None
    evidence_ref: Optional[str] = None


# ── GET /construction/subcontractors/{subcontractor_id}/legal-events ──────────
@router.get("/{subcontractor_id}/legal-events")
async def list_legal_events(
    subcontractor_id: UUID,
    current: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    sb = get_supabase()
    _ensure_sub_own(sb, subcontractor_id, current)
    # resolve site_id from subcontractor row
    sub_r = sb.table("subcontractors").select("site_id").eq("id", str(subcontractor_id)).limit(1).execute()
    if not sub_r.data:
        raise HTTPException(404, "하도급업체를 찾을 수 없습니다.")
    site_id = str(sub_r.data[0]["site_id"])
    items = list_events(sb, site_id=site_id, subcontractor_id=str(subcontractor_id))
    return {"status": "success", "data": {"items": items}}


# ── POST /construction/subcontractors/{subcontractor_id}/legal-events ─────────
@router.post("/{subcontractor_id}/legal-events")
async def create_legal_event(
    subcontractor_id: UUID,
    body: LegalEventCreate,
    current: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    sb = get_supabase()
    _ensure_sub_own(sb, subcontractor_id, current)
    sub_r = sb.table("subcontractors").select("site_id").eq("id", str(subcontractor_id)).limit(1).execute()
    if not sub_r.data:
        raise HTTPException(404, "하도급업체를 찾을 수 없습니다.")
    site_id = str(sub_r.data[0]["site_id"])
    created_by = current.get("id") or current.get("user_id")
    row = create_draft(
        sb,
        site_id=site_id,
        subcontractor_id=str(subcontractor_id),
        body=body.model_dump(exclude_none=False),
        created_by=str(created_by) if created_by else None,
    )
    return {"status": "success", "data": row}


# ── PATCH /construction/subcontractors/{subcontractor_id}/legal-events/{event_id} ──
@router.patch("/{subcontractor_id}/legal-events/{event_id}")
async def patch_legal_event(
    subcontractor_id: UUID,
    event_id: UUID,
    body: LegalEventPatch,
    current: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    sb = get_supabase()
    _ensure_sub_own(sb, subcontractor_id, current)
    row = update_draft(sb, event_id=str(event_id), body=body.model_dump(exclude_none=True))
    return {"status": "success", "data": row}


# ── POST /construction/subcontractors/{subcontractor_id}/legal-events/{event_id}/confirm ──
@router.post("/{subcontractor_id}/legal-events/{event_id}/confirm")
async def confirm_legal_event(
    subcontractor_id: UUID,
    event_id: UUID,
    current: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    sb = get_supabase()
    _ensure_sub_own(sb, subcontractor_id, current)
    row = confirm_event(sb, event_id=str(event_id))
    return {"status": "success", "data": row}


# ── POST /construction/subcontractors/{subcontractor_id}/legal-events/{event_id}/void ──
@router.post("/{subcontractor_id}/legal-events/{event_id}/void")
async def void_legal_event(
    subcontractor_id: UUID,
    event_id: UUID,
    current: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    sb = get_supabase()
    _ensure_sub_own(sb, subcontractor_id, current)
    row = void_event(sb, event_id=str(event_id))
    return {"status": "success", "data": row}
