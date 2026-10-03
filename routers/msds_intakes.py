"""MSDS Document Intake API — /me/msds/factories/{factory_id}/intakes."""
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services import msds_intake_svc as svc
from services.msds_product_svc import MsdsProductError

router = APIRouter(prefix="/me/msds", tags=["MSDS Intake"])


def _err(e: MsdsProductError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.detail})


def _require_user(current_user: dict) -> dict:
    if not current_user.get("id"):
        raise HTTPException(status_code=401, detail="사용자 식별에 실패했습니다.")
    return current_user


class NewProductBody(BaseModel):
    product_name: str
    manufacturer_name: Optional[str] = None

    class Config:
        extra = "forbid"


class ConfirmBody(BaseModel):
    existing_product_id: Optional[str] = None
    new_product: Optional[NewProductBody] = None
    selected_reference_candidate_ids: List[str] = []

    class Config:
        extra = "forbid"


class FinalizeBody(BaseModel):
    source_revision_date: Optional[str] = None
    source_revision_no: Optional[str] = None
    supplier_name: Optional[str] = None

    class Config:
        extra = "forbid"


@router.post("/factories/{factory_id}/intakes", status_code=201)
async def create_intake(
    factory_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    _require_user(current_user)
    sb = get_supabase()
    file_bytes = await file.read()
    try:
        result = svc.create_intake(
            sb=sb,
            current_user=current_user,
            factory_id=factory_id,
            file_bytes=file_bytes,
            file_name=file.filename or "msds.pdf",
            mime_type=file.content_type or "application/pdf",
        )
    except MsdsProductError as e:
        raise _err(e) from e
    status_code = 200 if result.get("duplicate") else 201
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=status_code, content={"status": "success", "data": result})


@router.get("/factories/{factory_id}/intakes/{intake_id}")
def get_intake(
    factory_id: str,
    intake_id: str,
    current_user: dict = Depends(get_current_user),
):
    _require_user(current_user)
    sb = get_supabase()
    try:
        intake = svc.get_intake(sb, current_user, factory_id, intake_id)
    except MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": intake}


@router.post("/factories/{factory_id}/intakes/{intake_id}/process")
def process_intake(
    factory_id: str,
    intake_id: str,
    current_user: dict = Depends(get_current_user),
):
    _require_user(current_user)
    sb = get_supabase()
    try:
        result = svc.process_intake(sb, current_user, factory_id, intake_id)
    except MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": result}


@router.get("/factories/{factory_id}/intakes/{intake_id}/facts")
def list_facts(
    factory_id: str,
    intake_id: str,
    current_user: dict = Depends(get_current_user),
):
    _require_user(current_user)
    sb = get_supabase()
    try:
        facts = svc.list_facts(sb, current_user, factory_id, intake_id)
    except MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": facts}


@router.get("/factories/{factory_id}/intakes/{intake_id}/candidates")
def list_candidates(
    factory_id: str,
    intake_id: str,
    current_user: dict = Depends(get_current_user),
):
    _require_user(current_user)
    sb = get_supabase()
    try:
        candidates = svc.list_candidates(sb, current_user, factory_id, intake_id)
    except MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": candidates}


@router.post("/factories/{factory_id}/intakes/{intake_id}/confirm")
def confirm_intake(
    factory_id: str,
    intake_id: str,
    body: ConfirmBody,
    current_user: dict = Depends(get_current_user),
):
    _require_user(current_user)
    sb = get_supabase()
    try:
        result = svc.confirm_intake(
            sb=sb,
            current_user=current_user,
            factory_id=factory_id,
            intake_id=intake_id,
            existing_product_id=body.existing_product_id,
            new_product=body.new_product.model_dump() if body.new_product else None,
            selected_reference_candidate_ids=body.selected_reference_candidate_ids,
        )
    except MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": result}


@router.post("/factories/{factory_id}/intakes/{intake_id}/finalize")
async def finalize_intake(
    factory_id: str,
    intake_id: str,
    body: FinalizeBody,
    current_user: dict = Depends(get_current_user),
):
    _require_user(current_user)
    sb = get_supabase()
    try:
        result = await svc.finalize_intake(
            sb=sb,
            current_user=current_user,
            factory_id=factory_id,
            intake_id=intake_id,
            source_revision_date=body.source_revision_date,
            source_revision_no=body.source_revision_no,
            supplier_name=body.supplier_name,
        )
    except MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": result}
