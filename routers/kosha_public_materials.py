"""Public read-only KOSHA stored-material display — WP-2 + WP-3.

GET /public/kosha/materials
GET /public/kosha/materials/stats
GET /public/kosha/materials/{material_id}

List/stats: latest COMPLETED snapshot membership only. No KOSHA, no R2, no DML.
Detail: WP-2 contract frozen (SELECT + R2 GET presign only).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from services.kosha_safety_materials.display import (
    CurrentSnapshotUnavailable,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    SupabaseDisplayStore,
    list_current_materials,
    load_public_material,
    stats_current_materials,
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


@router.get("/materials")
def list_public_materials(
    q: str = "",
    cat: str = "ALL",
    sec: str = "ALL",
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    try:
        return list_current_materials(
            get_store(),
            q=q,
            cat=cat,
            sec=sec,
            page=page,
            page_size=page_size,
        )
    except CurrentSnapshotUnavailable:
        raise HTTPException(status_code=503, detail="CURRENT_SNAPSHOT_UNAVAILABLE")


@router.get("/materials/stats")
def stats_public_materials():
    try:
        return stats_current_materials(get_store())
    except CurrentSnapshotUnavailable:
        raise HTTPException(status_code=503, detail="CURRENT_SNAPSHOT_UNAVAILABLE")


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
