"""Atomic asset_versions promotion — WP-1C-5A.

Live DML this WP = 0. Memory store matches SQL function semantics for tests.
"""
from __future__ import annotations

import threading
from typing import Any, Optional

VERSION_IMMUTABLE = (
    "content_checksum", "storage_key", "source_file_name", "source_file_size",
    "license_observed_at", "license_observed_type", "storage_basis",
)


class VersionError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _copy(row: dict) -> dict:
    return dict(row)


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
