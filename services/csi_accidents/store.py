"""CSI catalog/snapshot stores. Current = latest COMPLETED membership only."""
from __future__ import annotations

from typing import Any, Optional

from services.csi_accidents.parse import CsiSyncError


class MemoryCsiStore:
    def __init__(self):
        self.cases: dict[str, dict] = {}
        self.snapshots: list[dict] = []
        self.items: list[dict] = []
        self.dml = 0
        self.fail_on_membership = False
        self.kosha_writes = 0
        self.graph_writes = 0
        self.r2_writes = 0

    def list_cases(self) -> list[dict]:
        return list(self.cases.values())

    def get_latest_completed(self) -> Optional[dict]:
        done = [s for s in self.snapshots if s["status"] == "COMPLETED"]
        if not done:
            return None
        done.sort(key=lambda s: (s.get("completed_at") or "", s.get("started_at") or ""), reverse=True)
        return done[0]

    def get_snapshot_by_sha(self, file_sha256: str) -> Optional[dict]:
        matches = [s for s in self.snapshots if s.get("file_sha256") == file_sha256]
        done = [s for s in matches if s["status"] == "COMPLETED"]
        if done:
            return done[0]
        return matches[0] if matches else None

    def current_content_ids(self) -> list[str]:
        latest = self.get_latest_completed()
        if not latest:
            return []
        return [i["content_id"] for i in self.items if i["snapshot_id"] == latest["id"]]

    def current_ready_ids(self) -> list[str]:
        latest = self.get_latest_completed()
        if not latest:
            return []
        return [
            i["content_id"]
            for i in self.items
            if i["snapshot_id"] == latest["id"] and i.get("identity_status") == "READY"
        ]

    def upsert_cases(self, rows: list[dict]) -> int:
        self.dml += 1
        for row in rows:
            cid = row["content_id"]
            prev = self.cases.get(cid)
            if prev and prev.get("first_seen_at"):
                row = dict(row)
                row["first_seen_at"] = prev["first_seen_at"]
                hashes = set(prev.get("source_content_hashes") or [])
                hashes.add(row["source_content_hash"])
                row["source_content_hashes"] = hashes
            else:
                row = dict(row)
                row["source_content_hashes"] = {row["source_content_hash"]}
            self.cases[cid] = row
        return len(rows)

    def mark_hold(self, content_ids: list[str], reason: str) -> None:
        if not content_ids:
            return
        self.dml += 1
        for cid in content_ids:
            if cid in self.cases:
                self.cases[cid]["identity_status"] = "HOLD"
                self.cases[cid]["identity_reason"] = reason

    def insert_running_snapshot(self, row: dict) -> None:
        self.dml += 1
        self.snapshots.append(dict(row))

    def insert_membership(self, rows: list[dict]) -> None:
        if self.fail_on_membership:
            raise CsiSyncError("MEMBERSHIP_WRITE", "forced membership failure")
        self.dml += 1
        self.items.extend(rows)

    def complete_snapshot(self, snapshot_id: str, completed_at: str) -> None:
        self.dml += 1
        for s in self.snapshots:
            if s["id"] == snapshot_id and s["status"] == "RUNNING":
                s["status"] = "COMPLETED"
                s["completed_at"] = completed_at
                return
        raise CsiSyncError("SNAPSHOT_STATE", "RUNNING snapshot not found")

    def fail_snapshot(self, snapshot_id: str, reason: str, completed_at: str) -> None:
        self.dml += 1
        for s in self.snapshots:
            if s["id"] == snapshot_id:
                s["status"] = "FAILED"
                s["failure_reason"] = reason
                s["completed_at"] = completed_at
                return


class SupabaseCsiStore:
    def __init__(self, sb: Any):
        self.sb = sb
        self.dml = 0
        self.kosha_writes = 0
        self.graph_writes = 0
        self.r2_writes = 0

    def list_cases(self) -> list[dict]:
        out: list[dict] = []
        start = 0
        while True:
            r = (
                self.sb.table("csi_accident_cases")
                .select("content_id,identity_fingerprint,identity_status")
                .range(start, start + 999)
                .execute()
            )
            chunk = r.data or []
            out.extend(chunk)
            if len(chunk) < 1000:
                break
            start += 1000
        hashes: dict[str, set[str]] = {}
        start = 0
        while True:
            r = (
                self.sb.table("csi_accident_snapshot_items")
                .select("content_id,source_content_hash")
                .range(start, start + 999)
                .execute()
            )
            chunk = r.data or []
            for row in chunk:
                hashes.setdefault(row["content_id"], set()).add(row["source_content_hash"])
            if len(chunk) < 1000:
                break
            start += 1000
        for row in out:
            row["source_content_hashes"] = hashes.get(row["content_id"], set())
        return out

    def get_latest_completed(self) -> Optional[dict]:
        r = (
            self.sb.table("csi_accident_snapshots")
            .select("*")
            .eq("status", "COMPLETED")
            .order("completed_at", desc=True)
            .limit(1)
            .execute()
        )
        data = r.data or []
        return data[0] if data else None

    def get_snapshot_by_sha(self, file_sha256: str) -> Optional[dict]:
        r = (
            self.sb.table("csi_accident_snapshots")
            .select("*")
            .eq("file_sha256", file_sha256)
            .eq("status", "COMPLETED")
            .limit(1)
            .execute()
        )
        data = r.data or []
        if data:
            return data[0]
        r = (
            self.sb.table("csi_accident_snapshots")
            .select("*")
            .eq("file_sha256", file_sha256)
            .limit(1)
            .execute()
        )
        data = r.data or []
        return data[0] if data else None

    def upsert_cases(self, rows: list[dict]) -> int:
        self.dml += 1
        payload = []
        for row in rows:
            item = {
                k: row[k]
                for k in (
                    "content_id",
                    "source_id",
                    "source_key",
                    "identity_fingerprint",
                    "identity_status",
                    "identity_reason",
                    "fingerprint_version",
                    "first_seen_at",
                    "updated_at",
                )
            }
            payload.append(item)
        existing = {}
        ids = [r["content_id"] for r in payload]
        for i in range(0, len(ids), 200):
            got = (
                self.sb.table("csi_accident_cases")
                .select("content_id,first_seen_at")
                .in_("content_id", ids[i : i + 200])
                .execute()
            )
            for row in got.data or []:
                existing[row["content_id"]] = row.get("first_seen_at")
        for item in payload:
            if existing.get(item["content_id"]):
                item["first_seen_at"] = existing[item["content_id"]]
        for i in range(0, len(payload), 100):
            self.sb.table("csi_accident_cases").upsert(
                payload[i : i + 100], on_conflict="content_id"
            ).execute()
        return len(payload)

    def mark_hold(self, content_ids: list[str], reason: str) -> None:
        if not content_ids:
            return
        self.dml += 1
        for i in range(0, len(content_ids), 100):
            chunk = content_ids[i : i + 100]
            self.sb.table("csi_accident_cases").update(
                {"identity_status": "HOLD", "identity_reason": reason}
            ).in_("content_id", chunk).execute()

    def insert_running_snapshot(self, row: dict) -> None:
        self.dml += 1
        self.sb.table("csi_accident_snapshots").insert(row).execute()

    def insert_membership(self, rows: list[dict]) -> None:
        self.dml += 1
        for i in range(0, len(rows), 100):
            self.sb.table("csi_accident_snapshot_items").insert(rows[i : i + 100]).execute()

    def complete_snapshot(self, snapshot_id: str, completed_at: str) -> None:
        self.dml += 1
        self.sb.table("csi_accident_snapshots").update(
            {"status": "COMPLETED", "completed_at": completed_at}
        ).eq("id", snapshot_id).eq("status", "RUNNING").execute()

    def fail_snapshot(self, snapshot_id: str, reason: str, completed_at: str) -> None:
        self.dml += 1
        self.sb.table("csi_accident_snapshots").update(
            {
                "status": "FAILED",
                "failure_reason": reason[:500],
                "completed_at": completed_at,
            }
        ).eq("id", snapshot_id).execute()
