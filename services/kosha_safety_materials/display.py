"""Read-only public material payload — WP-2 detail + WP-3 list/stats.

No KOSHA fetch, no R2 body for list/stats, no DML.
"""
from __future__ import annotations

from typing import Optional

from .license_policy import decide
from .storage.r2_store import ALLOWED_BUCKET
from .writer import ASSETS, CATALOG, DETAILS, ITEMS, SNAPSHOTS, VERSIONS

CATALOG_SELECT = "id,title,url,category,industry_category,collected_at"
CATALOG_EMBED = f"{ITEMS}!inner(snapshot_id)"
STAT_CATEGORIES = ("EDUCATION", "CASE_STUDY", "GUIDE", "POSTER")
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class CurrentSnapshotUnavailable(Exception):
    pass


VERSION_SELECT = (
    "id,asset_id,material_id,storage_bucket,storage_key,content_checksum,"
    "source_content_type,source_file_size,source_file_name,is_current_version,is_derivative"
)


class MemoryDisplayStore:
    """In-memory read replica for tests. No insert/update/delete methods."""

    def __init__(self):
        self.catalog: dict[str, dict] = {}
        self.details: dict[str, dict] = {}
        self.assets: list[dict] = []
        self.snapshots: list[dict] = []
        self.items: list[dict] = []
        self.versions: list[dict] = []
        self.writes = 0
        self.kosha_network = 0
        self.r2_put = 0
        self.r2_delete = 0

    def catalog_get(self, material_id: str) -> dict | None:
        row = self.catalog.get(material_id)
        return dict(row) if row else None

    def details_get(self, material_id: str) -> dict | None:
        row = self.details.get(material_id)
        return dict(row) if row else None

    def assets_list(self, material_id: str) -> list[dict]:
        return [dict(a) for a in self.assets if a.get("material_id") == material_id]

    def latest_completed(self) -> dict | None:
        done = [s for s in self.snapshots if s.get("status") == "COMPLETED"]
        if not done:
            return None
        done.sort(key=lambda s: s.get("completed_at") or "", reverse=True)
        return dict(done[0])

    def membership_has(self, snapshot_id: str, material_id: str) -> bool:
        return any(
            i.get("snapshot_id") == snapshot_id and i.get("material_id") == material_id
            for i in self.items
        )

    def current_versions(self, material_id: str) -> list[dict]:
        return [
            dict(v) for v in self.versions
            if v.get("material_id") == material_id and v.get("is_current_version") is True
        ]

    def list_current(
        self,
        snapshot_id: str,
        *,
        q: str = "",
        cat: str = "",
        sec: str = "",
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[list[dict], int]:
        members = {
            i.get("material_id")
            for i in self.items
            if i.get("snapshot_id") == snapshot_id
        }
        needle = (q or "").strip().lower()
        rows = []
        for mid in members:
            row = self.catalog.get(mid)
            if not row:
                continue
            if cat and row.get("category") != cat:
                continue
            if sec and row.get("industry_category") != sec:
                continue
            if needle and needle not in (row.get("title") or "").lower():
                continue
            rows.append(dict(row))
        rows.sort(key=lambda r: (r.get("id") or ""))
        rows.sort(key=lambda r: r.get("collected_at") or "", reverse=True)
        total = len(rows)
        start = max(page - 1, 0) * page_size
        return rows[start:start + page_size], total

    def stats_current(self, snapshot_id: str) -> dict:
        members = {
            i.get("material_id")
            for i in self.items
            if i.get("snapshot_id") == snapshot_id
        }
        categories = {c: 0 for c in STAT_CATEGORIES}
        total = 0
        for mid in members:
            row = self.catalog.get(mid)
            if not row:
                continue
            total += 1
            key = row.get("category")
            if key in categories:
                categories[key] += 1
        return {"snapshot_id": snapshot_id, "total": total, "categories": categories}


class SupabaseDisplayStore:
    """SELECT-only. Must not insert/update/delete."""

    def __init__(self, sb=None):
        if sb is None:
            from db.supabase_client import get_supabase
            sb = get_supabase()
        self.sb = sb
        self.writes = 0

    def catalog_get(self, material_id: str) -> dict | None:
        r = self.sb.table(CATALOG).select(CATALOG_SELECT).eq("id", material_id).limit(1).execute()
        rows = r.data or []
        return dict(rows[0]) if rows else None

    def details_get(self, material_id: str) -> dict | None:
        r = self.sb.table(DETAILS).select("*").eq("material_id", material_id).limit(1).execute()
        rows = r.data or []
        return dict(rows[0]) if rows else None

    def assets_list(self, material_id: str) -> list[dict]:
        r = (
            self.sb.table(ASSETS)
            .select("*")
            .eq("material_id", material_id)
            .order("display_order")
            .execute()
        )
        return list(r.data or [])

    def latest_completed(self) -> dict | None:
        r = (
            self.sb.table(SNAPSHOTS)
            .select("id,snapshot_hash,status,unique_count,completed_at")
            .eq("status", "COMPLETED")
            .order("completed_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        return dict(rows[0]) if rows else None

    def membership_has(self, snapshot_id: str, material_id: str) -> bool:
        r = (
            self.sb.table(ITEMS)
            .select("material_id")
            .eq("snapshot_id", snapshot_id)
            .eq("material_id", material_id)
            .limit(1)
            .execute()
        )
        return bool(r.data)

    def current_versions(self, material_id: str) -> list[dict]:
        r = (
            self.sb.table(VERSIONS)
            .select(VERSION_SELECT)
            .eq("material_id", material_id)
            .eq("is_current_version", True)
            .execute()
        )
        return [dict(v) for v in (r.data or [])]

    def _current_catalog(self, snapshot_id: str, columns: str):
        return (
            self.sb.table(CATALOG)
            .select(f"{columns},{CATALOG_EMBED}", count="exact")
            .eq(f"{ITEMS}.snapshot_id", snapshot_id)
        )

    def list_current(
        self,
        snapshot_id: str,
        *,
        q: str = "",
        cat: str = "",
        sec: str = "",
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[list[dict], int]:
        qy = self._current_catalog(snapshot_id, CATALOG_SELECT)
        if cat:
            qy = qy.eq("category", cat)
        if sec:
            qy = qy.eq("industry_category", sec)
        if q:
            qy = qy.ilike("title", f"%{q}%")
        start = max(page - 1, 0) * page_size
        end = start + page_size - 1
        r = qy.order("collected_at", desc=True).order("id").range(start, end).execute()
        rows = []
        for row in r.data or []:
            item = dict(row)
            item.pop(ITEMS, None)
            rows.append(item)
        return rows, int(r.count or 0)

    def stats_current(self, snapshot_id: str) -> dict:
        categories = {}
        for cat in STAT_CATEGORIES:
            r = (
                self._current_catalog(snapshot_id, "id")
                .eq("category", cat)
                .limit(1)
                .execute()
            )
            categories[cat] = int(r.count or 0)
        total_r = self._current_catalog(snapshot_id, "id").limit(1).execute()
        return {
            "snapshot_id": snapshot_id,
            "total": int(total_r.count or 0),
            "categories": categories,
        }


def _asset_payload(asset: dict, version: Optional[dict], decision, signer) -> dict:
    atype = (asset.get("asset_type") or "").upper()
    mime = asset.get("mime_type") or (version or {}).get("source_content_type")
    size = asset.get("file_size")
    if size is None and version is not None:
        size = version.get("source_file_size")
    out = {
        "asset_id": asset.get("id"),
        "asset_type": atype or asset.get("asset_type"),
        "file_name": asset.get("file_name") or (version or {}).get("source_file_name") or "",
        "mime_type": mime,
        "file_size": size,
        "internally_available": False,
        "view_url": None,
    }
    if atype == "VIDEO" or not decision.internal_serve_allowed:
        return out
    if not version or version.get("is_current_version") is not True:
        return out
    if version.get("is_derivative") is True:
        return out
    bucket = version.get("storage_bucket")
    key = version.get("storage_key")
    if bucket != ALLOWED_BUCKET or not key:
        return out
    out["view_url"] = signer.sign(
        bucket,
        key,
        mime=out["mime_type"],
        filename=out["file_name"],
    )
    out["internally_available"] = True
    return out


def load_public_material(material_id: str, *, store, signer) -> dict | None:
    """Current snapshot member only. Returns None → 404. Never writes."""
    mid = (material_id or "").strip()
    if not mid:
        return None
    snap = store.latest_completed()
    if not snap or snap.get("status") != "COMPLETED":
        return None
    if not store.membership_has(snap["id"], mid):
        return None
    catalog = store.catalog_get(mid)
    if not catalog:
        return None
    detail = store.details_get(mid) or {}
    detail_ok = detail.get("enrichment_status") == "OK"
    kogl = detail.get("kogl_type") if detail_ok else "UNKNOWN"
    content_type = detail.get("content_type") if detail_ok else None
    decision = decide(kogl, content_type)
    assets_out: list[dict] = []
    if detail_ok:
        versions = {
            str(v.get("asset_id")): v
            for v in store.current_versions(mid)
            if v.get("is_current_version") is True
        }
        raw_assets = sorted(
            store.assets_list(mid),
            key=lambda a: (
                a.get("display_order") is None,
                a.get("display_order") if a.get("display_order") is not None else 0,
                a.get("id") or 0,
            ),
        )
        for asset in raw_assets:
            ver = versions.get(str(asset.get("id")))
            assets_out.append(_asset_payload(asset, ver, decision, signer))
    source_url = ""
    if detail_ok and detail.get("source_url"):
        source_url = detail.get("source_url") or ""
    if not source_url:
        source_url = catalog.get("url") or ""
    return {
        "id": catalog.get("id") or mid,
        "title": catalog.get("title") or "",
        "category": catalog.get("category") or "",
        "sector": catalog.get("industry_category") or catalog.get("sector") or "",
        "description": (detail.get("source_description") if detail_ok else None) or None,
        "source": {
            "provider": "KOSHA",
            "source_url": source_url,
            "published_at": detail.get("source_published_at") if detail_ok else None,
            "license_type": decision.kogl_type,
            "license_name": (detail.get("license_name") if detail_ok else None) or None,
        },
        "assets": assets_out,
    }


def _require_current_snapshot(store) -> dict:
    snap = store.latest_completed()
    if not snap or snap.get("status") != "COMPLETED" or not snap.get("id"):
        raise CurrentSnapshotUnavailable("CURRENT_SNAPSHOT_UNAVAILABLE")
    return snap


def _normalize_filter(value: str) -> str:
    v = (value or "").strip()
    if not v or v.upper() == "ALL":
        return ""
    return v


def _clamp_page(page, page_size) -> tuple[int, int]:
    try:
        page_n = int(page)
    except (TypeError, ValueError):
        page_n = 1
    try:
        size_n = int(page_size)
    except (TypeError, ValueError):
        size_n = DEFAULT_PAGE_SIZE
    return max(page_n, 1), min(max(size_n, 1), MAX_PAGE_SIZE)


def _list_item(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "title": row.get("title") or "",
        "url": row.get("url") or "",
        "category": row.get("category") or "",
        "sector": row.get("industry_category") or row.get("sector") or "",
        "collected_at": row.get("collected_at"),
    }


def list_current_materials(
    store,
    *,
    q: str = "",
    cat: str = "",
    sec: str = "",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict:
    """Latest COMPLETED snapshot membership only. Read-only. No R2/KOSHA."""
    snap = _require_current_snapshot(store)
    page_n, size_n = _clamp_page(page, page_size)
    items, total = store.list_current(
        snap["id"],
        q=(q or "").strip(),
        cat=_normalize_filter(cat),
        sec=_normalize_filter(sec),
        page=page_n,
        page_size=size_n,
    )
    return {
        "snapshot_id": snap["id"],
        "items": [_list_item(x) for x in items],
        "total": int(total),
        "page": page_n,
        "page_size": size_n,
    }


def stats_current_materials(store) -> dict:
    """Current snapshot totals. Read-only. No R2/KOSHA."""
    snap = _require_current_snapshot(store)
    stats = store.stats_current(snap["id"])
    categories = {
        key: int((stats.get("categories") or {}).get(key, 0) or 0)
        for key in STAT_CATEGORIES
    }
    return {
        "snapshot_id": snap["id"],
        "total": int(stats.get("total") or 0),
        "categories": categories,
    }
