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
from services.time import now_kst

PAGE = 1000


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    if not os.getenv("SUPABASE_SERVICE_KEY") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"):
        os.environ["SUPABASE_SERVICE_KEY"] = os.environ["SUPABASE_SERVICE_ROLE_KEY"]


def _parse_context(raw: str | None) -> tuple[str, str] | None:
    if not raw:
        return None
    if ":" not in raw:
        raise SystemExit("--context must be relation_type:relation_key")
    rel_type, rel_key = raw.split(":", 1)
    return rel_type.strip(), rel_key.strip()


def _paged(sb, table: str, columns: str) -> list[dict]:
    rows: list[dict] = []
    start = 0
    while True:
        resp = sb.table(table).select(columns).range(start, start + PAGE - 1).execute()
        batch = list(resp.data or [])
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        start += PAGE
    return rows


def load_production_sources(sb, wanted: set[str]) -> tuple[dict[str, list], dict[str, str]]:
    """Fetch current public contracts. Does not write source tables."""
    items: dict[str, list] = {}
    errors: dict[str, str] = {}
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
            else:
                mem = (
                    sb.table("kosha_safety_material_snapshot_items")
                    .select("material_id")
                    .eq("snapshot_id", snap["id"])
                    .execute()
                )
                ids = [r["material_id"] for r in (mem.data or []) if r.get("material_id")]
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
            domestic = _paged(sb, "kosha_accident_cases", "id,title,occurred_at,url")
            construction = _paged(
                sb,
                "kosha_construction_accidents",
                "id,accident_summary,work_type,accident_type,occurred_at",
            )
            items["accident"] = [
                {"content_id": r.get("id"), "id": r.get("id"), "title": r.get("title"), "source_url": r.get("url"), "published_at": r.get("occurred_at")}
                for r in domestic
                if r.get("id")
            ] + [
                {
                    "content_id": r.get("id"),
                    "id": r.get("id"),
                    "accident_summary": r.get("accident_summary"),
                    "work_type": r.get("work_type"),
                    "accident_type": r.get("accident_type"),
                    "published_at": r.get("occurred_at"),
                }
                for r in construction
                if r.get("id")
            ]
        except Exception as exc:
            errors["accident"] = str(exc)
    if "law" in wanted:
        try:
            rows = (
                sb.table("law_revision_board")
                .select("id,law_name,summary,status,is_public,enforcement_date")
                .eq("is_public", True)
                .eq("status", "PUBLISHED")
                .execute()
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
                for r in (rows.data or [])
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


def produce_all(items_by_source: dict[str, list], current_ids: dict[str, set[str] | None]) -> dict[str, list]:
    out = {}
    if "guide" in items_by_source:
        out["guide"] = produce_guide_relations(items_by_source["guide"], current_ids=current_ids.get("guide"))
        if "material" in items_by_source:
            out["guide_shadow"] = produce_guide_material_shadow(
                items_by_source["guide"],
                items_by_source["material"],
                current_guide_ids=current_ids.get("guide"),
                current_material_ids=current_ids.get("material"),
            )
    if "material" in items_by_source:
        out["material"] = produce_safety_material_relations(items_by_source["material"], current_ids=current_ids.get("material"))
    if "accident" in items_by_source:
        out["accident"] = produce_accident_relations(items_by_source["accident"])
    if "law" in items_by_source:
        out["law"] = produce_law_relations(items_by_source["law"])
    if "precedent" in items_by_source:
        out["precedent"] = produce_precedent_relations(items_by_source["precedent"])
    if "knowledge" in items_by_source:
        out["knowledge"] = produce_knowledge_center_relations(items_by_source["knowledge"] or None)
    return out


def main(argv: list[str] | None = None) -> int:
    _load_env()
    p = argparse.ArgumentParser(description="OBJ-GRAPH manual refresh (default dry-run)")
    p.add_argument("--apply", action="store_true", help="Write Graph tables. Default is dry-run.")
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
    if args.fixture_json:
        with open(args.fixture_json, encoding="utf-8") as fh:
            items_by_source = json.load(fh)
        items_by_source = {k: v for k, v in items_by_source.items() if k in wanted}
    else:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        items_by_source, failed = load_production_sources(sb, wanted)

    current_ids = {
        key: {str(item.get("content_id")) for item in rows if item.get("content_id")}
        for key, rows in items_by_source.items()
    }
    produced = produce_all(items_by_source, current_ids)
    scanned = {key: len(rows) for key, rows in items_by_source.items()}
    store = MemoryGraphStore()
    if args.apply:
        raise SystemExit(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "error_code": "PRODUCTION_APPLY_GATED",
                    "error_message": "WO-SAFETY-KNOWLEDGE-OBJ-GRAPH-IMPL-001: --apply is blocked until GPT core review. Dry-run only.",
                    "started_at": now_kst().isoformat(),
                },
                ensure_ascii=False,
            )
        )
    report = refresh_graph(
        store=store,
        produced_by_source=produced,
        scanned_by_source=scanned,
        failed_sources=failed,
        apply=False,
        context_filter=context_filter,
    )
    payload = report.as_dict()
    payload["db_write"] = 0
    payload["started_at"] = now_kst().isoformat()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if report.status in {"DRY_RUN", "COMPLETED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
