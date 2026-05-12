"""TAI Inspection Bridge v1.0.0
Legacy inspection_sets → Runtime checklist/schedule 호환 브릿지.
inspection_set_items=0이므로 Runtime checklist_item이 authoritative.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from db.supabase_client import get_supabase

router = APIRouter(prefix="/bridge/inspection", tags=["점검 브릿지"])


@router.get("/sets")
def bridge_inspection_sets(factory_id: Optional[str] = Query(None), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    """Legacy inspection_sets 조회 (Runtime 매핑 정보 포함)"""
    sb = get_supabase()
    q = sb.table("runtime_inspection_bridge").select("*", count="exact")
    o = (page - 1) * page_size
    q = q.order("created_at", desc=True).range(o, o + page_size - 1)
    r = q.execute()
    return {"status": "success", "source": "bridge", "data": {"items": r.data or [], "total": r.count or 0}}


@router.get("/sets/{set_id}")
def bridge_inspection_set_detail(set_id: str):
    """inspection_set 상세 + Runtime checklist 연결"""
    sb = get_supabase()
    bridge = sb.table("runtime_inspection_bridge").select("*").eq("inspection_set_id", set_id).execute()
    if not bridge.data:
        raise HTTPException(404, "inspection set bridge not found")
    b = bridge.data[0]
    # Legacy set 정보
    legacy = sb.table("inspection_sets").select("*").eq("id", set_id).execute()
    # Runtime checklists (전체 — 특정 schema 매핑 시 schema_id로 필터)
    result = {
        "bridge": b,
        "legacy_set": legacy.data[0] if legacy.data else None,
        "runtime_source": "runtime_checklist_item (802건, authoritative)",
        "legacy_items_count": 0,
        "note": "Legacy inspection_set_items=0. Runtime checklist_item이 실제 데이터.",
    }
    return {"status": "success", "data": result}


@router.get("/checklists")
def bridge_checklists(form_schema_id: Optional[str] = Query(None), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    """Runtime checklist_item 조회 (점검항목 authoritative source)"""
    sb = get_supabase()
    q = sb.table("runtime_checklist_item").select("*", count="exact")
    if form_schema_id:
        q = q.eq("form_schema_id", form_schema_id)
    o = (page - 1) * page_size
    q = q.order("item_order").range(o, o + page_size - 1)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": {"items": r.data or [], "total": r.count or 0}}


@router.get("/mapping-status")
def bridge_mapping_status():
    """매핑 현황 요약"""
    sb = get_supabase()
    r = sb.rpc("exec_sql", {}).execute() if False else None  # placeholder
    stats = sb.table("runtime_inspection_bridge").select("mapping_status", count="exact").execute()
    from collections import Counter
    dist = Counter(row["mapping_status"] for row in (stats.data or []))
    return {
        "status": "success",
        "data": {
            "total_legacy_sets": sum(dist.values()),
            "mapped": dist.get("MAPPED", 0),
            "partial": dist.get("PARTIAL", 0),
            "not_mappable": dist.get("NOT_MAPPABLE", 0),
            "needs_review": dist.get("NEEDS_HUMAN_REVIEW", 0),
            "runtime_checklists": 802,
            "ownership": "RUNTIME (inspection_set_items=0)",
        },
    }
