"""TAM-008B — Approval Route Foundation router.

All write endpoints are fail-closed (403 ROUTE_MANAGER_PERMISSION_REQUIRED)
until the authorization bootstrap (OD-01 OWNER_DECISION_REQUIRED) is resolved.
Read endpoints are open to authenticated users.

Design contract: docs/TAI_WO_TAM_006_DESIGN_CONSOLIDATION.md §6
"""
from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from routers.auth import get_current_user
from services.tam.routes_svc import TamError, create_route, create_version
from services.tam.routes_svc import create_step, create_assignee, publish_version
from services.tam.routes_svc import get_route, list_routes

router = APIRouter(prefix="/v1/tam", tags=["tam"])


def _ok(data: Any) -> dict:
    return {"status": "success", "data": data}


def _raise(err: TamError) -> None:
    raise HTTPException(
        status_code=err.http_status,
        detail={"code": err.code, "message": err.message},
    )


def _require_route_manager(user: dict) -> None:
    """Fail-closed: ROUTE_MANAGER permission ledger is OWNER_DECISION_REQUIRED.
    No user can manage routes until the authorization bootstrap is authorized."""
    raise HTTPException(
        status_code=403,
        detail={
            "code": "ROUTE_MANAGER_PERMISSION_REQUIRED",
            "message": "Route management requires ROUTE_MANAGER permission "
                       "(authorization bootstrap pending owner decision OD-01)",
        },
    )


# ── Request models ─────────────────────────────────────────────────────────────

class RouteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: str
    factory_id: Optional[str] = None
    route_scope: Literal["COMPANY_DEFAULT", "FACTORY_DEFAULT", "DOCUMENT_TYPE", "PROCESS_TYPE"]
    scope_key: Optional[str] = None
    display_name: str


class VersionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: Optional[str] = None


class StepCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_order: int
    step_name: str
    step_type: Literal["SEQUENTIAL", "PARALLEL_ANY", "PARALLEL_ALL"]
    allow_supplement: bool = False


class AssigneeCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/routes")
async def list_routes_endpoint(
    company_id: str = Query(...),
    factory_id: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    user: dict = Depends(get_current_user),
) -> dict:
    try:
        result = list_routes(user, company_id=company_id,
                             factory_id=factory_id, is_active=is_active)
        return _ok(result)
    except TamError as err:
        _raise(err)


@router.get("/routes/{route_id}")
async def get_route_endpoint(
    route_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    try:
        return _ok(get_route(user, route_id=route_id))
    except TamError as err:
        _raise(err)


@router.post("/routes", status_code=201)
async def create_route_endpoint(
    body: RouteCreateRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    _require_route_manager(user)  # always 403 until OD-01 resolved


@router.post("/routes/{route_id}/versions", status_code=201)
async def create_version_endpoint(
    route_id: str,
    body: VersionCreateRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    _require_route_manager(user)


@router.post("/routes/{route_id}/versions/{version_id}/steps", status_code=201)
async def create_step_endpoint(
    route_id: str,
    version_id: str,
    body: StepCreateRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    _require_route_manager(user)


@router.post("/routes/{route_id}/versions/{version_id}/steps/{step_id}/assignees",
             status_code=201)
async def create_assignee_endpoint(
    route_id: str,
    version_id: str,
    step_id: str,
    body: AssigneeCreateRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    _require_route_manager(user)


@router.post("/routes/{route_id}/versions/{version_id}/publish")
async def publish_version_endpoint(
    route_id: str,
    version_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    _require_route_manager(user)
