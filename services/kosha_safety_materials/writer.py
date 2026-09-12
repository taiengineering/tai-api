"""Details/assets writer — WP-1C-4B. catalog/snapshot/asset_versions DML 없음."""
from __future__ import annotations

from typing import Any, Optional
import time

DETAILS = "kosha_safety_material_details"
ASSETS = "kosha_safety_material_assets"
CATALOG = "kosha_safety_materials"
SNAPSHOTS = "kosha_safety_material_snapshots"
ITEMS = "kosha_safety_material_snapshot_items"
VERSIONS = "kosha_safety_material_asset_versions"

DETAIL_COLS = (
    "material_id", "source_provider", "source_med_seq", "source_url",
    "source_title", "source_description", "source_published_at", "source_updated_at",
    "kogl_type", "license_name", "license_source_url",
    "commercial_allowed", "modification_allowed", "render_policy",
    "content_type", "thumbnail_url", "source_checked_at", "source_content_hash",
    "enrichment_status", "failure_reason",
)
ASSET_COLS = (
    "material_id", "asset_type", "file_name", "source_file_url", "external_url",
    "embed_url", "mime_type", "file_size", "local_storage_url", "checksum",
    "display_order", "storage_allowed", "is_original",
)


def detail_body(detail: dict) -> dict:
    return {k: detail.get(k) for k in DETAIL_COLS}


def asset_body(asset: dict) -> dict:
    return {k: asset.get(k) for k in ASSET_COLS}


class MemoryStore:
    def __init__(self):
        self.catalog: dict[str, dict] = {}
        self.details: dict[str, dict] = {}
        self.assets: list[dict] = []
        self.snapshots: list[dict] = []
        self.items: list[dict] = []
        self.versions: list[dict] = []
        self._asset_id = 1
        self.dml = {
            "catalog": 0, "details": 0, "assets": 0, "snapshots": 0,
            "snapshot_items": 0, "asset_versions": 0, "historical": 0,
        }
        self.binary_gets = 0
        self.r2_ops = 0
        self.data_go_kr_calls = 0

    def catalog_get(self, material_id: str) -> dict | None:
        return self.catalog.get(material_id)

    def details_get(self, material_id: str) -> dict | None:
        row = self.details.get(material_id)
        return dict(row) if row else None

    def detail_ids(self) -> set[str]:
        return set(self.details)

    def assets_list(self, material_id: str) -> list[dict]:
        return [dict(a) for a in self.assets if a.get("material_id") == material_id]

    def count(self, table: str) -> int:
        return {
            CATALOG: len(self.catalog),
            DETAILS: len(self.details),
            ASSETS: len(self.assets),
            SNAPSHOTS: len(self.snapshots),
            ITEMS: len(self.items),
            VERSIONS: len(self.versions),
        }.get(table, 0)

    def latest_completed(self) -> dict | None:
        done = [s for s in self.snapshots if s.get("status") == "COMPLETED"]
        if not done:
            return None
        done.sort(key=lambda s: s.get("completed_at") or "", reverse=True)
        return dict(done[0])

    def membership(self, snapshot_id: str) -> list[dict]:
        return [dict(i) for i in self.items if i.get("snapshot_id") == snapshot_id]

    def insert_detail(self, body: dict) -> None:
        self.details[body["material_id"]] = dict(body)
        self.dml["details"] += 1

    def update_detail(self, material_id: str, body: dict) -> None:
        cur = dict(self.details[material_id])
        cur.update(body)
        self.details[material_id] = cur
        self.dml["details"] += 1

    def insert_asset(self, body: dict) -> None:
        row = dict(body)
        row["id"] = self._asset_id
        self._asset_id += 1
        self.assets.append(row)
        self.dml["assets"] += 1

    def update_asset(self, asset_id: Any, body: dict) -> None:
        for i, a in enumerate(self.assets):
            if a.get("id") == asset_id:
                cur = dict(a)
                cur.update(body)
                self.assets[i] = cur
                self.dml["assets"] += 1
                return


class SupabaseStore:
    _TRANSIENT_NAMES = frozenset({
        "RemoteProtocolError", "ConnectError", "ReadTimeout", "WriteTimeout",
        "ConnectTimeout", "LocalProtocolError", "ReadError", "WriteError",
        "PoolTimeout",
    })

    def __init__(self, sb=None):
        if sb is None:
            from db.supabase_client import get_supabase
            sb = get_supabase()
        self.sb = sb
        self.dml = {
            "catalog": 0, "details": 0, "assets": 0, "snapshots": 0,
            "snapshot_items": 0, "asset_versions": 0, "historical": 0,
        }
        self.binary_gets = 0
        self.r2_ops = 0
        self.data_go_kr_calls = 0

    def reconnect(self) -> None:
        from db.supabase_client import get_supabase
        self.sb = get_supabase()

    def _call(self, fn):
        from .detail_client import StopRun
        last = None
        for attempt in range(3):
            try:
                return fn()
            except StopRun:
                raise
            except Exception as e:
                if type(e).__name__ not in self._TRANSIENT_NAMES:
                    raise
                last = e
                self.reconnect()
                if attempt < 2:
                    time.sleep((1.0, 3.0)[attempt])
        raise StopRun("TRANSIENT_UPSTREAM_FAILURE", endpoint="supabase") from last

    def catalog_get(self, material_id: str) -> dict | None:
        def _go():
            r = self.sb.table(CATALOG).select("id,title,url,category").eq("id", material_id).limit(1).execute()
            rows = r.data or []
            return rows[0] if rows else None
        return self._call(_go)

    def details_get(self, material_id: str) -> dict | None:
        def _go():
            r = self.sb.table(DETAILS).select("*").eq("material_id", material_id).limit(1).execute()
            rows = r.data or []
            return rows[0] if rows else None
        return self._call(_go)

    def detail_ids(self) -> set[str]:
        ids: set[str] = set()
        start = 0
        page = 1000
        while True:
            def _go(st=start, n=page):
                r = self.sb.table(DETAILS).select("material_id").range(st, st + n - 1).execute()
                return r.data or []
            batch = self._call(_go)
            for row in batch:
                if row.get("material_id"):
                    ids.add(row["material_id"])
            if len(batch) < page:
                break
            start += page
        return ids

    def assets_list(self, material_id: str) -> list[dict]:
        def _go():
            r = self.sb.table(ASSETS).select("*").eq("material_id", material_id).execute()
            return r.data or []
        return self._call(_go)

    def count(self, table: str) -> int:
        def _go():
            r = self.sb.table(table).select("*", count="exact").limit(1).execute()
            return int(r.count or 0)
        try:
            return self._call(_go)
        except Exception:
            return -1

    def latest_completed(self) -> dict | None:
        def _go():
            r = (
                self.sb.table(SNAPSHOTS)
                .select("id,snapshot_hash,status,unique_count,declared_total,fetched_count,completed_at")
                .eq("status", "COMPLETED")
                .order("completed_at", desc=True)
                .limit(1)
                .execute()
            )
            rows = r.data or []
            return dict(rows[0]) if rows else None
        return self._call(_go)

    def membership(self, snapshot_id: str) -> list[dict]:
        rows: list[dict] = []
        start = 0
        page = 1000
        cols = "material_id,source_med_seq,source_url,source_title"
        while True:
            def _go(st=start, n=page):
                r = (
                    self.sb.table(ITEMS)
                    .select(cols)
                    .eq("snapshot_id", snapshot_id)
                    .range(st, st + n - 1)
                    .execute()
                )
                return r.data or []
            batch = self._call(_go)
            rows.extend(batch)
            if len(batch) < page:
                break
            start += page
        return rows

    def insert_detail(self, body: dict) -> None:
        self._call(lambda: self.sb.table(DETAILS).insert(body).execute())
        self.dml["details"] += 1

    def update_detail(self, material_id: str, body: dict) -> None:
        self._call(lambda: self.sb.table(DETAILS).update(body).eq("material_id", material_id).execute())
        self.dml["details"] += 1

    def insert_asset(self, body: dict) -> None:
        self._call(lambda: self.sb.table(ASSETS).insert(body).execute())
        self.dml["assets"] += 1

    def update_asset(self, asset_id: Any, body: dict) -> None:
        self._call(lambda: self.sb.table(ASSETS).update(body).eq("id", asset_id).execute())
        self.dml["assets"] += 1


class Writer:
    def __init__(self, dry_run: bool = True, store=None):
        self.dry_run = dry_run
        self.store = store if store is not None else SupabaseStore()

    def catalog_get(self, material_id: str) -> dict | None:
        return self.store.catalog_get(material_id)

    def details_get(self, material_id: str) -> dict | None:
        return self.store.details_get(material_id)

    def count(self, table: str) -> int:
        return self.store.count(table)

    def upsert(self, detail: dict, assets: list[dict], *, allow_update: bool = False) -> dict:
        existing = self.store.details_get(detail["material_id"])
        if existing and existing.get("source_content_hash") == detail.get("source_content_hash"):
            return {"op": "NO_CHANGE", "detail_writes": 0, "asset_writes": 0, "existing": existing}
        if existing and not allow_update:
            return {"op": "SKIP_EXISTING", "detail_writes": 0, "asset_writes": 0, "existing": existing}
        op = "INSERT" if not existing else "UPDATE"
        if self.dry_run:
            return {"op": op, "detail_writes": 0, "asset_writes": 0, "dry_run": True}
        body = detail_body(detail)
        if existing:
            self.store.update_detail(detail["material_id"], body)
        else:
            self.store.insert_detail(body)
        have = {a.get("checksum"): a for a in self.store.assets_list(detail["material_id"])}
        aw = 0
        for asset in assets:
            row = asset_body(asset)
            prev = have.get(asset.get("checksum"))
            if prev:
                if not allow_update or prev.get("id") in (None, "pending"):
                    continue
                self.store.update_asset(prev["id"], row)
            else:
                if not self.dry_run:
                    self.store.insert_asset(row)
                have[asset.get("checksum")] = {"id": "pending", **row}
            aw += 1
        return {"op": op, "detail_writes": 1, "asset_writes": aw}
