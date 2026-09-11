"""Durable OPEN holds for source-resolution data-quality exceptions — PATCH-5B-HOLD.

MemoryHoldStore = tests only. Production apply uses SupabaseHoldStore.
Holds are not storage completion.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Optional

HOLD_TABLE = "kosha_safety_material_storage_holds"
HOLD_REASONS = frozenset({
    "SOURCE_ASSET_FILENAME_MISMATCH",
    "SOURCE_ASSET_ZERO_MATCH",
    "SOURCE_ASSET_MULTI_MATCH",
})
HOLD_STATUSES = frozenset({"OPEN", "RESOLVED"})


class HoldError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def assert_hold_reason(reason: str) -> str:
    if reason not in HOLD_REASONS:
        raise HoldError("HOLD_REASON_NOT_ALLOWED", reason)
    return reason


def assert_production_holds(store) -> None:
    if store is None or isinstance(store, MemoryHoldStore) or type(store).__name__ == "MemoryHoldStore":
        raise HoldError("MEMORY_HOLD_STORE_FORBIDDEN")


class MemoryHoldStore:
    """In-process unique (snapshot_id, asset_id, reason). Tests only."""

    def __init__(self):
        self.rows: list[dict] = []
        self._id = 1
        self._lock = threading.Lock()
        self.inserts = 0

    def open_asset_ids(self, snapshot_id: str) -> set:
        return {
            r["asset_id"] for r in self.rows
            if r["snapshot_id"] == snapshot_id and r.get("status") == "OPEN"
        }

    def record_open(
        self,
        *,
        snapshot_id: str,
        asset_id,
        material_id: str,
        source_med_seq: str | None,
        reason: str,
        expected_file_name: str | None,
        observed_files: list | None = None,
    ) -> dict:
        assert_hold_reason(reason)
        key = (snapshot_id, asset_id, reason)
        with self._lock:
            for r in self.rows:
                if (r["snapshot_id"], r["asset_id"], r["reason"]) == key:
                    return {"status": "HOLD", "inserted": 0, "id": r["id"], "reason": reason, "row": dict(r)}
            row = {
                "id": self._id,
                "asset_id": asset_id,
                "material_id": material_id,
                "snapshot_id": snapshot_id,
                "source_med_seq": source_med_seq,
                "reason": reason,
                "expected_file_name": expected_file_name,
                "observed_files": list(observed_files or []),
                "observed_at": _utc(),
                "status": "OPEN",
                "resolution_note": None,
                "resolved_at": None,
            }
            self._id += 1
            self.rows.append(row)
            self.inserts += 1
            return {"status": "HOLD", "inserted": 1, "id": row["id"], "reason": reason, "row": dict(row)}


class SupabaseHoldStore:
    def __init__(self, sb=None):
        import os
        if not (os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")):
            raise HoldError("SERVICE_ROLE_REQUIRED")
        if sb is None:
            from db.supabase_client import get_supabase
            sb = get_supabase()
        self.sb = sb

    def open_asset_ids(self, snapshot_id: str) -> set:
        ids: set = set()
        start = 0
        while True:
            r = (
                self.sb.table(HOLD_TABLE)
                .select("asset_id")
                .eq("snapshot_id", snapshot_id)
                .eq("status", "OPEN")
                .range(start, start + 999)
                .execute()
            )
            batch = r.data or []
            for row in batch:
                aid = row.get("asset_id")
                if aid is None or aid == "" or aid == "pending":
                    raise HoldError("ASSET_ID_REQUIRED")
                ids.add(aid)
            if len(batch) < 1000:
                break
            start += 1000
        return ids

    def record_open(
        self,
        *,
        snapshot_id: str,
        asset_id,
        material_id: str,
        source_med_seq: str | None,
        reason: str,
        expected_file_name: str | None,
        observed_files: list | None = None,
    ) -> dict:
        assert_hold_reason(reason)
        body = {
            "asset_id": asset_id,
            "material_id": material_id,
            "snapshot_id": snapshot_id,
            "source_med_seq": source_med_seq,
            "reason": reason,
            "expected_file_name": expected_file_name,
            "observed_files": list(observed_files or []),
            "observed_at": _utc(),
            "status": "OPEN",
        }
        try:
            ins = (
                self.sb.table(HOLD_TABLE)
                .upsert(body, on_conflict="snapshot_id,asset_id,reason", ignore_duplicates=True)
                .execute()
            )
        except Exception as e:
            raise HoldError("HOLD_WRITE_FAILED", type(e).__name__) from e
        inserted = 1 if ins.data else 0
        r = (
            self.sb.table(HOLD_TABLE)
            .select("*")
            .eq("snapshot_id", snapshot_id)
            .eq("asset_id", asset_id)
            .eq("reason", reason)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        if not rows:
            raise HoldError("HOLD_WRITE_FAILED", "missing row after upsert")
        row = dict(rows[0])
        if inserted and row.get("status") != "OPEN":
            raise HoldError("HOLD_WRITE_FAILED", "status")
        return {"status": "HOLD", "inserted": inserted, "id": row.get("id"), "reason": reason, "row": row}
