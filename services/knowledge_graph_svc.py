"""OBJ-GRAPH persistence and public read model.

Producer candidates in, semantic edges/evidence out. No source-table writes.
Stale mutation only after a COMPLETED apply run, and only for completed sources.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

from services.knowledge_graph_producers import GraphCandidate, canonical_json
from services.knowledge_graph_rules import RULE_SET_VERSION
from services.time import now_kst, serialize_business_datetime

PUBLIC_FORBIDDEN_FIELDS = frozenset(
    {
        "legal_applicable",
        "legal_score",
        "applies_to_company",
        "obligation_verdict",
        "violation",
        "compliance_score",
        "user_id",
        "company_id",
        "factory_id",
        "diagnosis_id",
        "evidence",
        "evidence_key",
        "method",
        "rule_id",
        "rule_version",
    }
)

SOURCE_KEYS = {
    "guide": "KOSHA_GUIDE",
    "material": "SAFETY_MATERIAL",
    "accident": "ACCIDENT",
    "law": "LAW_UPDATE",
    "precedent": "PRECEDENT",
    "knowledge": "KNOWLEDGE_CENTER",
}

CONTENT_TO_SOURCE = {v: k for k, v in SOURCE_KEYS.items()}

TAI_ORIGIN = "https://taieng.co.kr"


def make_edge_key(
    *,
    edge_kind: str,
    source_content_type: str,
    source_content_id: str,
    relation_type: str,
    relation_key: str | None = None,
    target_content_type: str | None = None,
    target_content_id: str | None = None,
) -> str:
    """Single canonical identity function. method/rule/hash never included."""
    kind = str(edge_kind or "").upper()
    src_type = str(source_content_type or "").strip()
    src_id = str(source_content_id or "").strip()
    rel = str(relation_type or "").strip()
    if kind == "CONTEXT":
        key = str(relation_key or "").strip()
        if not key:
            raise ValueError("CONTEXT_RELATION_KEY_REQUIRED")
        return f"CTX|{src_type}|{src_id}|{rel}|{key}"
    if kind == "DIRECT":
        tgt_type = str(target_content_type or "").strip()
        tgt_id = str(target_content_id or "").strip()
        if not tgt_type or not tgt_id:
            raise ValueError("DIRECT_TARGET_REQUIRED")
        return f"DIR|{src_type}|{src_id}|{rel}|{tgt_type}|{tgt_id}"
    raise ValueError("EDGE_KIND_INVALID")


def make_evidence_key(payload: dict[str, Any]) -> str:
    canonical = {
        "method": payload.get("method"),
        "evidence_type": payload.get("evidence_type"),
        "source_field": payload.get("source_field"),
        "evidence_value": payload.get("evidence_value"),
        "rule_id": payload.get("rule_id"),
        "rule_version": payload.get("rule_version"),
        "source_version": payload.get("source_version"),
        "source_content_hash": payload.get("source_content_hash"),
    }
    return hashlib.sha256(canonical_json(canonical).encode("utf-8")).hexdigest()


def _ts(clock=None) -> str:
    return serialize_business_datetime(now_kst(clock) if clock else now_kst())


@dataclass
class KnowledgeRecord:
    content_type: str
    content_id: str
    title: str | None = None
    summary: str | None = None
    tai_url: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    published_at: str | None = None
    category: str | None = None
    is_public_current: bool = True

    def public_item(self) -> dict[str, Any]:
        return {
            "content_type": self.content_type,
            "content_id": self.content_id,
            "title": self.title,
            "summary": self.summary,
            "tai_url": self.tai_url,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "published_at": self.published_at,
            "category": self.category,
        }


class GraphStore(Protocol):
    def insert_run(self, row: dict[str, Any]) -> dict[str, Any]: ...
    def update_run(self, run_id: str, patch: dict[str, Any]) -> None: ...
    def get_edge_by_key(self, edge_key: str) -> dict[str, Any] | None: ...
    def upsert_edge(self, row: dict[str, Any]) -> dict[str, Any]: ...
    def get_evidence(self, edge_id: str, evidence_key: str) -> dict[str, Any] | None: ...
    def insert_evidence(self, row: dict[str, Any]) -> dict[str, Any]: ...
    def update_evidence(self, evidence_id: str, patch: dict[str, Any]) -> None: ...
    def list_edges(self) -> list[dict[str, Any]]: ...
    def list_evidence(self, edge_id: str) -> list[dict[str, Any]]: ...
    def source_writes(self) -> int: ...


class MemoryGraphStore:
    def __init__(self):
        self.runs: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, dict[str, Any]] = {}
        self.evidence: dict[tuple[str, str], dict[str, Any]] = {}
        self._source_writes = 0

    def source_writes(self) -> int:
        return self._source_writes

    def insert_run(self, row: dict[str, Any]) -> dict[str, Any]:
        run_id = row.get("id") or str(uuid.uuid4())
        stored = dict(row)
        stored["id"] = run_id
        self.runs[run_id] = stored
        return dict(stored)

    def update_run(self, run_id: str, patch: dict[str, Any]) -> None:
        self.runs[run_id].update(patch)

    def get_edge_by_key(self, edge_key: str) -> dict[str, Any] | None:
        row = self.edges.get(edge_key)
        return dict(row) if row else None

    def upsert_edge(self, row: dict[str, Any]) -> dict[str, Any]:
        existing = self.edges.get(row["edge_key"])
        if existing:
            existing.update(row)
            existing["id"] = existing.get("id") or str(uuid.uuid4())
            return dict(existing)
        stored = dict(row)
        stored["id"] = stored.get("id") or str(uuid.uuid4())
        self.edges[stored["edge_key"]] = stored
        return dict(stored)

    def get_evidence(self, edge_id: str, evidence_key: str) -> dict[str, Any] | None:
        row = self.evidence.get((edge_id, evidence_key))
        return dict(row) if row else None

    def insert_evidence(self, row: dict[str, Any]) -> dict[str, Any]:
        stored = dict(row)
        stored["id"] = stored.get("id") or str(uuid.uuid4())
        self.evidence[(stored["edge_id"], stored["evidence_key"])] = stored
        return dict(stored)

    def update_evidence(self, evidence_id: str, patch: dict[str, Any]) -> None:
        for row in self.evidence.values():
            if row.get("id") == evidence_id:
                row.update(patch)
                return

    def list_edges(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.edges.values()]

    def list_evidence(self, edge_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self.evidence.values() if row.get("edge_id") == edge_id]


class MemoryHydrator:
    def __init__(self, records: Iterable[KnowledgeRecord] | None = None):
        self.records: dict[tuple[str, str], KnowledgeRecord] = {}
        for rec in records or []:
            self.records[(rec.content_type, rec.content_id)] = rec

    def get(self, content_type: str, content_id: str) -> KnowledgeRecord | None:
        return self.records.get((content_type, content_id))

    def get_many(self, pairs: Iterable[tuple[str, str]]) -> dict[tuple[str, str], KnowledgeRecord]:
        out = {}
        for pair in pairs:
            rec = self.get(*pair)
            if rec is not None:
                out[pair] = rec
        return out


def default_tai_url(content_type: str, content_id: str, *, construction: bool = False) -> str:
    if content_type == "KOSHA_GUIDE":
        return f"{TAI_ORIGIN}/safety-guide/{content_id}"
    if content_type == "SAFETY_MATERIAL":
        return f"{TAI_ORIGIN}/safety-news-detail.html?id={content_id}"
    if content_type == "ACCIDENT" and construction:
        return f"{TAI_ORIGIN}/accident-case-detail.html?id={content_id}&tab=construction"
    if content_type == "ACCIDENT":
        return f"{TAI_ORIGIN}/accident/{content_id}"
    if content_type == "LAW_UPDATE":
        return f"{TAI_ORIGIN}/law/{content_id}"
    if content_type == "PRECEDENT":
        return f"{TAI_ORIGIN}/precedent/{content_id}"
    if content_type == "KNOWLEDGE_CENTER":
        return f"{TAI_ORIGIN}/kb/{content_id}"
    return None


def persist_candidates(
    store: GraphStore,
    candidates: Iterable[GraphCandidate],
    *,
    run_id: str,
    clock=None,
) -> dict[str, int]:
    ts = _ts(clock)
    accepted = 0
    rejected = 0
    duplicate_prevented = 0
    semantic_edges = 0
    evidence_count = 0
    reactivated = 0
    for cand in candidates:
        if cand.edge_kind == "CONTEXT" and not cand.relation_key:
            raise ValueError("CONTEXT_RELATION_KEY_REQUIRED")
        if cand.edge_kind == "DIRECT" and (not cand.target_content_type or not cand.target_content_id):
            raise ValueError("DIRECT_TARGET_REQUIRED")
        edge_key = make_edge_key(
            edge_kind=cand.edge_kind,
            source_content_type=cand.source_content_type,
            source_content_id=cand.source_content_id,
            relation_type=cand.relation_type,
            relation_key=cand.relation_key,
            target_content_type=cand.target_content_type,
            target_content_id=cand.target_content_id,
        )
        existing = store.get_edge_by_key(edge_key)
        edge_row = {
            "edge_key": edge_key,
            "edge_kind": cand.edge_kind,
            "source_content_type": cand.source_content_type,
            "source_content_id": cand.source_content_id,
            "relation_type": cand.relation_type,
            "relation_key": cand.relation_key,
            "relation_label": cand.relation_label,
            "target_content_type": cand.target_content_type,
            "target_content_id": cand.target_content_id,
            "status": cand.status,
            "is_active": True,
            "last_seen_run_id": run_id,
            "stale_at": None,
            "updated_at": ts,
        }
        if existing:
            edge_row["id"] = existing["id"]
            edge_row["first_seen_run_id"] = existing.get("first_seen_run_id") or run_id
            edge_row["created_at"] = existing.get("created_at") or ts
            if existing.get("is_active") is False or existing.get("stale_at"):
                reactivated += 1
            if existing.get("status") == "ACCEPTED" and cand.status != "ACCEPTED":
                edge_row["status"] = "ACCEPTED"
        else:
            edge_row["first_seen_run_id"] = run_id
            edge_row["created_at"] = ts
            semantic_edges += 1
        stored_edge = store.upsert_edge(edge_row)
        if cand.status == "ACCEPTED":
            accepted += 1
        else:
            rejected += 1
        ev_payload = {
            "method": cand.method,
            "evidence_type": cand.evidence_type,
            "source_field": cand.source_field,
            "evidence_value": cand.evidence_value,
            "rule_id": cand.rule_id,
            "rule_version": cand.rule_version,
            "source_version": cand.source_version,
            "source_content_hash": cand.source_content_hash,
        }
        evidence_key = make_evidence_key(ev_payload)
        found = store.get_evidence(stored_edge["id"], evidence_key)
        if found:
            store.update_evidence(found["id"], {"last_seen_run_id": run_id})
            duplicate_prevented += 1
        else:
            store.insert_evidence(
                {
                    "edge_id": stored_edge["id"],
                    "evidence_key": evidence_key,
                    **ev_payload,
                    "evidence_json": {},
                    "created_at": ts,
                    "last_seen_run_id": run_id,
                }
            )
            evidence_count += 1
    return {
        "accepted": accepted,
        "rejected": rejected,
        "duplicate_prevented": duplicate_prevented,
        "semantic_edges": semantic_edges,
        "evidence_count": evidence_count,
        "reactivated": reactivated,
    }


def stale_unseen_edges(
    store: GraphStore,
    *,
    run_id: str,
    completed_content_types: set[str],
    context_filter: tuple[str, str] | None,
    clock=None,
) -> int:
    if not completed_content_types:
        return 0
    ts = _ts(clock)
    count = 0
    for edge in store.list_edges():
        if edge.get("source_content_type") not in completed_content_types:
            continue
        if context_filter:
            rel_type, rel_key = context_filter
            if edge.get("edge_kind") == "CONTEXT":
                if edge.get("relation_type") != rel_type or edge.get("relation_key") != rel_key:
                    continue
            else:
                continue
        if edge.get("last_seen_run_id") == run_id:
            continue
        if edge.get("is_active") is False and edge.get("stale_at"):
            continue
        store.upsert_edge(
            {
                **edge,
                "is_active": False,
                "stale_at": ts,
                "updated_at": ts,
            }
        )
        count += 1
    return count


@dataclass
class RefreshReport:
    dry_run: bool
    status: str
    run_id: str | None
    scope: dict[str, Any]
    knowledge_items_scanned: int = 0
    candidates_generated: int = 0
    accepted: int = 0
    rejected: int = 0
    semantic_edges: int = 0
    evidence_count: int = 0
    duplicate_prevented: int = 0
    no_relation_items: int = 0
    stale_count: int = 0
    reactivated_count: int = 0
    source_errors: dict[str, str] = field(default_factory=dict)
    by_source: dict[str, dict[str, int]] = field(default_factory=dict)
    by_relation_type: dict[str, int] = field(default_factory=dict)
    by_method: dict[str, int] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "status": self.status,
            "run_id": self.run_id,
            "scope": self.scope,
            "knowledge_items_scanned": self.knowledge_items_scanned,
            "candidates_generated": self.candidates_generated,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "semantic_edges": self.semantic_edges,
            "evidence_count": self.evidence_count,
            "duplicate_prevented": self.duplicate_prevented,
            "no_relation_items": self.no_relation_items,
            "stale_count": self.stale_count,
            "reactivated_count": self.reactivated_count,
            "source_errors": self.source_errors,
            "by_source": self.by_source,
            "by_relation_type": self.by_relation_type,
            "by_method": self.by_method,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


def _filter_context(candidates: list[GraphCandidate], context_filter: tuple[str, str] | None) -> list[GraphCandidate]:
    if not context_filter:
        return candidates
    rel_type, rel_key = context_filter
    return [
        c
        for c in candidates
        if c.edge_kind == "CONTEXT" and c.relation_type == rel_type and c.relation_key == rel_key
    ]


def refresh_graph(
    *,
    store: GraphStore,
    produced_by_source: dict[str, list[GraphCandidate]],
    scanned_by_source: dict[str, int],
    failed_sources: dict[str, str] | None = None,
    apply: bool,
    context_filter: tuple[str, str] | None = None,
    clock=None,
    abort: bool = False,
    abort_message: str = "REFRESH_ABORTED",
) -> RefreshReport:
    failed_sources = dict(failed_sources or {})
    scope = {
        "sources": sorted(set(list(produced_by_source) + list(scanned_by_source) + list(failed_sources))),
        "context": {"relation_type": context_filter[0], "relation_key": context_filter[1]} if context_filter else None,
    }
    report = RefreshReport(dry_run=not apply, status="RUNNING", run_id=None, scope=scope)
    all_cands: list[GraphCandidate] = []
    items_with_rel: set[tuple[str, str]] = set()
    for source_key, cands in produced_by_source.items():
        scoped = _filter_context(cands, context_filter)
        report.by_source.setdefault(
            source_key,
            {"scanned": scanned_by_source.get(source_key, 0), "accepted": 0, "candidates": 0},
        )
        report.by_source[source_key]["candidates"] = len(scoped)
        for cand in scoped:
            all_cands.append(cand)
            items_with_rel.add((cand.source_content_type, cand.source_content_id))
            report.by_relation_type[cand.relation_type] = report.by_relation_type.get(cand.relation_type, 0) + 1
            report.by_method[cand.method] = report.by_method.get(cand.method, 0) + 1
            if cand.status == "ACCEPTED":
                report.by_source[source_key]["accepted"] += 1
    report.knowledge_items_scanned = sum(scanned_by_source.values())
    report.candidates_generated = len(all_cands)
    report.no_relation_items = max(report.knowledge_items_scanned - len(items_with_rel), 0)

    if abort:
        report.status = "FAILED"
        report.error_code = "REFRESH_FAILED"
        report.error_message = abort_message
        if apply:
            run = store.insert_run(
                {
                    "run_type": "MANUAL_REFRESH",
                    "scope_json": scope,
                    "rule_set_version": RULE_SET_VERSION,
                    "status": "FAILED",
                    "dry_run": False,
                    "started_at": _ts(clock),
                    "completed_at": _ts(clock),
                    "error_code": report.error_code,
                    "error_message": abort_message,
                    "metrics_json": {"source_errors": failed_sources},
                }
            )
            report.run_id = run["id"]
        return report

    if not apply:
        report.accepted = sum(1 for c in all_cands if c.status == "ACCEPTED")
        report.rejected = sum(1 for c in all_cands if c.status != "ACCEPTED")
        keys = {make_edge_key(
            edge_kind=c.edge_kind,
            source_content_type=c.source_content_type,
            source_content_id=c.source_content_id,
            relation_type=c.relation_type,
            relation_key=c.relation_key,
            target_content_type=c.target_content_type,
            target_content_id=c.target_content_id,
        ) for c in all_cands}
        report.semantic_edges = len(keys)
        report.evidence_count = len({make_evidence_key({
            "method": c.method,
            "evidence_type": c.evidence_type,
            "source_field": c.source_field,
            "evidence_value": c.evidence_value,
            "rule_id": c.rule_id,
            "rule_version": c.rule_version,
            "source_version": c.source_version,
            "source_content_hash": c.source_content_hash,
        }) for c in all_cands})
        report.status = "DRY_RUN"
        report.source_errors = failed_sources
        return report

    run = store.insert_run(
        {
            "run_type": "MANUAL_REFRESH",
            "scope_json": scope,
            "rule_set_version": RULE_SET_VERSION,
            "status": "RUNNING",
            "dry_run": False,
            "started_at": _ts(clock),
            "knowledge_items_scanned": report.knowledge_items_scanned,
            "candidates_generated": report.candidates_generated,
            "metrics_json": {},
        }
    )
    report.run_id = run["id"]
    metrics = persist_candidates(store, all_cands, run_id=run["id"], clock=clock)
    report.accepted = metrics["accepted"]
    report.rejected = metrics["rejected"]
    report.duplicate_prevented = metrics["duplicate_prevented"]
    report.semantic_edges = metrics["semantic_edges"]
    report.evidence_count = metrics["evidence_count"]
    report.reactivated_count = metrics["reactivated"]
    completed_types = {
        SOURCE_KEYS[k]
        for k in produced_by_source
        if k not in failed_sources and k in SOURCE_KEYS
    }
    report.stale_count = stale_unseen_edges(
        store,
        run_id=run["id"],
        completed_content_types=completed_types,
        context_filter=context_filter,
        clock=clock,
    )
    report.source_errors = failed_sources
    report.status = "COMPLETED"
    store.update_run(
        run["id"],
        {
            "status": "COMPLETED",
            "completed_at": _ts(clock),
            "accepted": report.accepted,
            "rejected": report.rejected,
            "duplicate_prevented": report.duplicate_prevented,
            "no_relation_items": report.no_relation_items,
            "metrics_json": {
                "by_source": report.by_source,
                "by_relation_type": report.by_relation_type,
                "by_method": report.by_method,
                "stale_count": report.stale_count,
                "source_errors": failed_sources,
            },
        },
    )
    return report


def _public_edge(edge: dict[str, Any], hydrator: MemoryHydrator) -> tuple[dict[str, Any], KnowledgeRecord] | None:
    if edge.get("status") != "ACCEPTED":
        return None
    if edge.get("is_active") is not True:
        return None
    if edge.get("stale_at"):
        return None
    rec = hydrator.get(edge["source_content_type"], edge["source_content_id"])
    if rec is None or not rec.is_public_current:
        return None
    return edge, rec


def strip_forbidden(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if k not in PUBLIC_FORBIDDEN_FIELDS}


def read_context(
    store: GraphStore,
    hydrator: MemoryHydrator,
    *,
    relation_type: str,
    relation_key: str,
    page: int = 1,
    page_size: int = 20,
    content_type: str | None = None,
) -> dict[str, Any]:
    matched = []
    label = None
    for edge in store.list_edges():
        if edge.get("edge_kind") != "CONTEXT":
            continue
        if edge.get("relation_type") != relation_type or edge.get("relation_key") != relation_key:
            continue
        if content_type and edge.get("source_content_type") != content_type:
            continue
        public = _public_edge(edge, hydrator)
        if not public:
            continue
        edge, rec = public
        label = edge.get("relation_label") or label
        matched.append(rec)
    seen = set()
    items = []
    for rec in matched:
        ident = (rec.content_type, rec.content_id)
        if ident in seen:
            continue
        seen.add(ident)
        items.append(rec)
    items.sort(key=lambda r: ((r.published_at or ""), r.content_type, r.content_id), reverse=False)
    items.sort(key=lambda r: r.published_at or "", reverse=True)
    total = len(items)
    start = max(page - 1, 0) * page_size
    page_items = items[start:start + page_size]
    return strip_forbidden(
        {
            "status": "ok",
            "context": {
                "relation_type": relation_type,
                "relation_key": relation_key,
                "relation_label": label,
            },
            "total": total,
            "items": [strip_forbidden(r.public_item()) for r in page_items],
        }
    )


def read_item_contexts(
    store: GraphStore,
    hydrator: MemoryHydrator,
    *,
    content_type: str,
    content_id: str,
) -> dict[str, Any]:
    rec = hydrator.get(content_type, content_id)
    if rec is None or not rec.is_public_current:
        return strip_forbidden({"content_type": content_type, "content_id": content_id, "contexts": []})
    contexts = []
    seen = set()
    for edge in store.list_edges():
        if edge.get("edge_kind") != "CONTEXT":
            continue
        if edge.get("source_content_type") != content_type or edge.get("source_content_id") != content_id:
            continue
        if not _public_edge(edge, hydrator):
            continue
        ident = (edge.get("relation_type"), edge.get("relation_key"))
        if ident in seen:
            continue
        seen.add(ident)
        contexts.append(
            {
                "relation_type": edge.get("relation_type"),
                "relation_key": edge.get("relation_key"),
                "relation_label": edge.get("relation_label"),
            }
        )
    contexts.sort(key=lambda c: (c["relation_type"] or "", c["relation_key"] or ""))
    return strip_forbidden(
        {
            "content_type": content_type,
            "content_id": content_id,
            "contexts": contexts,
        }
    )


def read_related(
    store: GraphStore,
    hydrator: MemoryHydrator,
    *,
    content_type: str,
    content_id: str,
) -> dict[str, Any]:
    source_contexts = []
    for edge in store.list_edges():
        if edge.get("edge_kind") != "CONTEXT":
            continue
        if edge.get("source_content_type") != content_type or edge.get("source_content_id") != content_id:
            continue
        if not _public_edge(edge, hydrator):
            continue
        source_contexts.append((edge.get("relation_type"), edge.get("relation_key")))
    context_set = set(source_contexts)
    counts: dict[tuple[str, str], dict[str, Any]] = {}
    for edge in store.list_edges():
        if edge.get("edge_kind") != "CONTEXT":
            continue
        ident = (edge.get("relation_type"), edge.get("relation_key"))
        if ident not in context_set:
            continue
        if edge.get("source_content_type") == content_type and edge.get("source_content_id") == content_id:
            continue
        public = _public_edge(edge, hydrator)
        if not public:
            continue
        _, rec = public
        key = (rec.content_type, rec.content_id)
        slot = counts.setdefault(key, {"rec": rec, "shared": set()})
        slot["shared"].add(ident)
    ranked = []
    for slot in counts.values():
        rec = slot["rec"]
        ranked.append(
            strip_forbidden(
                {
                    **rec.public_item(),
                    "shared_context_count": len(slot["shared"]),
                }
            )
        )
    ranked.sort(key=lambda item: (item.get("content_type") or "", item.get("content_id") or ""))
    ranked.sort(key=lambda item: item.get("published_at") or "", reverse=True)
    ranked.sort(key=lambda item: -int(item.get("shared_context_count") or 0))
    return strip_forbidden(
        {
            "content_type": content_type,
            "content_id": content_id,
            "items": ranked,
        }
    )
