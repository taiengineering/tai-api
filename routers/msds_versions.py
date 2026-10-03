"""MSDS Customer Original Version API — /me/msds/factories/{factory_id}/products/{product_id}/versions.

factory_id Canonical Scope. 7 endpoints.
DELETE 없음. VOID로 처리.
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services import msds_version_svc as svc
from services.msds_product_svc import MsdsProductError

router = APIRouter(prefix="/me/msds", tags=["MSDS 원본 버전"])


# ─── Request Schemas ──────────────────────────────────────────────────────────

class VoidBody(BaseModel):
    reason: str

    class Config:
        extra = "forbid"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _err(e: MsdsProductError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.detail})


def _require_user(current_user: dict) -> dict:
    if not current_user.get("id"):
        raise HTTPException(status_code=401, detail="사용자 식별에 실패했습니다.")
    return current_user


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/factories/{factory_id}/products/{product_id}/versions")
def list_versions(
    factory_id: str,
    product_id: str,
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    _require_user(current_user)
    sb = get_supabase()
    try:
        items, total = svc.list_versions(sb, current_user, factory_id, product_id,
                                          status=status, limit=limit, offset=offset)
    except MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": {"items": items, "total": total}}


@router.get("/factories/{factory_id}/products/{product_id}/versions/current")
def get_current_version(
    factory_id: str,
    product_id: str,
    current_user: dict = Depends(get_current_user),
):
    _require_user(current_user)
    sb = get_supabase()
    try:
        version = svc.get_current_version(sb, current_user, factory_id, product_id)
    except MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": version}


@router.get("/factories/{factory_id}/products/{product_id}/versions/{version_id}")
def get_version(
    factory_id: str,
    product_id: str,
    version_id: str,
    current_user: dict = Depends(get_current_user),
):
    _require_user(current_user)
    sb = get_supabase()
    try:
        version = svc.get_version(sb, current_user, factory_id, product_id, version_id)
    except MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": version}


@router.post("/factories/{factory_id}/products/{product_id}/versions", status_code=201)
async def create_version(
    factory_id: str,
    product_id: str,
    file: UploadFile = File(...),
    source_revision_date: Optional[str] = Form(None),
    source_revision_no: Optional[str] = Form(None),
    supplier_name: Optional[str] = Form(None),
    response: Response = None,
    current_user: dict = Depends(get_current_user),
):
    _require_user(current_user)
    sb = get_supabase()
    file_bytes = await file.read()
    try:
        version, rpc_status = await svc.create_version(
            sb=sb,
            current_user=current_user,
            factory_id=factory_id,
            product_id=product_id,
            file_bytes=file_bytes,
            file_name=file.filename or "msds.pdf",
            mime_type=file.content_type or "application/pdf",
            source_revision_date=source_revision_date,
            source_revision_no=source_revision_no,
            supplier_name=supplier_name,
        )
    except MsdsProductError as e:
        raise _err(e) from e

    if rpc_status == "NO_CHANGE" and response is not None:
        response.status_code = 200
    return {"status": "success", "data": version, "result": rpc_status}


@router.post("/factories/{factory_id}/products/{product_id}/versions/{version_id}/make-current")
def make_current(
    factory_id: str,
    product_id: str,
    version_id: str,
    current_user: dict = Depends(get_current_user),
):
    _require_user(current_user)
    sb = get_supabase()
    try:
        version = svc.make_current(sb, current_user, factory_id, product_id, version_id)
    except MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": version}


@router.post("/factories/{factory_id}/products/{product_id}/versions/{version_id}/void")
def void_version(
    factory_id: str,
    product_id: str,
    version_id: str,
    body: VoidBody,
    current_user: dict = Depends(get_current_user),
):
    _require_user(current_user)
    sb = get_supabase()
    try:
        version = svc.void_version(
            sb, current_user, factory_id, product_id, version_id, body.reason
        )
    except MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": version}


@router.get("/factories/{factory_id}/products/{product_id}/versions/{version_id}/download-url")
async def get_download_url(
    factory_id: str,
    product_id: str,
    version_id: str,
    current_user: dict = Depends(get_current_user),
):
    _require_user(current_user)
    sb = get_supabase()
    try:
        result = await svc.get_download_url(sb, current_user, factory_id, product_id, version_id)
    except MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": result}
