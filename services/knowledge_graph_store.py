"""Production OBJ-GRAPH Supabase adapter. No full-table edge scans. No DELETE."""

from __future__ import annotations

import uuid
from typing import Any

RUNS = "knowledge_relation_runs"
EDGES = "knowledge_relation_edges"
EVIDENCE = "knowledge_relation_evidence"

GRAPH_TABLES = frozenset({RUNS, EDGES, EVIDENCE})
SOURCE_TABLES = frozenset(
    {
        "kosha_guide",
        "kosha_guide_current",
        "kosha_safety_materials",
        "kosha_safety_material_details",
        "kosha_safety_material_snapshots",
        "kosha_safety_material_snapshot_items",
        "kosha_accident_cases",
        "kosha_construction_accidents",
        "law_revision_board",
        "industrial_accident_precedents",
    }
)

EDGE_COLS = (
    "id",
    "edge_key",
    "edge_kind",
    "source_content_type",
    "source_content_id",
    "relation_type",
    "relation_key",
    "relation_label",
    "target_content_type",
    "target_content_id",
    "status",
    "is_active",
    "first_seen_run_id",
    "last_seen_run_id",
    "stale_at",
    "created_at",
    "updated_at",
)

EVIDENCE_COLS = (
    "id",
    "edge_id",
    "evidence_key",
    "method",
    "evidence_type",
    "source_field",
    "evidence_value",
    "rule_id",
    "rule_version",
    "source_version",
    "source_content_hash",
    "evidence_json",
    "created_at",
    "last_seen_run_id",
)

RUN_COLS = (
    "id",
    "run_type",
    "scope_json",
    "rule_set_version",
    "status",
    "dry_run",
    "started_at",
    "completed_at",
    "knowledge_items_scanned",
    "candidates_generated",
    "accepted",
    "rejected",
    "duplicate_prevented",
    "no_relation_items",
    "metrics_json",
    "error_code",
    "error_message",
)

EDGE_SELECT = ",".join(EDGE_COLS)
RELATED_CONTEXT_LIMIT = 100
CONTEXT_ORDER = ("source_content_type", "source_content_id")
IN_CHUNK = 200


class FullTableScanForbidden(RuntimeError):
    def __init__(self):
        super().__init__("FULL_TABLE_SCAN_FORBIDDEN")


def _pick(row: dict[str, Any], cols: tuple[str, ...]) -> dict[str, Any]:
    return {k: row.get(k) for k in cols if k in row or row.get(k) is not None}


def _chunks(values: list[str], size: int = IN_CHUNK):
    for i in range(0, len(values), size):
        yield values[i : i + size]


class SupabaseGraphStore:
    """Indexed Graph table access. list_edges() is not implemented on purpose."""

    def __init__(self, sb):
        self.sb = sb
        self._source_writes = 0
        self.graph_writes = 0
        self.delete_calls = 0

    def source_writes(self) -> int:
        return self._source_writes

    def list_edges(self) -> list[dict[str, Any]]:
        raise FullTableScanForbidden()

    def _one(self, table: str, col: str, value: str) -> dict[str, Any] | None:
        resp = self.sb.table(table).select("*").eq(col, value).limit(1).execute()
        rows = list(resp.data or [])
        return dict(rows[0]) if rows else None

    def insert_run(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = dict(row)
        payload.setdefault("id", str(uuid.uuid4()))
        self.sb.table(RUNS).insert(payload).execute()
        self.graph_writes += 1
        stored = self.get_run(payload["id"])
        return stored or payload

    def update_run(self, run_id: str, patch: dict[str, Any]) -> None:
        self.sb.table(RUNS).update(patch).eq("id", run_id).execute()
        self.graph_writes += 1

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self._one(RUNS, "id", run_id)

    def get_edge_by_key(self, edge_key: str) -> dict[str, Any] | None:
        return self._one(EDGES, "edge_key", edge_key)

    def upsert_edge(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = _pick(row, EDGE_COLS)
        payload.pop("id", None)
        existing = self.get_edge_by_key(row["edge_key"])
        if existing:
            self.sb.table(EDGES).update(payload).eq("id", existing["id"]).execute()
            self.graph_writes += 1
            return self.get_edge_by_key(row["edge_key"]) or existing
        try:
            self.sb.table(EDGES).insert(payload).execute()
            self.graph_writes += 1
        except Exception:
            raced = self.get_edge_by_key(row["edge_key"])
            if not raced:
                raise
            self.sb.table(EDGES).update(payload).eq("id", raced["id"]).execute()
            self.graph_writes += 1
            return self.get_edge_by_key(row["edge_key"]) or raced
        return self.get_edge_by_key(row["edge_key"]) or payload

    def get_evidence(self, edge_id: str, evidence_key: str) -> dict[str, Any] | None:
        resp = (
            self.sb.table(EVIDENCE)
            .select("*")
            .eq("edge_id", edge_id)
            .eq("evidence_key", evidence_key)
            .limit(1)
            .execute()
        )
        rows = list(resp.data or [])
        return dict(rows[0]) if rows else None

    def insert_evidence(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = _pick(row, EVIDENCE_COLS)
        payload.pop("id", None)
        payload.setdefault("evidence_json", {})
        existing = self.get_evidence(row["edge_id"], row["evidence_key"])
        if existing:
            self.sb.table(EVIDENCE).update({"last_seen_run_id": payload.get("last_seen_run_id")}).eq(
                "id", existing["id"]
            ).execute()
            self.graph_writes += 1
            return self.get_evidence(row["edge_id"], row["evidence_key"]) or existing
        try:
            self.sb.table(EVIDENCE).insert(payload).execute()
            self.graph_writes += 1
        except Exception:
            raced = self.get_evidence(row["edge_id"], row["evidence_key"])
            if not raced:
                raise
            self.sb.table(EVIDENCE).update({"last_seen_run_id": payload.get("last_seen_run_id")}).eq(
                "id", raced["id"]
            ).execute()
            self.graph_writes += 1
            return self.get_evidence(row["edge_id"], row["evidence_key"]) or raced
        return self.get_evidence(row["edge_id"], row["evidence_key"]) or payload

    def update_evidence(self, evidence_id: str, patch: dict[str, Any]) -> None:
        self.sb.table(EVIDENCE).update(patch).eq("id", evidence_id).execute()
        self.graph_writes += 1

    def list_evidence(self, edge_id: str) -> list[dict[str, Any]]:
        resp = self.sb.table(EVIDENCE).select("*").eq("edge_id", edge_id).execute()
        return [dict(r) for r in (resp.data or [])]

    def _context_base_query(self, *, relation_type: str, relation_key: str, content_type: str | None = None):
        q = (
            self.sb.table(EDGES)
            .select(EDGE_SELECT)
            .eq("edge_kind", "CONTEXT")
            .eq("relation_type", relation_type)
            .eq("relation_key", relation_key)
            .eq("status", "ACCEPTED")
            .eq("is_active", True)
        )
        if content_type:
            q = q.eq("source_content_type", content_type)
        return q

    def count_context_edges(
        self,
        *,
        relation_type: str,
        relation_key: str,
        content_type: str | None = None,
    ) -> int:
        q = (
            self.sb.table(EDGES)
            .select("id", count="exact")
            .eq("edge_kind", "CONTEXT")
            .eq("relation_type", relation_type)
            .eq("relation_key", relation_key)
            .eq("status", "ACCEPTED")
            .eq("is_active", True)
        )
        if content_type:
            q = q.eq("source_content_type", content_type)
        resp = q.limit(1).execute()
        return int(getattr(resp, "count", None) or 0)

    def query_context_edges(
        self,
        *,
        relation_type: str,
        relation_key: str,
        content_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[dict[str, Any]]:
        page_n = max(int(page), 1)
        size_n = max(int(page_size), 1)
        start = (page_n - 1) * size_n
        end = start + size_n - 1
        q = self._context_base_query(
            relation_type=relation_type,
            relation_key=relation_key,
            content_type=content_type,
        )
        for col in CONTEXT_ORDER:
            q = q.order(col)
        resp = q.range(start, end).execute()
        return [dict(r) for r in (resp.data or [])]

    def query_item_context_edges(self, *, content_type: str, content_id: str) -> list[dict[str, Any]]:
        resp = (
            self.sb.table(EDGES)
            .select(EDGE_SELECT)
            .eq("edge_kind", "CONTEXT")
            .eq("source_content_type", content_type)
            .eq("source_content_id", content_id)
            .eq("status", "ACCEPTED")
            .eq("is_active", True)
            .execute()
        )
        return [dict(r) for r in (resp.data or [])]

    def query_edges_for_contexts(
        self,
        contexts: list[tuple[str, str]],
        *,
        exclude_content: tuple[str, str] | None = None,
        limit: int = RELATED_CONTEXT_LIMIT,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen = set()
        bound = max(int(limit), 1)
        for relation_type, relation_key in contexts:
            q = self._context_base_query(relation_type=relation_type, relation_key=relation_key)
            for col in CONTEXT_ORDER:
                q = q.order(col)
            resp = q.range(0, bound - 1).execute()
            for row in resp.data or []:
                if exclude_content and (
                    row.get("source_content_type"),
                    row.get("source_content_id"),
                ) == exclude_content:
                    continue
                key = row.get("id") or row.get("edge_key")
                if key in seen:
                    continue
                seen.add(key)
                out.append(dict(row))
        return out

    def query_stale_scope_edges(
        self,
        *,
        source_content_type: str,
        edge_kind: str,
        relation_type: str | None = None,
        relation_key: str | None = None,
        exclude_run_id: str,
    ) -> list[dict[str, Any]]:
        q = (
            self.sb.table(EDGES)
            .select(EDGE_SELECT)
            .eq("source_content_type", source_content_type)
            .eq("edge_kind", edge_kind)
            .eq("is_active", True)
            .neq("last_seen_run_id", exclude_run_id)
        )
        if relation_type:
            q = q.eq("relation_type", relation_type)
        if relation_key:
            q = q.eq("relation_key", relation_key)
        resp = q.execute()
        return [dict(r) for r in (resp.data or [])]

    def mark_edges_stale(self, edge_ids: list[str], *, stale_at: str, updated_at: str) -> int:
        if not edge_ids:
            return 0
        count = 0
        for chunk in _chunks(edge_ids):
            self.sb.table(EDGES).update(
                {"is_active": False, "stale_at": stale_at, "updated_at": updated_at}
            ).in_("id", chunk).execute()
            self.graph_writes += 1
            count += len(chunk)
        return count
