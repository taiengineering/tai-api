"""WO-008: Deliverable B — factory legal-classification routes.

GET  /factories/{factory_id}/legal-classification
POST /factories/{factory_id}/legal-classification/confirm

Dedicated authorized routes. Not a side effect of PATCH /factories/{id}.
Existing GET/PATCH /factories/{id} semantics unchanged.

Order: AUTH -> _ensure_factory_own -> company/sector ownership ->
       read/validate -> conditional insert/update -> server audit.
"""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _ensure_factory_own
from services.factory_legal_classification_svc import (
    get_factory_legal_classification,
    confirm_factory_legal_classification,
)

router = APIRouter(prefix="/factories", tags=["factory-legal-classification"])


class FactoryLegalClassificationConfirmBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appendix3_item_no: Annotated[StrictInt, Field(ge=1, le=49)]
    is_real_estate_management: Optional[StrictBool] = None
    # confirmed_sector: must match factory's actual sector (server validates).
    confirmed_sector: str
    # expected_revision: None for first insert; positive StrictInt for update (CAS).
    expected_revision: Optional[Annotated[StrictInt, Field(ge=1)]] = None
    # confirm_deliberate: explicit opt-in flag (must be true). Guards against accidental confirm.
    confirm_deliberate: StrictBool

    @model_validator(mode="after")
    def _confirm_deliberate_required(self) -> "FactoryLegalClassificationConfirmBody":
        if not self.confirm_deliberate:
            raise ValueError("confirm_deliberate must be true to proceed with confirmation")
        return self


@router.get("/{factory_id}/legal-classification")
async def get_legal_classification(
    factory_id: str,
    authorization: Optional[str] = Header(None),
):
    """Read current legal classification. Returns status=UNCONFIRMED if no record."""
    supabase = get_supabase()
    current = get_current_user(authorization)
    _ensure_factory_own(supabase, factory_id, current)
    record = get_factory_legal_classification(supabase, factory_id)
    if record is None:
        return {"factory_id": factory_id, "classification": None, "status": "UNCONFIRMED"}
    return {"factory_id": factory_id, "classification": record, "status": "CONFIRMED"}


@router.post("/{factory_id}/legal-classification/confirm")
async def confirm_legal_classification(
    factory_id: str,
    body: FactoryLegalClassificationConfirmBody,
    authorization: Optional[str] = Header(None),
):
    """Confirm or update factory legal classification.

    First confirm: omit expected_revision.
    Update: provide expected_revision matching current revision (CAS).
    confirmed_by is always taken from the auth token — never from client body.
    """
    supabase = get_supabase()
    current = get_current_user(authorization)
    _ensure_factory_own(supabase, factory_id, current)
    confirmed_by = str(current.get("id") or "")
    if not confirmed_by:
        raise HTTPException(status_code=403, detail="사용자 ID를 확인할 수 없습니다")
    record = confirm_factory_legal_classification(
        supabase,
        factory_id=factory_id,
        appendix3_item_no=body.appendix3_item_no,
        is_real_estate_management=body.is_real_estate_management,
        confirmed_sector=body.confirmed_sector,
        expected_revision=body.expected_revision,
        confirmed_by=confirmed_by,
    )
    return {"factory_id": factory_id, "classification": record}
