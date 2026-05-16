# routers/semantic_adapter_api.py — Operational Semantic Adapter API
"""
Legacy State → Canonical Grammar 변환.
Watch/Governance/LLM 계층의 운영 의미 정규화.
"""

import logging
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/semantic", tags=["의미변환"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


@router.get("/translate")
def translate_state_api(source_table: str, key: str, value: str):
    """단일 상태 → Canonical Event 변환."""
    try:
        from watch_engine.semantic_adapter import translate_state
        result = translate_state(_sb(), source_table, key, value)
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/translate-record")
def translate_record_api(source_table: str, record_id: str):
    """레코드 전체 → Canonical Context 변환."""
    try:
        from watch_engine.semantic_adapter import translate_record
        sb = _sb()

        # \ud14c\uc774\ube14\ubcc4 \ub808\ucf54\ub4dc \uc870\ud68c
        table_configs = {
            "payments": ("payments", "id"),
            "subscriptions": ("subscriptions", "id"),
            "engine_integrity_event": ("engine_integrity_event", "id"),
            "generated_document": ("generated_document", "id"),
        }

        if source_table not in table_configs:
            return {"status": "error", "message": f"\uc9c0\uc6d0\ud558\uc9c0 \uc54a\ub294 \ud14c\uc774\ube14: {source_table}"}

        tbl, pk = table_configs[source_table]
        record = sb.table(tbl).select("*").eq(pk, record_id).limit(1).execute()
        if not record.data:
            return {"status": "error", "message": "\ub808\ucf54\ub4dc \uc5c6\uc74c"}

        result = translate_record(sb, source_table, record.data[0])
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/mappings")
def get_all_mappings():
    """전체 Legacy → Canonical 매핑 목록."""
    try:
        resp = _sb().table("legacy_state_mapping") \
            .select("*").eq("enabled", True) \
            .order("source_table,legacy_key,legacy_value").execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/coverage")
def get_mapping_coverage():
    """매\ud551 \ucee4\ubc84\ub9ac\uc9c0 \uc694\uc57d."""
    try:
        sb = _sb()
        mappings = sb.table("legacy_state_mapping").select("source_table,legacy_key") \
            .eq("enabled", True).execute()

        coverage = {}
        for m in (mappings.data or []):
            t = m["source_table"]
            if t not in coverage:
                coverage[t] = {"fields": set(), "count": 0}
            coverage[t]["fields"].add(m["legacy_key"])
            coverage[t]["count"] += 1

        result = []
        for t, d in sorted(coverage.items()):
            result.append({
                "source_table": t,
                "mapped_fields": sorted(d["fields"]),
                "mapping_count": d["count"],
            })

        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/invalidate-cache")
def invalidate_adapter_cache():
    """매\ud551 \uce90\uc2dc \ucd08\uae30\ud654."""
    try:
        from watch_engine.semantic_adapter import invalidate_cache
        invalidate_cache()
        return {"status": "success", "message": "\uce90\uc2dc \ucd08\uae30\ud654 \uc644\ub8cc"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
