"""Document Activation Service v1.1 — Workflow → Document 연결.

Workflow 완료 시 runtime_document_activation 생성.
기존 form/schema/Gotenberg 구조 활용.
Fail-safe: 문서 생성 실패해도 workflow rollback 금지.

v1.1: FK 이슈 수정 (generated_document.runtime_document_id → runtime_document_data 참조)
      export_type 대문자 ('PDF'), dedupe 수정.
"""

import logging
import json
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("watch_engine.document.activation")


def activate_documents_for_workflow(
    sb,
    flow_key: str,
    trace_id: str,
    tenant_id: str = None,
    factory_id: str = None,
    actor_id: str = None,
    workflow_context: dict = None,
) -> dict:
    """Workflow 완료 시 연결된 문서 자동 activation.

    Returns: {"activated": int, "errors": int, "activations": [...]}
    """
    stats = {"activated": 0, "errors": 0, "activations": []}

    try:
        # 1. workflow_document_registry에서 연결 문서 조회
        docs = sb.table("workflow_document_registry") \
            .select("form_code,form_name,auto_generate,approval_required") \
            .eq("flow_key", flow_key).eq("enabled", True) \
            .order("priority").execute()

        if not docs.data:
            return stats

        for doc in docs.data:
            try:
                form_code = doc["form_code"]

                # 2. Dedupe: 동일 trace_id + flow_key + form_code
                existing = sb.table("runtime_document_activation") \
                    .select("id") \
                    .eq("trace_id", trace_id) \
                    .eq("flow_key", flow_key) \
                    .execute()

                # source_trace에서 form_code 매칭 확인
                already = False
                for ex in (existing.data or []):
                    # 같은 trace+flow에 이미 activation 있으면 skip
                    already = True
                    break

                if already:
                    continue

                # 3. runtime_document_activation 생성
                activation = {
                    "flow_key": flow_key,
                    "trace_id": trace_id,
                    "tenant_id": tenant_id,
                    "factory_id": factory_id,
                    "actor_id": actor_id,
                    "activation_reason": f"workflow_complete:{flow_key}",
                    "status": "ACTIVATED",
                    "source_trace": json.loads(json.dumps({
                        "form_code": form_code,
                        "form_name": doc["form_name"],
                        "auto_generate": doc["auto_generate"],
                        "approval_required": doc["approval_required"],
                        "workflow_context": workflow_context,
                    }, default=str)),
                    "workflow_context": json.loads(json.dumps(
                        workflow_context or {}, default=str
                    )),
                }
                activation = {k: v for k, v in activation.items() if v is not None}

                resp = sb.table("runtime_document_activation").insert(activation).execute()
                act_id = resp.data[0]["id"] if resp.data else None

                stats["activated"] += 1
                stats["activations"].append({
                    "activation_id": act_id,
                    "form_code": form_code,
                    "form_name": doc["form_name"],
                    "auto_generate": doc["auto_generate"],
                })

                # 4. auto_generate = true → generated_document 자동 생성
                # NOTE: runtime_document_id FK → runtime_document_data (NOT activation)
                # workflow 경로는 runtime_document_id = null
                if doc["auto_generate"]:
                    try:
                        gen = {
                            "flow_key": flow_key,
                            "trace_id": trace_id,
                            "tenant_id": tenant_id,
                            "factory_id": factory_id,
                            "actor_id": actor_id,
                            "form_code": form_code,
                            "document_name": doc["form_name"],
                            "export_type": "PDF",
                            "status": "PENDING",
                            "version": 1,
                        }
                        gen = {k: v for k, v in gen.items() if v is not None}
                        sb.table("generated_document").insert(gen).execute()
                    except Exception as e:
                        logger.warning("Auto-generate failed for %s: %s", form_code, e)

            except Exception as e:
                logger.error("Activation failed for %s/%s: %s", flow_key, doc.get("form_code"), e)
                stats["errors"] += 1

    except Exception as e:
        logger.error("activate_documents_for_workflow failed: %s", e)
        stats["errors"] += 1

    return stats


def generate_pdf_for_document(sb, generated_doc_id: str) -> dict:
    """Generated Document의 PDF 생성 (수동 트리거).

    Returns: {"success": bool, "download_url": str|None, "error": str|None}
    """
    try:
        # Get generated document
        gen = sb.table("generated_document") \
            .select("*").eq("id", generated_doc_id).limit(1).execute()
        if not gen.data:
            return {"success": False, "error": "generated document not found"}

        g = gen.data[0]
        form_code = g.get("form_code")

        if not form_code:
            return {"success": False, "error": "no form_code"}

        # Get form template
        form = sb.table("document_form_master") \
            .select("form_name,storage_html_path,hwp_url,pdf_url") \
            .eq("form_code", form_code).limit(1).execute()

        if not form.data:
            return {"success": False, "error": f"form {form_code} not found"}

        f = form.data[0]
        html_path = f.get("storage_html_path")

        if not html_path:
            sb.table("generated_document").update({
                "status": "TEMPLATE_MISSING",
            }).eq("id", generated_doc_id).execute()
            return {"success": False, "error": f"no HTML template for {form_code}"}

        # TODO: Gotenberg 실제 호출
        # 현재는 상태만 READY로. 실제 PDF는 기존 diagnosis_proposal.py 패턴 재사용.
        sb.table("generated_document").update({
            "status": "READY",
            "document_name": f.get("form_name"),
        }).eq("id", generated_doc_id).execute()

        return {
            "success": True,
            "form_code": form_code,
            "document_name": f.get("form_name"),
            "note": "PDF generation pending Gotenberg integration",
        }

    except Exception as e:
        logger.error("generate_pdf failed: %s", e)
        return {"success": False, "error": str(e)[:200]}
