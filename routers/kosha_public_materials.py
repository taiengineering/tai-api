"""Public read-only KOSHA stored-material display — WP-2.

GET /public/kosha/materials/{material_id}
DB SELECT + R2 GET presign only. No KOSHA fetch, no PUT/DELETE, no DML.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from services.kosha_safety_materials.display import (
    SupabaseDisplayStore,
    load_public_material,
)
from services.kosha_safety_materials.storage.r2_store import (
    R2Error,
    credentials_from_env,
    make_s3_client,
)
from services.kosha_safety_materials.storage.signed_url import R2GetSigner

router = APIRouter(prefix="/public/kosha", tags=["KOSHA public"])

_store = None
_signer = None


def get_store():
    global _store
    if _store is None:
        _store = SupabaseDisplayStore()
    return _store


def get_signer():
    global _signer
    if _signer is None:
        creds = credentials_from_env()
        _signer = R2GetSigner(make_s3_client(creds))
    return _signer


@router.get("/materials/{material_id}")
def get_public_material(material_id: str):
    try:
        body = load_public_material(material_id, store=get_store(), signer=get_signer())
    except R2Error as e:
        if e.code == "R2_INTEGRATION_BLOCKED":
            raise HTTPException(status_code=503, detail="STORAGE_UNAVAILABLE") from e
        raise
    if body is None:
        raise HTTPException(status_code=404, detail="MATERIAL_NOT_FOUND")
    return body
