"""MSDS Chemical Product API — /me/msds/products.

company_id 는 Bearer 토큰(get_current_user)에서만 파생.
client 가 company_id 를 보낼 수 없다(Pydantic extra=forbid).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services import msds_product_svc as svc

router = APIRouter(prefix="/me/msds", tags=["MSDS 화학제품"])


# ─── Request Schemas ──────────────────────────────────────────────────────────

class IdentifierBody(BaseModel):
    identifier_type: str
    identifier_value: str
    issuer_name: Optional[str] = None
    is_primary: bool = False

    class Config:
        extra = "forbid"


class ProductCreateBody(BaseModel):
    product_name: str
    manufacturer_name: Optional[str] = None
    identifiers: Optional[List[IdentifierBody]] = None

    class Config:
        extra = "forbid"


class ProductUpdateBody(BaseModel):
    product_name: Optional[str] = None
    manufacturer_name: Optional[str] = None
    identity_status: Optional[str] = None

    class Config:
        extra = "forbid"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _err(e: svc.MsdsProductError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.detail})


def _require_user(current_user: dict) -> dict:
    if not current_user.get("id"):
        raise HTTPException(status_code=401, detail="사용자 식별에 실패했습니다.")
    return current_user


# ─── Product Endpoints ────────────────────────────────────────────────────────

@router.get("/products")
def list_products(
    status: Optional[str] = Query(None),
    identity_status: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    _require_user(current_user)
    sb = get_supabase()
    try:
        data = svc.list_products(sb, current_user, status=status,
                                  identity_status=identity_status, q=q,
                                  limit=limit, offset=offset)
    except svc.MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": data}


@router.post("/products", status_code=201)
def create_product(
    body: ProductCreateBody,
    current_user: dict = Depends(get_current_user),
):
    _require_user(current_user)
    sb = get_supabase()
    identifiers = [i.dict() for i in body.identifiers] if body.identifiers else None
    try:
        product, candidates = svc.create_product(
            sb, current_user,
            product_name=body.product_name,
            manufacturer_name=body.manufacturer_name,
            identifiers=identifiers,
            created_source="MANUAL",
        )
    except svc.MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": product, "duplicate_candidates": candidates}


@router.get("/products/{product_id}")
def get_product(product_id: str, current_user: dict = Depends(get_current_user)):
    _require_user(current_user)
    sb = get_supabase()
    try:
        product = svc.get_product(sb, current_user, product_id)
    except svc.MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": product}


@router.patch("/products/{product_id}")
def update_product(
    product_id: str,
    body: ProductUpdateBody,
    current_user: dict = Depends(get_current_user),
):
    _require_user(current_user)
    sb = get_supabase()
    patch = body.dict(exclude_unset=True)
    try:
        product = svc.update_product(sb, current_user, product_id, patch)
    except svc.MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": product}


@router.post("/products/{product_id}/deactivate")
def deactivate_product(product_id: str, current_user: dict = Depends(get_current_user)):
    _require_user(current_user)
    sb = get_supabase()
    try:
        product = svc.deactivate_product(sb, current_user, product_id)
    except svc.MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": product}


@router.post("/products/{product_id}/reactivate")
def reactivate_product(product_id: str, current_user: dict = Depends(get_current_user)):
    _require_user(current_user)
    sb = get_supabase()
    try:
        product = svc.reactivate_product(sb, current_user, product_id)
    except svc.MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": product}


# ─── Identifier Endpoints ─────────────────────────────────────────────────────

@router.get("/products/{product_id}/identifiers")
def list_identifiers(product_id: str, current_user: dict = Depends(get_current_user)):
    _require_user(current_user)
    sb = get_supabase()
    try:
        items = svc.list_identifiers(sb, current_user, product_id)
    except svc.MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": {"items": items, "total": len(items)}}


@router.post("/products/{product_id}/identifiers", status_code=201)
def add_identifier(
    product_id: str,
    body: IdentifierBody,
    current_user: dict = Depends(get_current_user),
):
    _require_user(current_user)
    sb = get_supabase()
    payload = body.dict()
    payload["created_source"] = "MANUAL"
    try:
        ident = svc.add_identifier(sb, current_user, product_id, payload)
    except svc.MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": ident}


@router.delete("/products/{product_id}/identifiers/{identifier_id}")
def deactivate_identifier(
    product_id: str,
    identifier_id: str,
    current_user: dict = Depends(get_current_user),
):
    _require_user(current_user)
    sb = get_supabase()
    try:
        ident = svc.deactivate_identifier(sb, current_user, product_id, identifier_id)
    except svc.MsdsProductError as e:
        raise _err(e) from e
    return {"status": "success", "data": ident}
