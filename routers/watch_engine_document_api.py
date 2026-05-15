# routers/watch_engine_document_api.py — Document Output Pipeline API
"""
MVP 문서 생성 + Workflow-Document 연결 + 런타임 활성화.
P0 런치 블로커 해결 중심.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/watch-engine/documents", tags=["문서출력"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


# ═══ Workflow-Document Registry ═══

@router.get("/workflow-documents")
def get_workflow_documents(flow_key: str = None):
    """Workflow별 연결 문서 목록."""
    try:
        q = _sb().table("workflow_document_registry").select("*").eq("enabled", True).order("flow_key,priority")
        if flow_key:
            q = q.eq("flow_key", flow_key)
        return {"status": "success", "data": q.execute().data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ MVP Document List ═══

@router.get("/mvp")
def get_mvp_documents():
    """MVP 10종 문서 + 생성 현황."""
    try:
        sb = _sb()
        # Workflow-document 연결
        wdr = sb.table("workflow_document_registry").select("*").eq("enabled", True).order("flow_key,priority").execute()

        # Form master 정보
        form_codes = list(set(r["form_code"] for r in (wdr.data or [])))
        forms = {}
        if form_codes:
            resp = sb.table("document_form_master").select("form_code,form_name,form_type,obligation_type,trigger_event,law_name") \
                .in_("form_code", form_codes).execute()
            for f in (resp.data or []):
                forms[f["form_code"]] = f

        # Generated document 건수
        gen_count = sb.table("generated_document").select("id", count="exact").execute()
        activation_count = sb.table("runtime_document_activation").select("id", count="exact").execute()

        results = []
        for r in (wdr.data or []):
            form = forms.get(r["form_code"], {})
            results.append({
                "flow_key": r["flow_key"],
                "form_code": r["form_code"],
                "form_name": r["form_name"],
                "auto_generate": r["auto_generate"],
                "approval_required": r["approval_required"],
                "form_type": form.get("form_type"),
                "obligation_type": form.get("obligation_type"),
                "trigger_event": form.get("trigger_event"),
                "law_name": form.get("law_name"),
            })

        return {"status": "success", "data": {
            "documents": results,
            "total_mvp": len(results),
            "generated_count": gen_count.count or 0,
            "activation_count": activation_count.count or 0,
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Generated Documents ═══

@router.get("/generated")
def get_generated_documents(limit: int = 20):
    """생성된 문서 목록."""
    try:
        resp = _sb().table("generated_document").select("*") \
            .order("created_at", desc=True).limit(limit).execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Runtime Activations ═══

@router.get("/activations")
def get_activations(limit: int = 20):
    """런타임 활성화 목록."""
    try:
        resp = _sb().table("runtime_document_activation").select("*") \
            .order("created_at", desc=True).limit(limit).execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Form Master Browse ═══

@router.get("/forms")
def browse_forms(form_category: str = None, limit: int = 50):
    """문서 서식 브라우징."""
    try:
        q = _sb().table("document_form_master") \
            .select("form_code,form_name,form_type,form_category,obligation_type,trigger_event,law_name,is_active") \
            .eq("is_active", True).order("form_name").limit(limit)
        if form_category:
            q = q.eq("form_category", form_category)
        return {"status": "success", "data": q.execute().data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Document Pipeline Summary ═══

@router.get("/summary")
def get_document_summary():
    """문서 파이프라인 요약."""
    try:
        sb = _sb()
        forms = sb.table("document_form_master").select("form_code", count="exact").eq("is_active", True).execute()
        schemas = sb.table("document_schema_registry").select("id", count="exact").execute()
        wdr = sb.table("workflow_document_registry").select("id", count="exact").eq("enabled", True).execute()
        gen = sb.table("generated_document").select("id", count="exact").execute()
        act = sb.table("runtime_document_activation").select("id", count="exact").execute()
        runtime = sb.table("runtime_document_data").select("id", count="exact").execute()

        return {"status": "success", "data": {
            "form_master": forms.count or 0,
            "schema_registry": schemas.count or 0,
            "workflow_document_links": wdr.count or 0,
            "generated_documents": gen.count or 0,
            "runtime_activations": act.count or 0,
            "runtime_data": runtime.count or 0,
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}
