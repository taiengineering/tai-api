"""Document Activation Service v1.2 — Gotenberg PDF 연결.

v1.2: Gotenberg HTML→PDF 변환 + Supabase Storage 업로드 + download URL.
v1.1: FK fix, dedupe fix.
"""

import logging
import json
import io
import os
from datetime import datetime, timezone
from typing import Optional
from services.time import now_kst

logger = logging.getLogger("watch_engine.document.activation")

GOTENBERG_URL = os.getenv("GOTENBERG_URL", "http://tai-gotenberg.internal:3000")


def activate_documents_for_workflow(
    sb,
    flow_key: str,
    trace_id: str,
    tenant_id: str = None,
    factory_id: str = None,
    actor_id: str = None,
    workflow_context: dict = None,
) -> dict:
    """Workflow 완료 시 연결된 문서 자동 activation."""
    stats = {"activated": 0, "errors": 0, "activations": []}

    try:
        docs = sb.table("workflow_document_registry") \
            .select("form_code,form_name,auto_generate,approval_required") \
            .eq("flow_key", flow_key).eq("enabled", True) \
            .order("priority").execute()

        if not docs.data:
            return stats

        for doc in docs.data:
            try:
                form_code = doc["form_code"]

                # Dedupe: 동일 trace_id + flow_key
                existing = sb.table("runtime_document_activation") \
                    .select("id") \
                    .eq("trace_id", trace_id) \
                    .eq("flow_key", flow_key) \
                    .execute()

                if existing.data:
                    continue

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


async def render_pdf_gotenberg(sb, generated_doc_id: str) -> dict:
    """Gotenberg HTML→PDF 변환 + Storage 업로드.

    기존 diagnosis_proposal.py 패턴 재사용.
    Returns: {"success": bool, "download_url": str|None, "error": str|None}
    """
    try:
        import httpx

        # 1. generated_document 조회
        gen = sb.table("generated_document") \
            .select("*").eq("id", generated_doc_id).limit(1).execute()
        if not gen.data:
            return {"success": False, "error": "generated document not found"}

        g = gen.data[0]
        form_code = g.get("form_code")
        if not form_code:
            return {"success": False, "error": "no form_code"}

        # 2. form_master에서 HTML 템플릿 경로
        form = sb.table("document_form_master") \
            .select("form_name,storage_html_path,form_code") \
            .eq("form_code", form_code).limit(1).execute()

        if not form.data:
            sb.table("generated_document").update({"status": "FAILED"}) \
                .eq("id", generated_doc_id).execute()
            return {"success": False, "error": f"form {form_code} not found"}

        f = form.data[0]
        html_path = f.get("storage_html_path")

        if not html_path:
            # HTML 템플릿 없음 → 기본 HTML 생성
            html_content = _build_default_html(g, f)
        else:
            # Storage에서 HTML 템플릿 다운로드
            try:
                html_bytes = sb.storage.from_("form-templates").download(html_path)
                html_content = html_bytes.decode("utf-8") if isinstance(html_bytes, bytes) else str(html_bytes)
            except Exception as e:
                logger.warning("HTML template download failed, using default: %s", e)
                html_content = _build_default_html(g, f)

        # 3. Gotenberg HTML → PDF
        url = f"{GOTENBERG_URL}/forms/chromium/convert/html"
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                files={"files": ("index.html", html_content.encode("utf-8"), "text/html")},
                data={
                    "paperWidth": "8.27",
                    "paperHeight": "11.69",
                    "marginTop": "0.4",
                    "marginBottom": "0.4",
                    "marginLeft": "0.4",
                    "marginRight": "0.4",
                    "printBackground": "true",
                    "scale": "1",
                },
            )

        if response.status_code != 200:
            logger.error("Gotenberg error: %s %s", response.status_code, response.text[:200])
            sb.table("generated_document").update({"status": "FAILED"}) \
                .eq("id", generated_doc_id).execute()
            return {"success": False, "error": f"Gotenberg {response.status_code}"}

        pdf_bytes = response.content

        # 4. Supabase Storage 업로드
        now_str = now_kst().strftime("%Y%m%d_%H%M%S")
        filename = f"TAI_{form_code}_{now_str}.pdf"
        tenant = g.get("tenant_id") or "general"
        storage_path = f"{tenant}/{filename}"

        try:
            sb.storage.from_("form-outputs").upload(
                path=storage_path,
                file=pdf_bytes,
                file_options={"content-type": "application/pdf", "upsert": "true"},
            )
            download_url = sb.storage.from_("form-outputs").get_public_url(storage_path)
        except Exception as e:
            logger.warning("Storage upload failed: %s", e)
            download_url = None

        # 5. generated_document 상태 업데이트
        sb.table("generated_document").update({
            "status": "GENERATED",
            "storage_path": storage_path,
            "download_url": download_url,
            "document_name": f.get("form_name"),
        }).eq("id", generated_doc_id).execute()

        return {
            "success": True,
            "download_url": download_url,
            "storage_path": storage_path,
            "filename": filename,
            "form_code": form_code,
            "pdf_size_bytes": len(pdf_bytes),
        }

    except Exception as e:
        logger.error("render_pdf_gotenberg failed: %s", e)
        try:
            sb.table("generated_document").update({"status": "FAILED"}) \
                .eq("id", generated_doc_id).execute()
        except Exception:
            pass
        return {"success": False, "error": str(e)[:200]}


def _build_default_html(gen: dict, form: dict) -> str:
    """HTML 템플릿이 없을 때 기본 문서 HTML 생성."""
    form_name = form.get("form_name") or gen.get("document_name") or "문서"
    form_code = gen.get("form_code") or ""
    tenant_id = gen.get("tenant_id") or ""
    now = now_kst().strftime("%Y년 %m월 %d일")

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');
body {{ font-family: 'Noto Sans KR', sans-serif; padding: 40px; color: #333; }}
h1 {{ font-size: 24px; border-bottom: 2px solid #333; padding-bottom: 12px; }}
.meta {{ color: #666; font-size: 13px; margin-bottom: 24px; }}
.content {{ font-size: 14px; line-height: 1.8; }}
.footer {{ margin-top: 40px; text-align: center; color: #999; font-size: 11px; }}
</style>
</head>
<body>
<h1>{form_name}</h1>
<div class="meta">
  문서번호: {form_code}<br>
  사업장: {tenant_id}<br>
  생성일: {now}<br>
</div>
<div class="content">
  <p>본 문서는 TAI Safe 플랫폼에서 자동 생성된 문서입니다.</p>
  <p>실제 데이터 바인딩은 런타임 문서 데이터와 연결 후 완성됩니다.</p>
</div>
<div class="footer">
  TAI Safe — 산업안전 컴플라이언스 플랫폼 | {now}
</div>
</body>
</html>"""
