"""store_asset_original sequence — WP-1C-5A mock-verified. live PUT/KOSHA binary = 0 this WP."""
from __future__ import annotations

from typing import Callable, Optional

from .binary_fetch import BinaryFetchError, assert_binary_allowed
from .r2_store import R2Error, R2Store
from .storage_keys import content_checksum, object_key, source_asset_key
from .version_service import VersionError


class StorageError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def assert_current_member(material_id: str, membership_ids: set[str]) -> None:
    if material_id not in membership_ids:
        raise StorageError("HISTORICAL_STORAGE_FORBIDDEN")


def store_asset_original(
    *,
    kogl_type: str,
    content_type: str,
    material_id: str,
    atcfl_no: str,
    atcfl_seq,
    file_name: str,
    mime_type: str | None = None,
    membership_ids: Optional[set[str]] = None,
    fetch_fn: Callable,
    r2: R2Store,
    versions,
    version_payload: dict,
    dry_run: bool = False,
) -> dict:
    """license → key → fetch → SHA → HEAD → PUT if absent → read-back → promote.

    dry_run: KOSHA GET 0, R2 PUT 0, version DML 0.
    """
    if membership_ids is not None:
        assert_current_member(material_id, membership_ids)
    assert_binary_allowed(kogl_type, content_type)
    sak = source_asset_key(material_id, atcfl_no, atcfl_seq, file_name)
    if dry_run:
        return {
            "status": "DRY_RUN",
            "source_asset_key": sak,
            "kosha_binary_get": 0,
            "r2_put": 0,
            "version_dml": 0,
        }
    fetched = fetch_fn(
        kogl_type=kogl_type,
        content_type=content_type,
        atcfl_no=atcfl_no,
        atcfl_seq=atcfl_seq,
        file_name=file_name,
        mime_type=mime_type,
    )
    data = fetched["data"] if isinstance(fetched, dict) and "data" in fetched else None
    if data is None:
        path = fetched.get("dest_path")
        with open(path, "rb") as f:
            data = f.read()
    sha = fetched.get("sha256") or content_checksum(data)
    if sha != content_checksum(data):
        raise StorageError("SOURCE_SHA_MISMATCH")
    key = object_key(material_id, sak, sha, file_name)
    try:
        put_status = r2.put_new(
            key, data,
            content_type=mime_type or fetched.get("content_type") or "application/octet-stream",
            source_asset_key=sak,
            material_id=material_id,
            content_sha256=sha,
        )
        if put_status == "PUT":
            r2.readback_verify(key, sha)
    except R2Error as e:
        if e.code == "READBACK_MISMATCH":
            raise StorageError("READBACK_MISMATCH") from e
        if e.code == "VERSION_OBJECT_MISSING":
            raise StorageError("VERSION_OBJECT_MISSING") from e
        raise StorageError(e.code, e.message) from e
    payload = dict(version_payload)
    payload["source_asset_key"] = sak
    payload["content_checksum"] = sha
    payload["storage_key"] = key
    payload["storage_provider"] = "R2"
    payload["storage_bucket"] = r2.bucket
    payload["material_id"] = material_id
    payload["is_derivative"] = False
    try:
        promo = versions.promote(payload)
    except VersionError as e:
        raise StorageError("ORPHAN_OBJECT_CANDIDATE", e.code) from e
    return {
        "status": promo["status"],
        "source_asset_key": sak,
        "content_checksum": sha,
        "storage_key": key,
        "put": put_status,
        "promote": promo,
    }
