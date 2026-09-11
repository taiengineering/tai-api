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
    "SOURCE_ASSET_OVERSIZE_POLICY",
    "SOURCE_BINARY_UNAVAILABLE",
    "SOURCE_ASSET_REVIEW_REQUIRED",
})
UNAVAILABLE_REASON = "SOURCE_BINARY_UNAVAILABLE"
REVIEW_REASON = "SOURCE_ASSET_REVIEW_REQUIRED"
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

    def open_rows(self, snapshot_id: str, reason: str | None = None) -> list[dict]:
        out = []
        for r in self.rows:
            if r["snapshot_id"] != snapshot_id or r.get("status") != "OPEN":
                continue
            if reason is not None and r.get("reason") != reason:
                continue
            out.append(dict(r))
        return out

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

    def open_rows(self, snapshot_id: str, reason: str | None = None) -> list[dict]:
        rows: list[dict] = []
        start = 0
        while True:
            q = (
                self.sb.table(HOLD_TABLE)
                .select("asset_id,reason,observed_files,expected_file_name")
                .eq("snapshot_id", snapshot_id)
                .eq("status", "OPEN")
            )
            if reason is not None:
                q = q.eq("reason", reason)
            r = q.range(start, start + 999).execute()
            batch = r.data or []
            rows.extend(dict(x) for x in batch)
            if len(batch) < 1000:
                break
            start += 1000
        return rows

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


def oversize_report(holds, snapshot_id: str) -> dict:
    empty = {"oversize_hold_count": 0, "oversize_max_file_size": 0, "oversize_asset_ids": []}
    if holds is None or not snapshot_id or not hasattr(holds, "open_rows"):
        return empty
    from .limits import OVERSIZE_REASON, parsed_file_size

    rows = holds.open_rows(snapshot_id, OVERSIZE_REASON)
    ids = []
    max_sz = 0
    for r in rows:
        aid = r.get("asset_id")
        if aid is not None:
            ids.append(aid)
        for obs in r.get("observed_files") or []:
            n = parsed_file_size(obs.get("file_size") if isinstance(obs, dict) else None)
            if n is not None and n > max_sz:
                max_sz = n
    ids_sorted = sorted(ids)
    return {
        "oversize_hold_count": len(ids_sorted),
        "oversize_max_file_size": max_sz if ids_sorted else 0,
        "oversize_asset_ids": ids_sorted,
    }


def hold_breakdown(holds, snapshot_id: str) -> dict:
    from .classify import REVIEW_REASON, REVIEW_SUBREASONS

    reasons = [
        "SOURCE_ASSET_FILENAME_MISMATCH",
        "SOURCE_ASSET_ZERO_MATCH",
        "SOURCE_ASSET_MULTI_MATCH",
        "SOURCE_ASSET_OVERSIZE_POLICY",
        "SOURCE_BINARY_UNAVAILABLE",
        REVIEW_REASON,
    ]
    counts = {r: 0 for r in reasons}
    ids = {r: [] for r in reasons}
    review_subs = {s: 0 for s in sorted(REVIEW_SUBREASONS)}
    review_ids = {s: [] for s in sorted(REVIEW_SUBREASONS)}
    if holds is None or not snapshot_id or not hasattr(holds, "open_rows"):
        return {
            "hold_counts": counts,
            "hold_asset_ids": ids,
            "review_subreasons": review_subs,
            "review_subreason_ids": review_ids,
        }
    for r in holds.open_rows(snapshot_id):
        reason = r.get("reason")
        aid = r.get("asset_id")
        if reason in counts:
            counts[reason] += 1
            if aid is not None:
                ids[reason].append(aid)
        if reason == REVIEW_REASON:
            obs = (r.get("observed_files") or [{}])
            sub = obs[0].get("subreason") if obs and isinstance(obs[0], dict) else None
            if sub in review_subs:
                review_subs[sub] += 1
                if aid is not None:
                    review_ids[sub].append(aid)
    for k in ids:
        ids[k] = sorted(ids[k])
    for k in review_ids:
        review_ids[k] = sorted(review_ids[k])
    return {
        "hold_counts": counts,
        "hold_asset_ids": ids,
        "review_subreasons": review_subs,
        "review_subreason_ids": review_ids,
    }
