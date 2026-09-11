"""Atomic asset_versions promotion — WP-1C-5A/5B.

MemoryVersionStore = tests only. Production = SupabaseVersionStore RPC.
"""
from __future__ import annotations

import threading
from typing import Any, Optional

VERSION_IMMUTABLE = (
    "content_checksum", "storage_key", "source_file_name", "source_file_size",
    "license_observed_at", "license_observed_type", "storage_basis",
)

RPC_FUNCTION = "promote_kosha_safety_material_asset_version"
ALLOWED_PROMOTION = frozenset({"NO_CHANGE", "NEW_VERSION", "PROMOTED_EXISTING_VERSION"})
RPC_PARAM_NAMES = (
    "p_asset_id", "p_material_id", "p_source_asset_key", "p_content_checksum",
    "p_storage_provider", "p_storage_bucket", "p_storage_key",
    "p_source_file_name", "p_source_content_type", "p_source_file_size",
    "p_source_fetched_at", "p_is_derivative", "p_license_observed_at",
    "p_license_observed_type", "p_license_name", "p_license_source_url",
    "p_storage_basis", "p_source_med_seq", "p_source_url",
    "p_med_gonggongnuri_raw", "p_med_gonggongnuri_nm_raw",
)
PAYLOAD_TO_RPC = {
    "asset_id": "p_asset_id",
    "material_id": "p_material_id",
    "source_asset_key": "p_source_asset_key",
    "content_checksum": "p_content_checksum",
    "storage_provider": "p_storage_provider",
    "storage_bucket": "p_storage_bucket",
    "storage_key": "p_storage_key",
    "source_file_name": "p_source_file_name",
    "source_content_type": "p_source_content_type",
    "source_file_size": "p_source_file_size",
    "source_fetched_at": "p_source_fetched_at",
    "is_derivative": "p_is_derivative",
    "license_observed_at": "p_license_observed_at",
    "license_observed_type": "p_license_observed_type",
    "license_name": "p_license_name",
    "license_source_url": "p_license_source_url",
    "storage_basis": "p_storage_basis",
    "source_med_seq": "p_source_med_seq",
    "source_url": "p_source_url",
    "med_gonggongnuri_raw": "p_med_gonggongnuri_raw",
    "med_gonggongnuri_nm_raw": "p_med_gonggongnuri_nm_raw",
}


class VersionError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _copy(row: dict) -> dict:
    return dict(row)


def payload_to_rpc(payload: dict) -> dict:
    out = {}
    for src, dest in PAYLOAD_TO_RPC.items():
        out[dest] = payload.get(src)
    out["p_is_derivative"] = False
    return out


def parse_promotion_result(raw) -> dict:
    data = raw
    if hasattr(raw, "data"):
        data = raw.data
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict):
        raise VersionError("UNKNOWN_PROMOTION_RESULT")
    status = data.get("status")
    if status not in ALLOWED_PROMOTION:
        raise VersionError("UNKNOWN_PROMOTION_RESULT", str(status))
    return {"status": status, "id": data.get("id"), "dml": data.get("dml"), "row": data}


def assert_production_versions(store) -> None:
    if store is None or isinstance(store, MemoryVersionStore) or type(store).__name__ == "MemoryVersionStore":
        raise VersionError("MEMORY_STORE_FORBIDDEN")



class MemoryVersionStore:
    """In-process replica of promote_kosha_safety_material_asset_version."""

    def __init__(self):
        self.rows: list[dict] = []
        self._id = 1
        self._lock = threading.Lock()
        self.fail_next_insert = False
        self.dml = 0

    def current(self, source_asset_key: str) -> dict | None:
        for r in self.rows:
            if r["source_asset_key"] == source_asset_key and r.get("is_current_version"):
                return _copy(r)
        return None

    def by_checksum(self, source_asset_key: str, checksum: str) -> dict | None:
        for r in self.rows:
            if r["source_asset_key"] == source_asset_key and r["content_checksum"] == checksum:
                return _copy(r)
        return None

    def current_count(self, source_asset_key: str) -> int:
        return sum(
            1 for r in self.rows
            if r["source_asset_key"] == source_asset_key and r.get("is_current_version")
        )

    def promote(self, payload: dict) -> dict:
        key = payload["source_asset_key"]
        sha = payload["content_checksum"]
        with self._lock:
            snapshot = [_copy(r) for r in self.rows]
            next_id = self._id
            dml0 = self.dml
            try:
                return self._promote_locked(payload, key, sha)
            except Exception:
                self.rows = snapshot
                self._id = next_id
                self.dml = dml0
                raise

    def _promote_locked(self, payload: dict, key: str, sha: str) -> dict:
        if payload.get("is_derivative"):
            raise VersionError("DERIVATIVE_FORBIDDEN")
        cur = None
        for r in self.rows:
            if r["source_asset_key"] == key and r.get("is_current_version"):
                cur = r
                break
        if cur and cur["content_checksum"] == sha:
            return {"status": "NO_CHANGE", "id": cur["id"], "dml": 0, "row": _copy(cur)}
        prev = None
        for r in self.rows:
            if r["source_asset_key"] == key and r["content_checksum"] == sha:
                prev = r
                break
        if prev is not None:
            if cur is not None:
                cur["is_current_version"] = False
                self.dml += 1
            prev["is_current_version"] = True
            self.dml += 1
            if self.current_count(key) != 1:
                raise VersionError("CURRENT_NOT_UNIQUE")
            return {"status": "PROMOTED_EXISTING_VERSION", "id": prev["id"], "dml": 2 if cur else 1, "row": _copy(prev)}
        if self.fail_next_insert:
            self.fail_next_insert = False
            raise VersionError("DB_INSERT_FAILED")
        if cur is not None:
            cur["is_current_version"] = False
            self.dml += 1
        row = dict(payload)
        row["id"] = self._id
        self._id += 1
        row["is_current_version"] = True
        row["is_derivative"] = False
        self.rows.append(row)
        self.dml += 1
        if self.current_count(key) != 1:
            raise VersionError("CURRENT_NOT_UNIQUE")
        return {"status": "NEW_VERSION", "id": row["id"], "dml": 2 if cur is not None else 1, "row": _copy(row)}


class SupabaseVersionStore:
    """Production adapter. Only RPC promote_kosha_safety_material_asset_version."""

    def __init__(self, sb=None):
        import os
        if not (os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")):
            raise VersionError("SERVICE_ROLE_REQUIRED")
        if sb is None:
            from db.supabase_client import get_supabase
            sb = get_supabase()
        self.sb = sb

    def promote(self, payload: dict) -> dict:
        params = payload_to_rpc(payload)
        missing = [n for n in RPC_PARAM_NAMES if n not in params]
        if missing:
            raise VersionError("RPC_PARAM_MISMATCH", ",".join(missing))
        try:
            resp = self.sb.rpc(RPC_FUNCTION, params).execute()
        except Exception as e:
            raise VersionError("DB_PROMOTION_FAILED", type(e).__name__) from e
        parsed = parse_promotion_result(resp)
        return parsed

    def current(self, source_asset_key: str) -> dict | None:
        r = (
            self.sb.table("kosha_safety_material_asset_versions")
            .select("*")
            .eq("source_asset_key", source_asset_key)
            .eq("is_current_version", True)
            .limit(2)
            .execute()
        )
        rows = r.data or []
        if len(rows) > 1:
            raise VersionError("CURRENT_NOT_UNIQUE")
        return dict(rows[0]) if rows else None

    def current_count(self, source_asset_key: str) -> int:
        r = (
            self.sb.table("kosha_safety_material_asset_versions")
            .select("id", count="exact")
            .eq("source_asset_key", source_asset_key)
            .eq("is_current_version", True)
            .execute()
        )
        return int(r.count or 0)

    def by_checksum(self, source_asset_key: str, checksum: str) -> dict | None:
        r = (
            self.sb.table("kosha_safety_material_asset_versions")
            .select("*")
            .eq("source_asset_key", source_asset_key)
            .eq("content_checksum", checksum)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        return dict(rows[0]) if rows else None
