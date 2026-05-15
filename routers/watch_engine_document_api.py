# routers/watch_engine_document_api.py — Document Output Pipeline API v3
"""
MVP 문서 생성 + Runtime Activation + Gotenberg PDF + Download.
v3: Gotenberg 실제 연결, download redirect, generate-pdf async.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/watch-engine/documents", tags=["문서출력"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


# ═══ Workflow-Document Registry ═══

@router.get("/workflow-documents")
def get_workflow_documents(flow_key: str = None):
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
    try:
        sb = _sb()
        wdr = sb.table("workflow_document_registry").select("*").eq("enabled", True).order("flow_key,priority").execute()
        form_codes = list(set(r["form_code"] for r in (wdr.data or [])))
        forms = {}
        if form_codes:
            resp = sb.table("document_form_master").select("form_code,form_name,form_type,obligation_type,trigger_event,law_name") \
                .in_("form_code", form_codes).execute()
            for f in (resp.data or []):
                forms[f["form_code"]] = f
        gen_count = sb.table("generated_document").select("id", count="exact").execute()
        activation_count = sb.table("runtime_document_activation").select("id", count="exact").execute()
        results = []
        for r in (wdr.data or []):
            form = forms.get(r["form_code"], {})
            results.append({**r, "form_type": form.get("form_type"), "obligation_type": form.get("obligation_type"),
                            "trigger_event": form.get("trigger_event"), "law_name": form.get("law_name")})
        return {"status": "success", "data": {"documents": results, "total_mvp": len(results),
                "generated_count": gen_count.count or 0, "activation_count": activation_count.count or 0}}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Runtime Activation (Manual) ═══

class ActivateBody(BaseModel):
    flow_key: str
    trace_id: str
    tenant_id: Optional[str] = None
    factory_id: Optional[str] = None
    actor_id: Optional[str] = "founder"
    workflow_context: Optional[dict] = None


@router.post("/activate")
def activate_documents(body: ActivateBody):
    """수동 문서 활성화 (workflow 완료 후 호출)."""
    try:
        from watch_engine.document import activate_documents_for_workflow
        result = activate_documents_for_workflow(
            _sb(),
            flow_key=body.flow_key, trace_id=body.trace_id,
            tenant_id=body.tenant_id, factory_id=body.factory_id,
            actor_id=body.actor_id, workflow_context=body.workflow_context,
        )
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ PDF Generation (Gotenberg) ═══

@router.post("/generate-pdf/{generated_doc_id}")
async def generate_pdf(generated_doc_id: str):
    """Gotenberg HTML→PDF 변환 + Storage 업로드."""
    try:
        from watch_engine.document import render_pdf_gotenberg
        result = await render_pdf_gotenberg(_sb(), generated_doc_id)
        return {"status": "success" if result.get("success") else "error", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Download ═══

@router.get("/download/{generated_doc_id}")
def download_document(generated_doc_id: str):
    """PDF 다운로드 (redirect to Storage URL)."""
    try:
        sb = _sb()
        gen = sb.table("generated_document") \
            .select("download_url,storage_path,status,document_name") \
            .eq("id", generated_doc_id).limit(1).execute()

        if not gen.data:
            return {"status": "error", "message": "문서를 찾을 수 없습니다"}

        g = gen.data[0]

        if g.get("download_url"):
            return RedirectResponse(url=g["download_url"], status_code=302)

        if g.get("storage_path"):
            try:
                url = sb.storage.from_("form-outputs").get_public_url(g["storage_path"])
                return RedirectResponse(url=url, status_code=302)
            except Exception:
                pass

        return {"status": "error", "message": f"PDF 미생성 (상태: {g.get('status')})"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Activations List ═══

@router.get("/activations")
def get_activations(limit: int = 20):
    try:
        resp = _sb().table("runtime_document_activation").select("*") \
            .order("created_at", desc=True).limit(limit).execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Generated Documents ═══

@router.get("/generated")
def get_generated_documents(limit: int = 20):
    try:
        resp = _sb().table("generated_document") \
            .select("id,flow_key,trace_id,tenant_id,form_code,document_name,export_type,status,download_url,version,created_at") \
            .order("created_at", desc=True).limit(limit).execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Forms Browse ═══

@router.get("/forms")
def browse_forms(form_category: str = None, limit: int = 50):
    try:
        q = _sb().table("document_form_master") \
            .select("form_code,form_name,form_type,form_category,obligation_type,trigger_event,law_name,is_active") \
            .eq("is_active", True).order("form_name").limit(limit)
        if form_category:
            q = q.eq("form_category", form_category)
        return {"status": "success", "data": q.execute().data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Summary ═══

@router.get("/summary")
def get_document_summary():
    try:
        sb = _sb()
        forms = sb.table("document_form_master").select("form_code", count="exact").eq("is_active", True).execute()
        schemas = sb.table("document_schema_registry").select("id", count="exact").execute()
        wdr = sb.table("workflow_document_registry").select("id", count="exact").eq("enabled", True).execute()
        gen = sb.table("generated_document").select("id", count="exact").execute()
        gen_ready = sb.table("generated_document").select("id", count="exact").eq("status", "GENERATED").execute()
        act = sb.table("runtime_document_activation").select("id", count="exact").execute()
        runtime = sb.table("runtime_document_data").select("id", count="exact").execute()
        return {"status": "success", "data": {
            "form_master": forms.count or 0, "schema_registry": schemas.count or 0,
            "workflow_document_links": wdr.count or 0,
            "generated_documents": gen.count or 0,
            "generated_ready": gen_ready.count or 0,
            "runtime_activations": act.count or 0,
            "runtime_data": runtime.count or 0,
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}
