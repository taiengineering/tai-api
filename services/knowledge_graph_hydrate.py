"""Runtime Knowledge hydration from source SoT. No Graph content copy. No N+1."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from services.knowledge_graph_svc import KnowledgeRecord, default_tai_url

IN_CHUNK = 200

GUIDE_TABLE = "kosha_guide_current"
MATERIAL_CATALOG = "kosha_safety_materials"
MATERIAL_SNAPSHOTS = "kosha_safety_material_snapshots"
MATERIAL_ITEMS = "kosha_safety_material_snapshot_items"
ACCIDENT_DOMESTIC = "kosha_accident_cases"
ACCIDENT_CONSTRUCTION = "kosha_construction_accidents"
LAW_TABLE = "law_revision_board"
PRECEDENT_TABLE = "industrial_accident_precedents"


def _chunks(values: list[str], size: int = IN_CHUNK):
    uniq = []
    seen = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        uniq.append(value)
    for i in range(0, len(uniq), size):
        yield uniq[i : i + size]


class ProductionKnowledgeHydrator:
    """Batch hydrate current/public Knowledge only. KNOWLEDGE_CENTER is DEFERRED."""

    def __init__(self, sb):
        self.sb = sb
        self.source_writes = 0
        self.batch_queries = 0

    def get(self, content_type: str, content_id: str) -> KnowledgeRecord | None:
        return self.get_many([(content_type, content_id)]).get((content_type, content_id))

    def get_many(self, pairs: Iterable[tuple[str, str]]) -> dict[tuple[str, str], KnowledgeRecord]:
        by_type: dict[str, list[str]] = defaultdict(list)
        for content_type, content_id in pairs:
            by_type[content_type].append(str(content_id))
        out: dict[tuple[str, str], KnowledgeRecord] = {}
        for content_type, ids in by_type.items():
            try:
                out.update(self._hydrate_type(content_type, ids))
            except Exception:
                continue
        return out

    def _in(self, table: str, col: str, ids: list[str], columns: str, extra_eq: list[tuple[str, Any]] | None = None):
        rows = []
        for chunk in _chunks(ids):
            q = self.sb.table(table).select(columns).in_(col, chunk)
            for key, value in extra_eq or []:
                q = q.eq(key, value)
            self.batch_queries += 1
            rows.extend(list(q.execute().data or []))
        return rows

    def _hydrate_type(self, content_type: str, ids: list[str]) -> dict[tuple[str, str], KnowledgeRecord]:
        if content_type == "KOSHA_GUIDE":
            return self._guides(ids)
        if content_type == "SAFETY_MATERIAL":
            return self._materials(ids)
        if content_type == "ACCIDENT":
            return self._accidents(ids)
        if content_type == "LAW_UPDATE":
            return self._laws(ids)
        if content_type == "PRECEDENT":
            return self._precedents(ids)
        return {}

    def _guides(self, ids: list[str]) -> dict[tuple[str, str], KnowledgeRecord]:
        rows = self._in(
            GUIDE_TABLE,
            "guide_no",
            ids,
            "guide_no,guide_title,category_name,guide_url,regist_date",
        )
        out = {}
        for row in rows:
            cid = str(row.get("guide_no") or "")
            if not cid:
                continue
            out[("KOSHA_GUIDE", cid)] = KnowledgeRecord(
                content_type="KOSHA_GUIDE",
                content_id=cid,
                title=row.get("guide_title"),
                summary=None,
                tai_url=default_tai_url("KOSHA_GUIDE", cid),
                source_name="KOSHA",
                source_url=row.get("guide_url"),
                published_at=row.get("regist_date"),
                category=row.get("category_name"),
                is_public_current=True,
            )
        return out

    def _materials(self, ids: list[str]) -> dict[tuple[str, str], KnowledgeRecord]:
        self.batch_queries += 1
        snap_resp = (
            self.sb.table(MATERIAL_SNAPSHOTS)
            .select("id,status,completed_at")
            .eq("status", "COMPLETED")
            .order("completed_at", desc=True)
            .limit(1)
            .execute()
        )
        snaps = list(snap_resp.data or [])
        if not snaps:
            return {}
        snap_id = snaps[0]["id"]
        members = self._in(
            MATERIAL_ITEMS,
            "material_id",
            ids,
            "material_id,snapshot_id",
            extra_eq=[("snapshot_id", snap_id)],
        )
        current_ids = [str(r.get("material_id")) for r in members if r.get("material_id")]
        if not current_ids:
            return {}
        rows = self._in(MATERIAL_CATALOG, "id", current_ids, "id,title,category,url,collected_at")
        out = {}
        for row in rows:
            cid = str(row.get("id") or "")
            if not cid:
                continue
            out[("SAFETY_MATERIAL", cid)] = KnowledgeRecord(
                content_type="SAFETY_MATERIAL",
                content_id=cid,
                title=row.get("title"),
                summary=None,
                tai_url=default_tai_url("SAFETY_MATERIAL", cid),
                source_name="KOSHA",
                source_url=row.get("url"),
                published_at=row.get("collected_at"),
                category=row.get("category"),
                is_public_current=True,
            )
        return out

    def _accidents(self, ids: list[str]) -> dict[tuple[str, str], KnowledgeRecord]:
        out = {}
        domestic = self._in(ACCIDENT_DOMESTIC, "id", ids, "id,title,reg_dt,file_url")
        for row in domestic:
            cid = str(row.get("id") or "")
            if not cid:
                continue
            out[("ACCIDENT", cid)] = KnowledgeRecord(
                content_type="ACCIDENT",
                content_id=cid,
                title=row.get("title"),
                summary=None,
                tai_url=default_tai_url("ACCIDENT", cid),
                source_name="KOSHA",
                source_url=row.get("file_url"),
                published_at=row.get("reg_dt"),
                category=None,
                is_public_current=True,
            )
        construction = self._in(
            ACCIDENT_CONSTRUCTION,
            "id",
            ids,
            "id,accident_summary,work_type,accident_type,occurrence_date",
        )
        for row in construction:
            cid = str(row.get("id") or "")
            if not cid:
                continue
            out[("ACCIDENT", cid)] = KnowledgeRecord(
                content_type="ACCIDENT",
                content_id=cid,
                title=None,
                summary=row.get("accident_summary"),
                tai_url=default_tai_url("ACCIDENT", cid, construction=True),
                source_name="KOSHA",
                source_url=None,
                published_at=row.get("occurrence_date"),
                category=row.get("work_type") or row.get("accident_type"),
                is_public_current=True,
            )
        return out

    def _laws(self, ids: list[str]) -> dict[tuple[str, str], KnowledgeRecord]:
        rows = self._in(
            LAW_TABLE,
            "id",
            ids,
            "id,law_name,summary,status,is_public,enforcement_date",
            extra_eq=[("is_public", True), ("status", "PUBLISHED")],
        )
        out = {}
        for row in rows:
            cid = str(row.get("id") or "")
            if not cid:
                continue
            out[("LAW_UPDATE", cid)] = KnowledgeRecord(
                content_type="LAW_UPDATE",
                content_id=cid,
                title=row.get("law_name"),
                summary=row.get("summary"),
                tai_url=default_tai_url("LAW_UPDATE", cid),
                source_name="LAW",
                source_url=None,
                published_at=row.get("enforcement_date"),
                category=None,
                is_public_current=True,
            )
        return out

    def _precedents(self, ids: list[str]) -> dict[tuple[str, str], KnowledgeRecord]:
        rows = self._in(PRECEDENT_TABLE, "id", ids, "id,case_name,summary,hazard_type,sector")
        out = {}
        for row in rows:
            cid = str(row.get("id") or "")
            if not cid:
                continue
            out[("PRECEDENT", cid)] = KnowledgeRecord(
                content_type="PRECEDENT",
                content_id=cid,
                title=row.get("case_name"),
                summary=row.get("summary"),
                tai_url=default_tai_url("PRECEDENT", cid),
                source_name="PRECEDENT",
                source_url=None,
                published_at=None,
                category=row.get("hazard_type") or row.get("sector"),
                is_public_current=True,
            )
        return out
