"""Manual OBJ-GRAPH refresh. Default is DRY RUN. No daily cron.

  python scripts/refresh_knowledge_graph.py
  python scripts/refresh_knowledge_graph.py --source guide --context equipment:forklift
  python scripts/refresh_knowledge_graph.py --apply --source guide --context equipment:forklift

Production --apply is a later gate. This script does not apply the migration.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.knowledge_graph_producers import (
    produce_accident_relations,
    produce_guide_material_shadow,
    produce_guide_relations,
    produce_knowledge_center_relations,
    produce_law_relations,
    produce_precedent_relations,
    produce_safety_material_relations,
)
from services.knowledge_graph_svc import (
    MemoryGraphStore,
    SOURCE_KEYS,
    refresh_graph,
)
from services.knowledge_graph_store import GRAPH_TABLES, SOURCE_TABLES, SupabaseGraphStore
from services.time import now_kst

PAGE = 1000
APPLY_ENV = "KNOWLEDGE_GRAPH_APPLY_ENABLED"


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    if not os.getenv("SUPABASE_SERVICE_KEY") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"):
        os.environ["SUPABASE_SERVICE_KEY"] = os.environ["SUPABASE_SERVICE_ROLE_KEY"]


def _production_supabase():
    """HTTP/1.1 client. HTTP/2 stream IDs cap around 19999 and abort large applies."""
    import httpx
    from supabase import create_client
    from supabase.lib.client_options import SyncClientOptions

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")
    http = httpx.Client(http2=False, timeout=120.0)
    return create_client(url, key, options=SyncClientOptions(httpx_client=http))


def _parse_context(raw: str | None) -> tuple[str, str] | None:
    if not raw:
        return None
    if ":" not in raw:
        raise SystemExit("--context must be relation_type:relation_key")
    rel_type, rel_key = raw.split(":", 1)
    return rel_type.strip(), rel_key.strip()


def _paged_filtered(sb, table: str, columns: str, eq: dict | None = None) -> list[dict]:
    rows: list[dict] = []
    start = 0
    filters = dict(eq or {})
    while True:
        q = sb.table(table).select(columns)
        for key, value in filters.items():
            q = q.eq(key, value)
        resp = q.range(start, start + PAGE - 1).execute()
        batch = list(resp.data or [])
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        start += PAGE
    return rows


def _paged(sb, table: str, columns: str) -> list[dict]:
    return _paged_filtered(sb, table, columns)


def load_production_sources(
    sb, wanted: set[str], stats: dict | None = None
) -> tuple[dict[str, list], dict[str, str]]:
    """Fetch current public contracts. Does not write source tables."""
    items: dict[str, list] = {}
    errors: dict[str, str] = {}
    stats = stats if stats is not None else {}
    if "guide" in wanted:
        try:
            rows = _paged(
                sb,
                "kosha_guide_current",
                "guide_no,guide_title,category_name,category_code,content_hash,guide_url,regist_date",
            )
            items["guide"] = [
                {
                    "content_id": r.get("guide_no"),
                    "guide_no": r.get("guide_no"),
                    "guide_title": r.get("guide_title"),
                    "category": r.get("category_name"),
                    "content_hash": r.get("content_hash"),
                    "source_url": r.get("guide_url"),
                    "published_at": r.get("regist_date"),
                }
                for r in rows
                if r.get("guide_no")
            ]
        except Exception as exc:
            errors["guide"] = str(exc)
    if "material" in wanted:
        try:
            snaps = (
                sb.table("kosha_safety_material_snapshots")
                .select("id,status,completed_at")
                .eq("status", "COMPLETED")
                .order("completed_at", desc=True)
                .limit(1)
                .execute()
            )
            snap = (snaps.data or [None])[0]
            if not snap:
                items["material"] = []
                stats["material_membership_declared"] = 0
                stats["material_membership_fetched"] = 0
            else:
                count_resp = (
                    sb.table("kosha_safety_material_snapshot_items")
                    .select("material_id", count="exact")
                    .eq("snapshot_id", snap["id"])
                    .limit(1)
                    .execute()
                )
                declared = int(getattr(count_resp, "count", None) or 0)
                mem = _paged_filtered(
                    sb,
                    "kosha_safety_material_snapshot_items",
                    "material_id",
                    eq={"snapshot_id": snap["id"]},
                )
                ids = [r["material_id"] for r in mem if r.get("material_id")]
                stats["material_membership_declared"] = declared or len(ids)
                stats["material_membership_fetched"] = len(ids)
                catalog = []
                details = {}
                for i in range(0, len(ids), PAGE):
                    chunk = ids[i : i + PAGE]
                    resp = sb.table("kosha_safety_materials").select("id,title,category,url").in_("id", chunk).execute()
                    catalog.extend(resp.data or [])
                    dresp = (
                        sb.table("kosha_safety_material_details")
                        .select("material_id,source_description,source_content_hash")
                        .in_("material_id", chunk)
                        .execute()
                    )
                    for row in dresp.data or []:
                        details[row.get("material_id")] = row
                items["material"] = [
                    {
                        "content_id": r.get("id"),
                        "id": r.get("id"),
                        "title": r.get("title"),
                        "category": r.get("category"),
                        "description": (details.get(r.get("id")) or {}).get("source_description"),
                        "source_version": (details.get(r.get("id")) or {}).get("source_content_hash"),
                        "source_url": r.get("url"),
                        "in_current_snapshot": True,
                    }
                    for r in catalog
                ]
        except Exception as exc:
            errors["material"] = str(exc)
    if "accident" in wanted:
        try:
            domestic = _paged(sb, "kosha_accident_cases", "id,title,reg_dt,file_url")
            kosha_items = [
                {
                    "content_id": r.get("id"),
                    "id": r.get("id"),
                    "title": r.get("title"),
                    "source_url": r.get("file_url"),
                    "published_at": r.get("reg_dt"),
                }
                for r in domestic
                if r.get("id")
            ]
            csi_rows = _paged_filtered(
                sb,
                "csi_accident_current",
                "content_id,title,summary,occurred_at,construction_type,process_major,"
                "process_minor,object_major,object_minor,work_process,accident_type_major,"
                "accident_type,source_content_hash,source_dataset_url,identity_status",
                eq={"identity_status": "READY"},
            )
            csi_items = []
            for r in csi_rows:
                cid = r.get("content_id")
                if not cid or str(r.get("identity_status") or "") != "READY":
                    continue
                summary = r.get("summary")
                csi_items.append(
                    {
                        "content_id": cid,
                        "id": cid,
                        "title": r.get("title"),
                        "summary": summary,
                        "accident_summary": summary,
                        "construction_type": r.get("construction_type"),
                        "process_major": r.get("process_major"),
                        "process_minor": r.get("process_minor"),
                        "object_major": r.get("object_major"),
                        "object_minor": r.get("object_minor"),
                        "work_process": r.get("work_process"),
                        "accident_type_major": r.get("accident_type_major"),
                        "accident_type": r.get("accident_type"),
                        "source_url": r.get("source_dataset_url"),
                        "published_at": r.get("occurred_at"),
                        "source_version": r.get("source_content_hash"),
                        "identity_status": "READY",
                    }
                )
            items["accident"] = kosha_items + csi_items
            stats["accident_kosha_scanned"] = len(kosha_items)
            stats["accident_csi_scanned"] = len(csi_items)
            stats["accident_construction_included"] = 0
        except Exception as exc:
            errors["accident"] = str(exc)
    if "law" in wanted:
        try:
            rows = _paged_filtered(
                sb,
                "law_revision_board",
                "id,law_name,summary,status,is_public,enforcement_date",
                eq={"is_public": True, "status": "PUBLISHED"},
            )
            items["law"] = [
                {
                    "content_id": r.get("id"),
                    "id": r.get("id"),
                    "law_name": r.get("law_name"),
                    "summary": r.get("summary"),
                    "status": r.get("status"),
                    "is_public": r.get("is_public"),
                    "published_at": r.get("enforcement_date"),
                }
                for r in rows
            ]
        except Exception as exc:
            errors["law"] = str(exc)
    if "precedent" in wanted:
        try:
            rows = _paged(
                sb,
                "industrial_accident_precedents",
                "id,case_name,summary,hazard_type,sector",
            )
            items["precedent"] = [
                {
                    "content_id": r.get("id"),
                    "id": r.get("id"),
                    "case_name": r.get("case_name"),
                    "summary": r.get("summary"),
                    "hazard_type": r.get("hazard_type"),
                    "sector": r.get("sector"),
                }
                for r in rows
                if r.get("id")
            ]
        except Exception as exc:
            errors["precedent"] = str(exc)
    if "knowledge" in wanted:
        # MKT API SoT. Stable current/hash not owned by tai-api → DEFERRED.
        items["knowledge"] = []
    return items, errors


def produce_all(
    items_by_source: dict[str, list],
    current_ids: dict[str, set[str] | None],
    failed_sources: dict[str, str] | None = None,
) -> dict[str, list]:
    failed = failed_sources or {}
    out = {}
    if "guide" in items_by_source:
        out["guide"] = produce_guide_relations(items_by_source["guide"], current_ids=current_ids.get("guide"))
        if (
            "material" in items_by_source
            and "guide" not in failed
            and "material" not in failed
        ):
            out["guide_shadow"] = produce_guide_material_shadow(
                items_by_source["guide"],
                items_by_source["material"],
                current_guide_ids=current_ids.get("guide"),
                current_material_ids=current_ids.get("material"),
            )
    if "material" in items_by_source and "material" not in failed:
        out["material"] = produce_safety_material_relations(items_by_source["material"], current_ids=current_ids.get("material"))
    if "accident" in items_by_source and "accident" not in failed:
        out["accident"] = produce_accident_relations(items_by_source["accident"])
    if "law" in items_by_source:
        out["law"] = produce_law_relations(items_by_source["law"])
    if "precedent" in items_by_source:
        out["precedent"] = produce_precedent_relations(items_by_source["precedent"])
    if "knowledge" in items_by_source:
        out["knowledge"] = produce_knowledge_center_relations(items_by_source["knowledge"] or None)
    return out


def _accident_origin_report(candidates) -> dict:
    kosha = []
    csi = []
    for cand in candidates:
        sample = {
            "content_id": cand.source_content_id,
            "source_field": cand.source_field,
            "evidence_value": cand.evidence_value,
            "relation_type": cand.relation_type,
            "relation_key": cand.relation_key,
        }
        if str(cand.source_content_id).startswith("CSI:"):
            csi.append(sample)
        else:
            kosha.append(sample)
    return {
        "kosha": len(kosha),
        "csi": len(csi),
        "combined": len(kosha) + len(csi),
        "csi_samples": csi[:10],
    }


def _scoped_accidents(produced: dict, context_filter: tuple[str, str] | None):
    cands = list(produced.get("accident") or [])
    if not context_filter:
        return cands
    rel_type, rel_key = context_filter
    return [c for c in cands if c.relation_type == rel_type and c.relation_key == rel_key]


def _blocked(message: str) -> int:
    raise SystemExit(
        json.dumps(
            {
                "status": "BLOCKED",
                "error_code": "PRODUCTION_APPLY_GATED",
                "error_message": message,
                "started_at": now_kst().isoformat(),
            },
            ensure_ascii=False,
        )
    )


def main(argv: list[str] | None = None, *, graph_store=None) -> int:
    _load_env()
    p = argparse.ArgumentParser(description="OBJ-GRAPH manual refresh (default dry-run)")
    p.add_argument("--apply", action="store_true", help="Write Graph tables. Requires KNOWLEDGE_GRAPH_APPLY_ENABLED=1.")
    p.add_argument("--all", action="store_true")
    p.add_argument(
        "--source",
        action="append",
        choices=list(SOURCE_KEYS),
        help="Repeatable. guide|material|accident|law|precedent|knowledge",
    )
    p.add_argument("--context", default=None, help="relation_type:relation_key e.g. equipment:forklift")
    p.add_argument("--fixture-json", default=None, help="tests: local JSON sources, no production DB")
    args = p.parse_args(argv)

    wanted = set(args.source or [])
    if args.all or not wanted:
        if args.all:
            wanted = set(SOURCE_KEYS)
        elif not wanted:
            wanted = {"guide"}
    context_filter = _parse_context(args.context)

    failed = {}
    source_stats: dict = {}
    if args.fixture_json:
        with open(args.fixture_json, encoding="utf-8") as fh:
            items_by_source = json.load(fh)
        items_by_source = {k: v for k, v in items_by_source.items() if k in wanted}
    else:
        sb = _production_supabase()
        items_by_source, failed = load_production_sources(sb, wanted, stats=source_stats)

    current_ids = {
        key: {str(item.get("content_id")) for item in rows if item.get("content_id")}
        for key, rows in items_by_source.items()
    }
    produced = produce_all(items_by_source, current_ids, failed_sources=failed)
    scanned = {key: len(rows) for key, rows in items_by_source.items()}
    apply = bool(args.apply)
    if apply and os.getenv(APPLY_ENV) != "1":
        return _blocked("two-key apply required: --apply and KNOWLEDGE_GRAPH_APPLY_ENABLED=1")
    if apply:
        store = graph_store
        if store is None:
            store = SupabaseGraphStore(_production_supabase())
        if isinstance(store, MemoryGraphStore):
            return _blocked("MemoryGraphStore is forbidden on --apply")
        report = refresh_graph(
            store=store,
            produced_by_source=produced,
            scanned_by_source=scanned,
            failed_sources=failed,
            apply=True,
            context_filter=context_filter,
        )
        payload = report.as_dict()
        payload["db_write"] = 1
        payload["source_stats"] = source_stats
        payload["accident_origin_counts"] = _accident_origin_report(_scoped_accidents(produced, context_filter))
        payload["graph_tables"] = sorted(GRAPH_TABLES)
        payload["source_tables"] = sorted(SOURCE_TABLES)
        payload["source_writes"] = store.source_writes()
        payload["started_at"] = now_kst().isoformat()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if report.status == "COMPLETED" else 1
    report = refresh_graph(
        store=MemoryGraphStore(),
        produced_by_source=produced,
        scanned_by_source=scanned,
        failed_sources=failed,
        apply=False,
        context_filter=context_filter,
    )
    payload = report.as_dict()
    payload["db_write"] = 0
    payload["source_stats"] = source_stats
    payload["accident_origin_counts"] = _accident_origin_report(_scoped_accidents(produced, context_filter))
    payload["started_at"] = now_kst().isoformat()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if report.status in {"DRY_RUN", "COMPLETED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
