"""MSDS Barcode / QR Scan Resolver API — /me/msds/factories/{factory_id}/scans/resolve."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services import msds_scan_svc as svc
from services.msds_product_svc import MsdsProductError

router = APIRouter(prefix="/me/msds", tags=["MSDS Scan"])


def _err(e: MsdsProductError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.detail})


def _require_user(current_user: dict) -> dict:
    if not current_user.get("id"):
        raise HTTPException(status_code=401, detail="사용자 식별에 실패했습니다.")
    return current_user


class ScanResolveBody(BaseModel):
    scan_kind: str
    raw_value: str
    symbology: Optional[str] = None

    class Config:
        extra = "forbid"


@router.post("/factories/{factory_id}/scans/resolve")
def resolve_scan(
    factory_id: str,
    body: ScanResolveBody,
    current_user: dict = Depends(get_current_user),
):
    _require_user(current_user)
    sb = get_supabase()
    try:
        result = svc.resolve_scan(
            sb=sb,
            current_user=current_user,
            factory_id=factory_id,
            scan_kind=body.scan_kind,
            raw_value=body.raw_value,
            symbology=body.symbology,
        )
    except MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": result}
